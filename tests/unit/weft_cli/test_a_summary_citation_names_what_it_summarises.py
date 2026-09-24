"""Carried repair **R43.31**: a citation of a node over several sources says what it is.

`weft ask` through `iterative-retrieve` cited a `raptor-corpus` summary as `[1]  — <node id>`,
because a summary over many sources has no one `uri` and the human line printed none.
"""

from __future__ import annotations

import json
import re

from weft_cli import render
from weft_cli.commands import AskCommandResult
from weft_cli.output import AskFormat
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_index.payload import LayerMember, RaptorFacts
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_retrieve.payload import Passage, Query
from weft_store import Scored

_CITATION_LINE = re.compile(r"^  \[1\] (?P<label>.*) — (?P<node_id>\S+)$")


def _leaf(content: str, source: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({SourceId(source)}),
    )


def _summary(sources: tuple[str, ...], *, layer: str | None) -> Node:
    members = [_leaf(f"passage from {source}", source) for source in sources]
    summary = Node.combine(
        members, content="A summary across the corpus.", media_type=MediaType.TEXT
    ).with_ext(
        RaptorFacts(
            members=len(members),
            members_truncated=0,
            characters_held=sum(len(member.content) for member in members),
            characters_shown=sum(len(member.content) for member in members),
            level=1,
        )
    )
    return summary.with_ext(LayerMember(layer=layer)) if layer is not None else summary


def _result(node: Node, citation: Citation) -> AskCommandResult:
    passage = Passage(scored=Scored(value=node, score=0.9), rank=0, retrieved_by="test", label="1")
    answer = Answer(
        origin=Query(text="q"),
        text="the answer [1]",
        stance=AnswerStance.ANSWERED,
        citations=(citation,),
        used=(passage,),
        answered_by="scripted",
    )
    return AskCommandResult(
        question="q",
        top_k=5,
        format=AskFormat.TEXT,
        pipeline_name="iterative-retrieve",
        answer=answer,
    )


def _citation_line(stdout: str | None) -> re.Match[str]:
    assert stdout is not None
    lines = [line for line in stdout.splitlines() if line.startswith("  [1]")]
    assert len(lines) == 1, stdout
    match = _CITATION_LINE.match(lines[0])
    assert match is not None, lines[0]
    return match


def test_a_corpus_summary_citation_names_its_source_count_and_its_layer() -> None:
    # Arrange — what `cited_answer` builds for a summary: no single source, so no uri.
    node = _summary(("doc-a", "doc-b", "doc-c"), layer="raptor-corpus")
    citation = Citation(marker="1", node_id=node.id, source_id=None, uri="")

    # Act
    rendered = render.render_outcome(Produced(value=_result(node, citation)))

    # Assert
    line = _citation_line(rendered.stdout)
    label = line["label"].strip()
    assert label, f"empty source label: {line.string!r}"
    assert re.search(r"\b3 sources\b", label), label
    assert "raptor-corpus" in label, label
    assert line["node_id"] == str(node.id)


def test_a_summary_outside_any_layer_still_names_its_source_count() -> None:
    # Arrange
    node = _summary(("doc-a", "doc-b"), layer=None)
    citation = Citation(marker="1", node_id=node.id, source_id=None, uri="")

    # Act
    rendered = render.render_outcome(Produced(value=_result(node, citation)))

    # Assert
    line = _citation_line(rendered.stdout)
    label = line["label"].strip()
    assert label, f"empty source label: {line.string!r}"
    assert re.search(r"\b2 sources\b", label), label
    assert line["node_id"] == str(node.id)


def test_a_single_source_chunk_citation_renders_exactly_as_before() -> None:
    # Arrange
    node = _leaf("a passage", "doc-a").derive(content="a chunk of doc-a")
    citation = Citation(
        marker="1", node_id=node.id, source_id=SourceId("doc-a"), uri="doc://a", page=7
    )

    # Act
    rendered = render.render_outcome(Produced(value=_result(node, citation)))

    # Assert
    line = _citation_line(rendered.stdout)
    assert line.string == f"  [1] doc://a p.7 — {node.id}"


def test_the_json_citation_of_a_summary_keeps_uri_a_locator_rather_than_a_description() -> None:
    # Arrange — the description is the human line's (owner `weft_cli/render.py`); `uri` and
    # `source_id` stay the honest empties `Citation` documents, never prose a script would open.
    node = _summary(("doc-a", "doc-b", "doc-c"), layer="raptor-corpus")
    citation = Citation(marker="1", node_id=node.id, source_id=None, uri="")

    # Act
    rendered = render.render_outcome(Produced(value=_result(node, citation)), as_json=True)

    # Assert
    assert rendered.stdout is not None
    emitted = json.loads(rendered.stdout.splitlines()[-1])["citations"][0]
    assert emitted["uri"] == ""
    assert emitted["source_id"] is None
    assert emitted["node_id"] == str(node.id)
