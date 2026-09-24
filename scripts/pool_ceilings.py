"""The free bound a frozen pool carries — ledger task **40.4**.

`eval/pool-promotion/protocol.toml` -> `[ceilings]` states both formulas this module computes,
per question and as a mean over a corpus or a slice of it: the oracle gain a perfect reorder of
the pool would add over dense's own RR@5, and the promotion gain `anchor-promote`'s own rule and
matcher could actually reach. Both are read off a captured pool and a scored run — this module
reads the store once, to recover each pool chunk's content by its recorded hash, and computes
nothing a reorderer's own outcome could touch: no ranking is re-run, no reorderer stage is called.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import psycopg
from pydantic import BaseModel, ConfigDict, ValidationError

from weft_cli.eval_commands import document_labels_from_manifest
from weft_cli.eval_scoring import resolve_labels
from weft_eval.pool import LoadedPool, PoolManifest, PoolQuestion, load_pool_manifest
from weft_eval.question_set import Question, QuestionSet, QuestionSetError, read_question_set
from weft_eval.run_record import PerQuestionScores, QuestionKey, RunRecord, load_run_record
from weft_kernel.errors import WeftError
from weft_kernel.payload import Produced
from weft_retrieve.anchor_promote import anchor_contained
from weft_retrieve.intent_and_anchors import find_anchors

#: How many node ids one `WHERE id = ANY(%s)` batch carries.
_CONTENT_BATCH: Final[int] = 1000


class QuestionCeiling(BaseModel):
    """One question's free bound — both formulas evaluated over its own captured pool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    rr5: float
    any_relevant_in_pool: bool
    best_relevant_rank: int | None
    distinct_documents: int
    rule_fires: bool
    oracle_gain: float
    promotion_gain: float


class SliceCeiling(BaseModel):
    """Both ceilings, and the two numbers they are ceilings over, meaned across a slice."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    oracle_ceiling: float
    promotion_ceiling: float
    mrr5: float
    relevant_in_pool: float


def _verify_contents(question: PoolQuestion, contents: Mapping[str, str]) -> None:
    for chunk in question.chunks:
        content = contents.get(chunk.node_id)
        if content is None:
            raise ValueError(f"no content given for pool chunk '{chunk.node_id}'")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != chunk.content_sha256:
            raise ValueError(
                f"content for pool chunk '{chunk.node_id}' no longer hashes to its recorded "
                "content_sha256"
            )


def _best_relevant_rank(question: PoolQuestion, relevant: frozenset[str]) -> int | None:
    for rank, chunk in enumerate(question.chunks, start=1):
        if chunk.document_id in relevant:
            return rank
    return None


def _promotion_gain(
    question: PoolQuestion,
    relevant: frozenset[str],
    contents: Mapping[str, str],
    anchors: tuple[str, ...],
    rr5: float,
) -> float:
    for chunk in question.chunks:
        if chunk.document_id not in relevant:
            continue
        content = contents[chunk.node_id]
        if any(anchor_contained(anchor, content) for anchor in anchors):
            return 1 - rr5
    return 0.0


def question_ceiling(
    question: PoolQuestion,
    *,
    text: str,
    relevant: frozenset[str],
    contents: Mapping[str, str],
    rr5: float,
) -> QuestionCeiling:
    """`question`'s own ceiling — see the module docstring for both formulas.

    Every chunk's content is checked against `PoolChunk.content_sha256` before anything else is
    computed, naming the chunk whose content no longer hashes to what the pool recorded.
    """
    _verify_contents(question, contents)

    best_relevant_rank = _best_relevant_rank(question, relevant)
    any_relevant_in_pool = best_relevant_rank is not None
    distinct_documents = len({chunk.document_id for chunk in question.chunks})

    anchors = tuple(anchor.text for anchor in find_anchors(text))
    rule_fires = bool(anchors)

    oracle_gain = (1.0 if any_relevant_in_pool else 0.0) - rr5

    promotion_gain = (
        _promotion_gain(question, relevant, contents, anchors, rr5) if rule_fires else 0.0
    )

    return QuestionCeiling(
        question_id=question.id,
        rr5=rr5,
        any_relevant_in_pool=any_relevant_in_pool,
        best_relevant_rank=best_relevant_rank,
        distinct_documents=distinct_documents,
        rule_fires=rule_fires,
        oracle_gain=oracle_gain,
        promotion_gain=promotion_gain,
    )


def _mean_ceiling(group: Sequence[QuestionCeiling]) -> SliceCeiling:
    n = len(group)
    return SliceCeiling(
        n=n,
        oracle_ceiling=sum(c.oracle_gain for c in group) / n,
        promotion_ceiling=sum(c.promotion_gain for c in group) / n,
        mrr5=sum(c.rr5 for c in group) / n,
        relevant_in_pool=sum(1.0 for c in group if c.any_relevant_in_pool) / n,
    )


def _axis_groups(
    ceilings: Sequence[QuestionCeiling], axes: Mapping[str, Mapping[str, str]]
) -> dict[str, list[QuestionCeiling]]:
    groups: dict[str, list[QuestionCeiling]] = {}
    axis_values: dict[str, set[str]] = {}
    for question_axes in axes.values():
        for axis, value in question_axes.items():
            axis_values.setdefault(axis, set()).add(value)
    for axis, values in axis_values.items():
        for value in values:
            group = [
                ceiling
                for ceiling in ceilings
                if axes.get(ceiling.question_id, {}).get(axis) == value
            ]
            if group:
                groups[f"{axis}={value}"] = group
    return groups


def slice_summary(
    ceilings: Sequence[QuestionCeiling], axes: Mapping[str, Mapping[str, str]]
) -> dict[str, SliceCeiling]:
    """Both ceilings, meaned over every declared slice — see the module docstring.

    `"all"` over every question, `f"{axis}={value}"` for every axis/value pair any question's
    `axes[question.question_id]` carries, and `"rule-fires=true"`/`"rule-fires=false"` from
    `QuestionCeiling.rule_fires` directly rather than from `axes`. A slice no question falls into
    is not emitted.
    """
    groups: dict[str, list[QuestionCeiling]] = {}
    if ceilings:
        groups["all"] = list(ceilings)

    groups.update(_axis_groups(ceilings, axes))

    for flag, label in ((True, "true"), (False, "false")):
        group = [ceiling for ceiling in ceilings if ceiling.rule_fires is flag]
        if group:
            groups[f"rule-fires={label}"] = group

    return {key: _mean_ceiling(group) for key, group in groups.items()}


def relevant_by_question(
    labels: Mapping[str, Sequence[str]],
    *,
    document_ids: Sequence[str],
    document_labels: Mapping[str, str] | None,
) -> dict[str, frozenset[str]]:
    """Each question's `relevant_documents` labels, resolved to the pool's own document ids.

    `document_labels`, when given, maps a manifest id (`eval/questions/*.toml`'s ground-truth
    vocabulary) to the corpus-relative label `resolve_labels` matches against — a label missing
    from it is refused naming the label and the question. Resolution itself is
    `weft_cli.eval_scoring.resolve_labels`, the identical public resolver `weft_cli.eval_scoring.
    score_pipeline` scores with, so a label is never matched a second, drifting way here.
    """
    mapped: dict[str, tuple[str, ...]] = {}
    for question_id, entries in labels.items():
        if document_labels is None:
            mapped[question_id] = tuple(entries)
            continue
        resolved_entries: list[str] = []
        for entry in entries:
            if entry not in document_labels:
                valid = ", ".join(sorted(document_labels))
                raise ValueError(
                    f"question '{question_id}': label '{entry}' names no id in the given "
                    f"manifest. Valid options: {valid}"
                )
            resolved_entries.append(document_labels[entry])
        mapped[question_id] = tuple(resolved_entries)

    all_labels = {label for entries in mapped.values() for label in entries}
    resolved_labels = resolve_labels(all_labels, corpus_document_ids=document_ids)

    return {
        question_id: frozenset(resolved_labels[label] for label in entries)
        for question_id, entries in mapped.items()
    }


def _rr5_by_question(
    record: RunRecord, questions: Sequence[Question]
) -> tuple[dict[str, float], list[str]]:
    """`record`'s own RR@5 per question, and the ids of every question it left out.

    A question is left out when its outcome was not `Produced`.
    """
    per_question: PerQuestionScores | None = None
    if record.question_scores is not None:
        per_question = record.question_scores.get("mrr@5")
    if per_question is None:
        raise ValueError("the record carries no 'mrr@5' question_scores")

    rr5: dict[str, float] = {}
    excluded: list[str] = []
    for index, question in enumerate(questions):
        key = question.id if per_question.keyed_by is QuestionKey.QUESTION_ID else str(index)
        outcome = per_question.scores.get(key)
        if isinstance(outcome, Produced):
            rr5[question.id] = outcome.value
        else:
            excluded.append(question.id)
    return rr5, excluded


def _assert_row_count(
    conn: psycopg.Connection[tuple[Any, ...]], expected: int, *, when: str
) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM weft_nodes")
        row = cur.fetchone()
    found = int(row[0]) if row is not None else 0
    if found != expected:
        raise RowCountMismatchError(
            f"weft_nodes {when}: expected {expected:,} rows (the manifest's store_rows), "
            f"found {found:,} — the measurement is abandoned"
        )


class RowCountMismatchError(RuntimeError):
    """`weft_nodes`'s row count no longer agrees with `PoolManifest.store_rows` — `L8.30`."""


def _fetch_contents(
    conn: psycopg.Connection[tuple[Any, ...]], node_ids: Sequence[str]
) -> dict[str, str]:
    contents: dict[str, str] = {}
    for batch in itertools.batched(node_ids, _CONTENT_BATCH):
        with conn.cursor() as cur:
            cur.execute("SELECT id, content FROM weft_nodes WHERE id = ANY(%s)", (list(batch),))
            for node_id, content in cur.fetchall():
                contents[str(node_id)] = str(content)
    return contents


def _print_slices(slices: Mapping[str, SliceCeiling]) -> None:
    for name in sorted(slices):
        summary = slices[name]
        print(
            f"{name}: n={summary.n} oracle={summary.oracle_ceiling:.4f} "
            f"promotion={summary.promotion_ceiling:.4f} mrr5={summary.mrr5:.4f} "
            f"relevant_in_pool={summary.relevant_in_pool:.4f}",
            flush=True,
        )


def _load_inputs(args: argparse.Namespace) -> tuple[LoadedPool, RunRecord, QuestionSet]:
    loaded_pool = load_pool_manifest(args.manifest)
    record = load_run_record(args.record)
    question_set = read_question_set(args.questions)
    return loaded_pool, record, question_set


def _scores_and_relevance(
    record: RunRecord,
    questions: Sequence[Question],
    labels: Mapping[str, Sequence[str]],
    manifest: PoolManifest,
    document_labels: Mapping[str, str] | None,
) -> tuple[dict[str, float], list[str], dict[str, frozenset[str]]]:
    rr5_by_question, excluded = _rr5_by_question(record, questions)
    relevant = relevant_by_question(
        labels, document_ids=manifest.document_ids, document_labels=document_labels
    )
    return rr5_by_question, excluded, relevant


def main(argv: Sequence[str] | None = None) -> int:
    """Compute every scored question's ceilings from a frozen pool and write them with slices.

    Args:
        argv: The command-line arguments; `None` reads `sys.argv`.

    Returns:
        0 once the ceilings are written, 2 when an input cannot be read or does not agree.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=None)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        loaded_pool, record, question_set = _load_inputs(args)
    except (WeftError, QuestionSetError, ValidationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    manifest: PoolManifest = loaded_pool.manifest
    questions_by_id = {question.id: question for question in question_set.questions}

    document_labels = (
        document_labels_from_manifest(str(args.labels)) if args.labels is not None else None
    )
    labels = {question.id: question.relevant_documents for question in question_set.questions}

    try:
        rr5_by_question, excluded, relevant = _scores_and_relevance(
            record, question_set.questions, labels, manifest, document_labels
        )
    except (ValueError, WeftError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    excluded_set = frozenset(excluded)
    scored_pool_questions = [
        pool_question
        for pool_question in manifest.questions
        if pool_question.id not in excluded_set
    ]
    node_ids = sorted(
        {chunk.node_id for pool_question in scored_pool_questions for chunk in pool_question.chunks}
    )

    try:
        with psycopg.connect(args.dsn, autocommit=True) as conn:
            _assert_row_count(conn, manifest.store_rows, when="before the content fetch")
            contents = _fetch_contents(conn, node_ids)
            _assert_row_count(conn, manifest.store_rows, when="after the content fetch")
    except (psycopg.Error, RowCountMismatchError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        ceilings = [
            question_ceiling(
                pool_question,
                text=questions_by_id[pool_question.id].text,
                relevant=relevant[pool_question.id],
                contents=contents,
                rr5=rr5_by_question[pool_question.id],
            )
            for pool_question in scored_pool_questions
        ]
    except (ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    axes = {
        pool_question.id: dict(questions_by_id[pool_question.id].axes)
        for pool_question in scored_pool_questions
    }
    slices = slice_summary(ceilings, axes)

    _print_slices(slices)

    payload = {
        "manifest": loaded_pool.sha256,
        "record": args.record.stem,
        "experiment": manifest.experiment,
        "arm": manifest.arm,
        "questions": [ceiling.model_dump() for ceiling in ceilings],
        "excluded": excluded,
        "slices": {name: summary.model_dump() for name, summary in slices.items()},
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
