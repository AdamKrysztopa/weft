"""Unit tests for `weft_cli.contract_reference`.

Mirrors `packages/weft-rag/src/weft_cli/contract_reference.py`. Covers the happy path
(walking the real, installed first-party contracts, `NodeStore`'s `VectorSearch`
capability sibling included), the edge case (a rendered method reflects the real
signature and docstring, never a hand-typed approximation), and the error case
(`missing_from_walked_set` actually reports what it is asked to, and respects the
waiver). `tests/docs/test_generated_docs.py` is the check against the checked-in file;
this module is the plumbing that produces it.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

import pytest

from weft_chunk.contract import Chunker
from weft_cli.contract_reference import (
    ContractNotDescribableError,
    PublishedContract,
    ReferenceFormatterUnavailableError,
    capability_siblings,
    discover_for_reference,
    missing_from_walked_set,
    published_contracts,
    render_contract_reference,
)
from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_kernel.runner import Stage
from weft_retrieve.contract import ContextPacker, Fuser, QueryScorer, Retriever, Sufficiency
from weft_retrieve.no_retrieval import NoRetrieval
from weft_retrieve.payload import Candidates, QuerySet
from weft_store.contract import NodeStore, TextSearch, VectorSearch


def test_published_contracts_includes_vectorsearch_beside_nodestore() -> None:
    # Arrange
    registry = discover_for_reference()

    # Act
    contracts = {
        published.contract: published.distributions for published in published_contracts(registry)
    }

    # Assert — VectorSearch is never registered under its own name (weft_store.contract's
    # own module docstring), so this is only true if the capability-sibling walk ran. Both
    # distributions appear against `VectorSearch` because the class each of them registered
    # under `NodeStore` provides it — the walk attributes a capability to whoever *satisfies*
    # it, asked of the registered class, never to whoever happens to register a name under
    # the anchor. `TextSearch` is the asymmetry that proves the distinction: `weft-qdrant`
    # registers a store and deliberately does not satisfy it (task 2.6), and the shipped
    # reference must not tell an operator otherwise. Repair for a reviewer finding: the walk
    # copied the anchor's whole distribution set onto every sibling, and the generated
    # manual declared a capability the code refuses.
    assert NodeStore in contracts
    assert VectorSearch in contracts
    assert contracts[VectorSearch] == contracts[NodeStore] == frozenset({"weft-rag", "weft-qdrant"})
    assert contracts[TextSearch] == frozenset({"weft-rag"})


def test_a_stage_contract_is_never_derived_as_another_stages_sibling() -> None:
    """Repair for task 2.13: `weft-retrieve`'s pipeline positions share the one
    method name `run`, so `issubclass` cannot structurally tell `Retriever` from
    `Fuser` from `QueryScorer` — before this filter, registering `no-retrieval`
    under `Retriever` made every one of them satisfied by structure alone, and this
    reference would have printed `weft-retrieve` as "Registered by" for a `Fuser` and
    a `QueryScorer` nothing registers.

    **Every real `Stage` contract in this tree is registered as of task 2.25** —
    `ContextPacker` (task 2.19) and `QueryScorer` (task 2.25's own `query-scorer`) were
    the last two examples of "a `Stage` contract nothing registers" this test could have
    reached for. Rather than keep chasing whichever real contract is still open, this test
    now defines its own never-registered stand-in — `_UnregisteredRetriever`, sharing
    `Retriever`'s exact `In`/`Out` shape and its `run` method name, so `NoRetrieval`
    satisfies it structurally exactly as it structurally satisfies `Fuser` and
    `QueryScorer`. The structural fact under test — `capability_siblings` filters every
    `Stage`-shaped Protocol out of consideration, not merely the ones nothing happens to
    register — does not depend on which real contract is currently open, and a local
    stand-in keeps this test true forever rather than needing a fresh "sharper example"
    every time a task closes the previous one.
    """
    # Arrange — the same structural fact the fix depends on, checked directly first so
    # the assertion on `published_contracts` below is not the only evidence for it.
    # `isinstance`, not `issubclass`, on pyright's own rule: a Protocol carrying a
    # non-method member (`version`) cannot be the right side of `issubclass` statically —
    # `_distributions_satisfying` avoids this by asking only of a `type[object]` pyright
    # cannot specialise; this test asks a concrete question instead.
    instance = NoRetrieval()
    assert isinstance(instance, Fuser)
    assert isinstance(instance, _UnregisteredRetriever)

    # Act
    registry = discover_for_reference()
    contracts = {
        published.contract: published.distributions for published in published_contracts(registry)
    }

    # Assert — `Retriever`, `Fuser`, `ContextPacker` and `QueryScorer` are all real: a name
    # is registered under each, so each is its own anchor with its own registering
    # distribution. `_UnregisteredRetriever` is not found at all, never found-but-empty,
    # because it is not a candidate sibling of anything in the first place —
    # `capability_siblings` excludes every `Stage` contract from the walk, not just the
    # ones nothing structurally satisfies. A walk without that filter would print
    # `weft-retrieve` under it anyway, since `NoRetrieval` satisfies it structurally
    # (asserted above) and `weft-retrieve` is what registers `NoRetrieval` under
    # `Retriever`.
    assert contracts[Retriever] == frozenset({"weft-rag"})
    assert contracts[Fuser] == frozenset({"weft-rag"})
    assert contracts[ContextPacker] == frozenset({"weft-rag"})
    assert contracts[QueryScorer] == frozenset({"weft-rag"})
    assert _UnregisteredRetriever not in contracts
    # `Sufficiency` is not `Stage`-shaped (it takes three arguments, never one payload) —
    # a legitimate capability sibling of `Retriever`, and as of task 2.24 (`llm-sufficiency`,
    # `hedge-phrases`) a satisfied one: the walk attributes it to `weft-retrieve` because that
    # is the distribution whose registered classes actually satisfy the Protocol, the same
    # rule `test_published_contracts_includes_vectorsearch_beside_nodestore` checks above.
    assert Sufficiency in contracts
    assert contracts[Sufficiency] == frozenset({"weft-rag"})


@runtime_checkable
class _UnregisteredRetriever(Stage[QuerySet, Candidates], Protocol):
    """Stand-in: `Retriever`'s exact `In`/`Out` shape and `run` method name, satisfied
    structurally by `NoRetrieval` (and by every real `Retriever`), registered nowhere.
    See `test_a_stage_contract_is_never_derived_as_another_stages_sibling`'s own docstring
    for why a local stand-in replaced the last real "still open" example.

    `version` is declared only under `if TYPE_CHECKING:` and assigned after the class
    body, the same convention every real contract in this tree follows — a real attribute
    here would join `__protocol_attrs__` and `isinstance` would then require `NoRetrieval`
    itself to carry a `.version`, which no plugin instance does.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]: ...


_UnregisteredRetriever.version = "1.0.0"


def test_capability_siblings_excludes_every_stage_contract() -> None:
    # Act
    siblings = capability_siblings(Retriever)

    # Assert — the self-test `08` §3 requires of every floor: prove the exclusion can
    # actually remove something, rather than passing because nothing was ever offered.
    assert Fuser not in siblings
    assert ContextPacker not in siblings
    assert QueryScorer not in siblings
    assert Retriever not in siblings  # never its own sibling either
    assert Sufficiency in siblings


def test_render_contract_reference_reflects_the_real_signature() -> None:
    # Arrange
    registry = discover_for_reference()
    contracts = published_contracts(registry)

    # Act
    rendered = render_contract_reference(contracts)

    # Assert — the edge case: a method's own signature, not a hand-typed approximation.
    # `Chunker.run` takes a `Sequence[Node]` and returns `Outcome[Sequence[Node]]`; if the
    # contract's signature ever changes, these strings change with it because
    # `inspect.signature` read it off the live class, not off a copy in this test. Checked
    # as separate substrings, not one exact line, because `render_contract_reference`
    # pipes its output through `ruff format`, which may wrap a long signature onto
    # several lines — see that function's own docstring for why.
    assert "async def run(" in rendered
    assert "payload: collections.abc.Sequence[weft_kernel.payload.node.Node]" in rendered
    assert "-> weft_kernel.payload.outcome.Outcome[" in rendered
    assert "collections.abc.Sequence[weft_kernel.payload.node.Node]\n]: ..." in rendered
    assert Chunker.__doc__ is not None
    assert Chunker.__doc__.strip().splitlines()[0] in rendered


def test_missing_from_walked_set_reports_an_unwalked_registered_contract() -> None:
    # Arrange
    class _Registered:
        """Stand-in: reported by the registry."""

    # Act
    missing = missing_from_walked_set(
        registered=frozenset({_Registered}), walked=frozenset(), waived=frozenset()
    )

    # Assert
    assert missing == {_Registered}


def test_missing_from_walked_set_respects_a_named_waiver() -> None:
    # Arrange
    class _Registered:
        """Stand-in: reported by the registry, but deliberately waived."""

    # Act
    missing = missing_from_walked_set(
        registered=frozenset({_Registered}),
        walked=frozenset(),
        waived=frozenset({_Registered.__qualname__}),
    )

    # Assert
    assert missing == frozenset()


def test_render_contract_reference_normalises_optional_to_a_native_union() -> None:
    # Arrange
    registry = discover_for_reference()
    contracts = published_contracts(registry)

    # Act
    rendered = render_contract_reference(contracts)

    # Assert — `NodeStore.scan`'s source reads `cursor: Cursor | None = None`, but a
    # `NewType` unioned with `None` evaluates, at class-body time, to
    # `typing.Optional[Cursor]` (see the module's own docstring). The rendered reference
    # reads the way `docs/02-extension-model.md`'s own examples and CLAUDE.md's rule
    # ("native 3.12 type hints") require: `X | None`, and `Optional` never appears.
    assert "cursor: weft_store.contract.Cursor | None = None" in rendered
    assert "Optional" not in rendered


def test_render_contract_reference_raises_for_a_contract_with_no_version() -> None:
    # Arrange
    class _Versionless:
        """Stand-in: satisfies no real contract, carries no `.version`."""

    contracts = (PublishedContract(contract=_Versionless, distributions=frozenset({"weft-test"})),)

    # Act / Assert — a contract the generator cannot describe stops generation rather
    # than being described with an invented `unversioned` placeholder.
    with pytest.raises(ContractNotDescribableError, match="carries no `.version`"):
        render_contract_reference(contracts)


def test_render_contract_reference_raises_for_a_contract_with_no_protocol_attrs() -> None:
    # Arrange
    class _NotAProtocol:
        """Stand-in: has a version, but is not a runtime-checkable Protocol."""

        version = "1.0.0"

    contracts = (PublishedContract(contract=_NotAProtocol, distributions=frozenset({"weft-test"})),)

    # Act / Assert — a contract exposing no `__protocol_attrs__` stops generation rather
    # than being described with an empty `### Methods` section.
    with pytest.raises(ContractNotDescribableError, match="__protocol_attrs__"):
        render_contract_reference(contracts)


def test_a_contracts_declared_data_members_are_documented_beside_its_methods() -> None:
    # Arrange — task 2.7's repair. `weft_prompts.contract.Prompt` is the first contract in
    # this tree with a registered implementation whose protocol membership includes data
    # members (`input_model`, `output_model`) rather than methods alone, and an annotation
    # with no assignment is not an attribute of the class: generation died with a bare
    # `AttributeError` naming `input_model`.
    registry = discover_for_reference()
    contracts = published_contracts(registry)

    # Act
    rendered = render_contract_reference(contracts)

    # Assert — both halves of the contract are documented, because a `Prompt` missing
    # `input_model` fails `isinstance` exactly as surely as one missing `render`.
    assert "### Declared attributes" in rendered
    assert "input_model: typing.ClassVar[type[pydantic.main.BaseModel]]" in rendered
    assert "async def render(" in rendered


def test_render_contract_reference_raises_for_a_contract_with_nothing_to_call() -> None:
    # Arrange
    @runtime_checkable
    class _MarkerOnly(Protocol):
        """Stand-in: a versioned Protocol declaring data and no method at all."""

        version: ClassVar[str] = "1.0.0"
        shape: ClassVar[str]

    contracts = (PublishedContract(contract=_MarkerOnly, distributions=frozenset({"weft-test"})),)

    # Act / Assert — a marker is not something a pack author implements a method of, and
    # this reference documents what they write. Stopping is the loud half of the same rule
    # the repair above is the quiet half of.
    with pytest.raises(ContractNotDescribableError, match="only data members"):
        render_contract_reference(contracts)


# ---------------------------------------------------------------------------
# Task 6.7 — a shipped module may not depend on a tool the distribution never
# declares. `09` section 5.2's failure condition, one layer up from files:
# something load-bearing present in the checkout and absent from the artefact.
# ---------------------------------------------------------------------------


def test_weft_cli_declares_the_formatter_it_shells_out_to() -> None:
    """`ruff` is invoked at generation time by `_ruff_format_markdown`, so it is a dependency.

    It is an **extra** rather than a base dependency: a user who indexes and asks never reaches
    this module, and shipping a formatter to all of them to serve a document generator would be
    the wrong trade. That is the shape `weft-rag[bertscore]` and `weft-otel[otlp]` already
    have. Before task 6.7 it was declared nowhere at all and worked only because the *workspace
    root's* dev group happens to carry `ruff` — invisible to every check in this repository
    until the distribution was installed from its own sdist and the code actually run
    (`docs/lessons.md` L6.24).
    """
    # Arrange
    # `weft-rag` since 2026-09-05: `weft_cli` ships inside it, so the extra it needs is
    # declared there. The property is unchanged — the module that shells out to `ruff` and the
    # manifest that declares it must be the same distribution.
    manifest = Path(__file__).resolve().parents[3] / "packages" / "weft-rag" / "pyproject.toml"

    # Act
    with manifest.open("rb") as handle:
        extras = tomllib.load(handle)["project"].get("optional-dependencies", {})

    # Assert
    assert "reference" in extras, (
        "`weft_cli.contract_reference` shells out to `ruff`, so the distribution that ships "
        "it must declare it. Add a "
        "`[project.optional-dependencies] reference` extra naming it."
    )
    assert any(requirement.startswith("ruff") for requirement in extras["reference"])


def test_a_missing_formatter_is_refused_by_name_rather_than_as_a_subprocess_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absent optional dependency says which extra installs it — `02` section 2's rule that a
    refusal names what was wanted and how to get it, not `CalledProcessError` with a return code.
    """
    # Arrange — an interpreter that certainly cannot run `ruff`, because it is not one. The
    # public renderer is the subject: what a caller must get back is the named refusal, and
    # reaching past it into the private formatter would test the plumbing instead of the
    # promise.
    monkeypatch.setattr(sys, "executable", "/nonexistent/interpreter")

    # Act / Assert
    with pytest.raises(ReferenceFormatterUnavailableError) as caught:
        render_contract_reference(())

    message = str(caught.value)
    assert "ruff" in message
    assert "reference" in message, "the refusal must name the extra that installs it"
