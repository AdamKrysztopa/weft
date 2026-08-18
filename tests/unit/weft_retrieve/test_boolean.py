"""Unit tests for `weft_retrieve.boolean`.

Mirrors `packages/weft-retrieve/src/weft_retrieve/boolean.py`. Ledger **2.23**: "a Boolean
query is parsed to an operator expression with precedence, and an empty conjunction is a
visible outcome rather than a union." This module covers only the first half — `BoolExpr`,
`parse_tokens` and `BooleanRetrieval`; the second half, `BooleanCombine`, is tested in
`test_fusion.py` beside `single-list` and `reciprocal-rank-fusion`, the same module split
`.phase2-design.md`'s own task map places the implementations in.

**`parse_tokens` is tested directly, with no model anywhere in the loop.** The ledger line's
own claim — "a real parse to a typed expression tree, not a split on whitespace: `a AND b OR
c` must have one defined reading" — is a property of this pure function alone: precedence,
paren overrides and operator refusal are all deterministic given a token sequence, so proving
them does not need `BooleanRetrieval`, a cascade, or a stub LLM at all.

`out.origin == in.origin` is asserted in every test that produces a `QuerySet`, the same
obligation every query-path plugin's own test module in this pack already carries.
"""

from collections.abc import Mapping

import pytest

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, Outcome, Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.boolean import (
    NAME,
    BooleanPlan,
    BooleanRetrieval,
    BooleanRetrievalConfig,
    BoolExpr,
    BoolOp,
    index_leaves,
    leaves,
    parse_tokens,
)
from weft_retrieve.contract import QueryTransform, StageLookup
from weft_retrieve.payload import Query, QuerySet
from weft_retrieve.prompts import (
    BOOLEAN_PARSE_NAME,
    BooleanParsePrompt,
    BooleanToken,
    BooleanTokenKind,
)

_TERM = BooleanTokenKind.TERM
_AND = BooleanTokenKind.AND
_OR = BooleanTokenKind.OR
_NOT = BooleanTokenKind.NOT
_LPAREN = BooleanTokenKind.LPAREN
_RPAREN = BooleanTokenKind.RPAREN

_ALL_OPS = frozenset({BoolOp.AND, BoolOp.OR, BoolOp.NOT})


def _term(text: str) -> BooleanToken:
    return BooleanToken(kind=_TERM, text=text)


def _tok(kind: BooleanTokenKind) -> BooleanToken:
    return BooleanToken(kind=kind)


# --- `parse_tokens`: precedence, parentheses, and refusal — no model involved. -------------


def test_and_binds_tighter_than_or_giving_one_defined_reading() -> None:
    # Arrange — "a AND b OR c" must parse as (a AND b) OR c, never a AND (b OR c). This is
    # the ledger line's own worked example, proven against the parser directly.
    tokens = (_term("a"), _tok(_AND), _term("b"), _tok(_OR), _term("c"))

    # Act
    parsed = parse_tokens(tokens, operators=_ALL_OPS, max_depth=3)

    # Assert
    assert isinstance(parsed, BoolExpr)
    assert parsed.op is BoolOp.OR
    assert len(parsed.clauses) == 2
    left, right = parsed.clauses
    assert left.op is BoolOp.AND
    assert [clause.term for clause in left.clauses] == ["a", "b"]
    assert right == BoolExpr(op=BoolOp.TERM, term="c")


def test_explicit_parentheses_override_the_default_precedence() -> None:
    # Arrange — the edge case: "a AND (b OR c)" is a genuinely different tree from the
    # unparenthesised reading above, and the parser must tell the two apart.
    tokens = (
        _term("a"),
        _tok(_AND),
        _tok(_LPAREN),
        _term("b"),
        _tok(_OR),
        _term("c"),
        _tok(_RPAREN),
    )

    # Act
    parsed = parse_tokens(tokens, operators=_ALL_OPS, max_depth=3)

    # Assert
    assert isinstance(parsed, BoolExpr)
    assert parsed.op is BoolOp.AND
    left, right = parsed.clauses
    assert left == BoolExpr(op=BoolOp.TERM, term="a")
    assert right.op is BoolOp.OR
    assert [clause.term for clause in right.clauses] == ["b", "c"]


def test_not_binds_to_the_immediately_following_term() -> None:
    # Arrange — "a AND NOT b" is a well-defined AND with a negated second operand.
    tokens = (_term("a"), _tok(_AND), _tok(_NOT), _term("b"))

    # Act
    parsed = parse_tokens(tokens, operators=_ALL_OPS, max_depth=3)

    # Assert
    assert isinstance(parsed, BoolExpr)
    assert parsed.op is BoolOp.AND
    positive, negated = parsed.clauses
    assert positive == BoolExpr(op=BoolOp.TERM, term="a")
    assert negated.op is BoolOp.NOT
    assert negated.clauses == (BoolExpr(op=BoolOp.TERM, term="b"),)


def test_an_operator_not_in_the_configured_set_is_refused_naming_the_supported_ones() -> None:
    # Arrange — the error case: a document that narrowed `operators` to (AND, NOT) sees a
    # query using `OR`, which this parser must refuse rather than silently accept.
    tokens = (_term("a"), _tok(_OR), _term("b"))

    # Act
    parsed = parse_tokens(tokens, operators=frozenset({BoolOp.AND, BoolOp.NOT}), max_depth=3)

    # Assert
    assert isinstance(parsed, Failed)
    assert "or" in parsed.reason
    assert "and" in parsed.reason and "not" in parsed.reason


def test_an_unmatched_parenthesis_is_refused_rather_than_silently_dropped() -> None:
    # Act / Assert
    parsed = parse_tokens((_tok(_LPAREN), _term("a")), operators=_ALL_OPS, max_depth=3)
    assert isinstance(parsed, Failed)
    assert "')'" in parsed.reason


def test_two_terms_with_no_operator_between_them_is_refused() -> None:
    # Act / Assert — "a b" is not "a AND b" by silent inference; a missing connective is a
    # malformed query, not a default this parser picks for the caller.
    parsed = parse_tokens((_term("a"), _term("b")), operators=_ALL_OPS, max_depth=3)
    assert isinstance(parsed, Failed)


def test_a_tree_deeper_than_max_depth_is_refused() -> None:
    # Arrange — three levels of explicit nesting, asked to fit in a depth of one.
    tokens = (
        _tok(_LPAREN),
        _tok(_LPAREN),
        _term("a"),
        _tok(_OR),
        _term("b"),
        _tok(_RPAREN),
        _tok(_OR),
        _term("c"),
        _tok(_RPAREN),
    )

    # Act
    parsed = parse_tokens(tokens, operators=_ALL_OPS, max_depth=1)

    # Assert
    assert isinstance(parsed, Failed)
    assert "max_depth" in parsed.reason


def test_leaves_and_index_leaves_visit_left_to_right() -> None:
    # Arrange
    tokens = (_term("a"), _tok(_AND), _term("b"), _tok(_OR), _term("c"))
    parsed = parse_tokens(tokens, operators=_ALL_OPS, max_depth=3)
    assert isinstance(parsed, BoolExpr)

    # Act
    indexed = index_leaves(parsed)

    # Assert
    ordered = leaves(indexed)
    assert [leaf.term for leaf in ordered] == ["a", "b", "c"]
    assert [leaf.leaf_index for leaf in ordered] == [0, 1, 2]


def test_a_term_bool_expr_must_carry_a_non_blank_term() -> None:
    # Act / Assert — `BoolExpr`'s own shape validator, modelled on `Filter`'s.
    with pytest.raises(ValueError, match="term"):
        BoolExpr(op=BoolOp.TERM, term=None)


def test_an_and_bool_expr_needs_two_or_more_clauses() -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="two or more"):
        BoolExpr(op=BoolOp.AND, clauses=(BoolExpr(op=BoolOp.TERM, term="a"),))


# --- `BooleanRetrieval`: tokenise through the cascade, parse, emit one Query per leaf. ------


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script — same shape as `test_transforms.
    py`'s own, reused rather than restated."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, ctx
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompts — same shape as `test_transforms.py`'s."""

    def __init__(self, prompts: Mapping[str, object]) -> None:
        self._prompts = prompts

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset(self._prompts)

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("this plugin resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        del contract, config
        return self._prompts[name]


class _RefusingLLM:
    """An `LLM` that never answers usably — used for the parse-failure edge case, where the
    cascade itself is what fails rather than `parse_tokens`."""

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("tier 1 is unavailable on this stub")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        return Produced(value=Completion(text="I cannot help with that.", model="stub-model"))

    async def close(self) -> None: ...


def _lookup() -> _StubLookup:
    return _StubLookup({BOOLEAN_PARSE_NAME: BooleanParsePrompt()})


def _services(llm: object, lookup: object | None = None) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, lookup if lookup is not None else _lookup())
    return services


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


_TOKENS_REPLY = (
    '{"tokens": ['
    '{"kind": "term", "text": "cats"}, '
    '{"kind": "and", "text": ""}, '
    '{"kind": "term", "text": "dogs"}'
    "]}"
)


async def test_a_boolean_query_is_tokenised_parsed_and_split_into_one_query_per_leaf() -> None:
    # Arrange
    asked = Query(text="cats AND dogs")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM([_TOKENS_REPLY])

    # Act
    outcome = await BooleanRetrieval().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    result: QuerySet = outcome.value
    assert result.origin == asked
    assert [query.text for query in result.queries] == ["cats", "dogs"]
    assert [query.produced_by for query in result.queries] == [
        f"{NAME}#0",
        f"{NAME}#1",
    ]
    plan = result.ext[BooleanPlan.__namespace__]
    assert isinstance(plan, BooleanPlan)
    assert plan.expr.op is BoolOp.AND
    assert plan.producer == NAME
    assert [leaf.term for leaf in leaves(plan.expr)] == ["cats", "dogs"]


async def test_a_cascade_that_cannot_tokenise_is_relayed_never_papered_over() -> None:
    # Arrange — the edge case: `on_parse_failure` has one member (`FAIL`) today, so a cascade
    # that stepped down through all three tiers and still could not answer is relayed exactly
    # as it answered, the same "on_failure has one member" arithmetic every sibling transform
    # in this pack already uses.
    asked = Query(text="something that cannot be tokenised")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _RefusingLLM()

    # Act
    outcome = await BooleanRetrieval().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Failed)


async def test_a_syntactically_malformed_tokenisation_is_refused_by_the_parser() -> None:
    # Arrange — the error case: the cascade answers usably, but the tokens it answered with
    # do not parse (two terms, no operator between them) — `parse_tokens`'s own refusal,
    # relayed rather than silently accepted.
    bad_reply = '{"tokens": [{"kind": "term", "text": "a"}, {"kind": "term", "text": "b"}]}'
    asked = Query(text="a b")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM([bad_reply])

    # Act
    outcome = await BooleanRetrieval().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Failed)


async def test_a_query_using_a_disabled_operator_is_refused_naming_the_supported_set() -> None:
    # Arrange — `operators` narrowed away from the default, exercised end to end through the
    # plugin rather than only through `parse_tokens` directly.
    or_reply = (
        '{"tokens": ['
        '{"kind": "term", "text": "a"}, '
        '{"kind": "or", "text": ""}, '
        '{"kind": "term", "text": "b"}'
        "]}"
    )
    asked = Query(text="a OR b")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM([or_reply])
    config = BooleanRetrievalConfig(operators=(BoolOp.AND, BoolOp.NOT))

    # Act
    outcome = await BooleanRetrieval(config).run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Failed)
    assert "or" in outcome.reason


async def test_driving_boolean_retrieval_through_the_seam_produces_a_query_set() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    asked = Query(text="cats AND dogs")
    payload = QuerySet(origin=asked, queries=(asked,))
    llm = _StubLLM([_TOKENS_REPLY])
    transform = BooleanRetrieval()
    wrapped = wrap(
        transform.run, distribution="weft-retrieve", contract="QueryTransform", plugin=NAME
    )

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert [query.text for query in outcome.value.queries] == ["cats", "dogs"]
    assert isinstance(transform, QueryTransform)


def test_config_operators_may_not_include_term_and_may_not_be_empty() -> None:
    # Act / Assert — `term` is a leaf kind, not a combinator this config restricts.
    with pytest.raises(ValueError, match="leaf"):
        BooleanRetrievalConfig(operators=(BoolOp.TERM,))
    with pytest.raises(ValueError, match="at least one"):
        BooleanRetrievalConfig(operators=())


def test_the_declared_cost_bound_is_one_one() -> None:
    # Act / Assert — like `hyde` and `step-back`, this transform is not conditioned on
    # anything in the payload, so the floor and the ceiling are the same number.
    assert BooleanRetrieval.cost_bound == (1, 1)
    assert BooleanRetrieval.provides == (BooleanPlan,)
