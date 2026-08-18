"""`boolean-retrieval` — a Boolean query parsed to a typed expression tree, with precedence.

Task **2.23**, `docs/build-ledger.md`: "a Boolean query is parsed to an operator expression
with precedence, and an empty conjunction is a visible outcome rather than a union."
`docs/10-technique-catalogue.md` §1.1's own row names the reference's defect precisely: the
decomposition was a flat `(operator, list[str])` (`types.py:75-82`), so any compound query
parsed to `MIXED` and `MIXED` was handled as `OR` — `a AND b OR c` and `a OR b AND c` were the
same fact to the reference's own type. That flat shape is structurally unable to represent the
distinction `10` §1.1 is about; `BoolExpr` below, modelled on `weft_store.contract.Filter`'s
own shape (a discriminating `op`, a leaf payload, and `clauses` for a combinator), is what
makes the distinction *representable* rather than merely correct by luck of implementation.

**The model tokenises; the parser decides what the tokens mean.** `weft_retrieve.prompts.
BooleanParsePrompt` asks a model to split the query into an ordered sequence of terms,
combinator keywords and parentheses — a lexical question with one honest answer regardless of
wording, phrasing or language. `parse_tokens` below is a plain recursive-descent parser over
that sequence, entirely deterministic and entirely untested by any model: standard precedence
(`not` binds tightest, then `and`, then `or` loosest — the same ordering Python's own `not`/
`and`/`or` use, and the one every Boolean query language this catalogue cites shares), with
explicit parentheses overriding it exactly where they appear. This is the fix for "not a split
on whitespace": a naive scan of `a AND b OR c` cannot tell `(a AND b) OR c` from `a AND (b OR
c)`, and neither shape is present in the reference's own flat structure to check against — a real
parser is what gives the sentence "one defined reading" a mechanism, and `tests/unit/
weft_retrieve/test_boolean.py` proves it directly against the parser, with no model in the
loop at all.

**Two plugins, and this module ships one of them.** `BooleanRetrieval` (`QueryTransform`) is
here, alongside `BoolOp`, `BoolExpr` and `BooleanPlan`; `weft_retrieve.fusion.BooleanCombine`
(the `Fuser`) is the plugin that actually evaluates the tree against retrieved candidates —
`.phase2-design.md`'s own task-map row places it there rather than here, beside
`reciprocal-rank-fusion`, because both are the *combining* half of a two-plugin technique and
`weft_retrieve.fusion` is already where a `Ranking` gets assembled from more than one list.
The split itself is `.phase2-design.md`'s own stated reason: "the operator expression is
*data* between them, inspectable and independently testable," and it is what lets `requires`/
`provides` refuse a `boolean-combine` with no `boolean-retrieval` upstream at resolution,
before a single query is ever asked — `tests/unit/weft_retrieve/test_init.py`'s own resolution
test drives that refusal through `weft_kernel.runner.Runner.resolve` directly.

**`BooleanPlan` crosses the retrieve stage through `ext`, which needed a real fix to work.**
`weft_retrieve.payload`'s own module docstring names `ext: ExtMap` as the settled mechanism
for "a strategy needs to pass something downstream" — but neither `vector-top-k` nor
`no-retrieval` used to carry `QuerySet.ext` onto the `Candidates` they produced, so anything a
`QueryTransform` attached upstream of them was silently dropped the moment a retriever ran.
`weft_retrieve.vector_top_k.VectorTopK.run` now forwards it (see that module's own docstring);
this is the first plugin whose worked example actually needed that gap closed rather than
merely being entitled to it in principle.

**Leaf identity crosses the retrieve stage a different way — through `Query.produced_by`, not
`ext`.** Each leaf's derived `Query` is stamped `f"{NAME}#{leaf_index}"`, and that string
survives on `RankedList.query.produced_by` regardless of whether any given retriever forwards
`ext` at all, because carrying the `Query` that was searched is `Retriever`'s own contract
obligation, not an opt-in convenience. `weft_retrieve.fusion.BooleanCombine` reads leaf
identity from there and reads the *tree* — the part `produced_by` cannot carry — from the
forwarded `BooleanPlan`. The two mechanisms exist for different reasons and neither substitutes
for the other. Matching the prefix is keyed off `BooleanPlan.producer`, not off this module's
own `NAME` hardcoded at the reading end — a second `QueryTransform` that provides `BooleanPlan`
under its own registered name is exactly as attributable as this one, because the plan itself,
not `weft_retrieve.boolean`, is what `boolean-combine` trusts for the producer's identity.

**No `xor`.** `10` §1.1's own row on this technique names a distinct reference defect — XOR
"advertised in five user-facing places and implemented in none." The corrected reading this
build takes is not "add XOR and implement it" but "do not advertise what is not backed by real
evaluation semantics": `BoolOp` ships with exactly the leaf marker and the three combinators
`operators`' own default names (`and`, `or`, `not`). A future task that wants XOR adds it with
its own set-arithmetic semantics defined and tested in `weft_retrieve.fusion.BooleanCombine`,
rather than this module reserving a member for it on spec.

**`not` is a real unary operator in the grammar, and a real limitation at evaluation.** The
grammar here accepts `not` wherever a primary expression is legal, because refusing it here
would make the *parser* respect a limitation that belongs to *evaluation* — a corpus is not
enumerable from a set of retrieved hits, so "not x" standing alone, or beside an `or`, has no
bounded complement to compute. `weft_retrieve.fusion.BooleanCombine` is where that refusal
actually lives, named there rather than baked into the shape of the tree.
"""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Failed, Outcome, Produced
from weft_llm.contract import LLM
from weft_llm.payload import OnFailure
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Query, QueryOrigin, QuerySet
from weft_retrieve.prompts import (
    BOOLEAN_PARSE_NAME,
    BooleanQueryRequest,
    BooleanToken,
    BooleanTokenKind,
    BooleanTokens,
)

#: The name this transform is registered and selectable under — see `weft_retrieve.register`.
NAME = "boolean-retrieval"

#: `Query.produced_by`'s own prefix for a leaf this plugin derived — see the module docstring's
#: paragraph on why leaf identity crosses the retrieve stage through this rather than `ext`.
LEAF_PREFIX = f"{NAME}#"


class BoolOp(StrEnum):
    """The vocabulary `BoolExpr.op` names — one leaf kind and the combinators `operators`
    admits. See the module docstring for why there is no `xor` member.
    """

    #: A leaf: one search term, carried in `BoolExpr.term`.
    TERM = "term"
    AND = "and"
    OR = "or"
    NOT = "not"


#: The combinator members alone — what a `BooleanRetrievalConfig.operators` tuple may name.
#: `TERM` is a leaf kind, never something an operator's config restricts or grants.
COMBINATOR_OPS: frozenset[BoolOp] = frozenset({BoolOp.AND, BoolOp.OR, BoolOp.NOT})

_TOKEN_TO_OP: dict[BooleanTokenKind, BoolOp] = {
    BooleanTokenKind.AND: BoolOp.AND,
    BooleanTokenKind.OR: BoolOp.OR,
    BooleanTokenKind.NOT: BoolOp.NOT,
}


class BoolExpr(BaseModel):
    """A parsed Boolean expression — one node of the tree `parse_tokens` builds.

    Modelled on `weft_store.contract.Filter`'s own shape: one discriminating `op`, a leaf
    payload only a leaf carries (`term`, the way `Filter` carries `field`/`value`), and
    `clauses` only a combinator carries. `_shape_matches_op` below is `Filter._shape_matches_op`
    read for this vocabulary instead of that one — the same idea, checked once, regardless of
    who builds a `BoolExpr`.

    `leaf_index` is `None` until `index_leaves` assigns it, left-to-right, depth-first —
    `weft_retrieve.fusion.BooleanCombine` reads it back off `Query.produced_by` to know which
    retrieved candidates answer which leaf of the tree, since `ext` does not reach that far
    (see the module docstring).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: BoolOp
    term: str | None = None
    leaf_index: int | None = None
    clauses: tuple["BoolExpr", ...] = ()

    @model_validator(mode="after")
    def _shape_matches_op(self) -> "BoolExpr":
        if self.op is BoolOp.TERM:
            if self.term is None or not self.term.strip():
                raise ValueError("a 'term' BoolExpr must carry a non-blank 'term'")
            if self.clauses:
                raise ValueError("a 'term' BoolExpr must not carry 'clauses'")
        else:
            if self.term is not None:
                raise ValueError(f"'{self.op.value}' carries no 'term' — only a leaf does")
            if self.op is BoolOp.NOT:
                if len(self.clauses) != 1:
                    raise ValueError("'not' takes exactly one clause")
            elif len(self.clauses) < 2:  # noqa: PLR2004 - "two or more", stated in the message
                raise ValueError(f"'{self.op.value}' takes two or more clauses")
        return self


def leaves(expr: BoolExpr) -> tuple[BoolExpr, ...]:
    """Every leaf in `expr`, left to right — `weft_store.fields.leaves`'s own shape, reused for
    this tree rather than restated: combinators flattened away, leaves kept in encounter order.
    """
    if expr.op is BoolOp.TERM:
        return (expr,)
    return tuple(leaf for clause in expr.clauses for leaf in leaves(clause))


def index_leaves(expr: BoolExpr) -> BoolExpr:
    """`expr`, with every leaf's `leaf_index` assigned 0, 1, 2, … in the order `leaves` visits.

    A separate pass rather than something `parse_tokens` assigns as it goes: assigning indices
    is a fact about the *finished* tree's own left-to-right leaf order, not about the order the
    grammar happens to descend in (which, for a right-recursive `not`, is not the same thing).
    """
    counter = [0]

    def _walk(node: BoolExpr) -> BoolExpr:
        if node.op is BoolOp.TERM:
            indexed = node.model_copy(update={"leaf_index": counter[0]})
            counter[0] += 1
            return indexed
        return node.model_copy(update={"clauses": tuple(_walk(clause) for clause in node.clauses)})

    return _walk(expr)


class BooleanSyntaxError(Exception):
    """Internal control flow for `parse_tokens` alone — never raised past this module's own
    boundary. `parse_tokens` catches every instance and reports it as a `Failed`, the same
    "catch specific exceptions, never let one leak past the seam" rule every cascade-backed
    plugin in this pack already follows for a model's own refusal.
    """


def parse_tokens(
    tokens: tuple[BooleanToken, ...], *, operators: frozenset[BoolOp], max_depth: int
) -> BoolExpr | Failed:
    """`tokens`, parsed into one `BoolExpr` with standard precedence — `not` tightest, then
    `and`, then `or` loosest — or a `Failed` naming exactly what went wrong.

    Three ways this refuses, each named rather than folded into one generic message: a
    combinator token not among `operators` (an operator this document did not enable), a
    malformed sequence (an unmatched parenthesis, a missing operand — `BooleanSyntaxError`),
    and a tree nested deeper than `max_depth` (checked after parsing, against the tree's own
    leaf-to-root distance, which is a fact about the *finished* AST rather than about how the
    grammar happened to recurse getting there — see `_depth`).
    """
    try:
        expr, position = _or_expr(tokens, 0, operators)
    except BooleanSyntaxError as error:
        return Failed(reason=f"'{NAME}' could not parse the tokenised query: {error}")
    if position != len(tokens):
        return Failed(
            reason=(
                f"'{NAME}' parsed a complete expression using {position} of {len(tokens)} "
                f"tokens and stopped — the tokens after that point have no operator "
                f"connecting them to what came before. Check for a missing 'and'/'or' "
                f"between two terms, or an extra ')'."
            )
        )
    depth = _depth(expr)
    if depth > max_depth:
        return Failed(
            reason=(
                f"'{NAME}' parsed a Boolean expression {depth} levels deep, and max_depth is "
                f"{max_depth}. Simplify the query, or raise max_depth in this stage's 'with:' "
                f"block."
            )
        )
    return expr


def _depth(expr: BoolExpr) -> int:
    """0 for a leaf, otherwise one more than its deepest clause — a fact about the tree, not
    about how many grammar rules a parser descended through to build it."""
    if not expr.clauses:
        return 0
    return 1 + max(_depth(clause) for clause in expr.clauses)


def _require_enabled(op: BoolOp, operators: frozenset[BoolOp]) -> None:
    if op not in operators:
        supported = ", ".join(sorted(member.value for member in operators))
        raise BooleanSyntaxError(
            f"'{op.value}' is not among this document's supported operators ({supported})"
        )


def _or_expr(
    tokens: tuple[BooleanToken, ...], position: int, operators: frozenset[BoolOp]
) -> tuple[BoolExpr, int]:
    left, position = _and_expr(tokens, position, operators)
    clauses = [left]
    while position < len(tokens) and tokens[position].kind is BooleanTokenKind.OR:
        _require_enabled(BoolOp.OR, operators)
        right, position = _and_expr(tokens, position + 1, operators)
        clauses.append(right)
    if len(clauses) == 1:
        return clauses[0], position
    return BoolExpr(op=BoolOp.OR, clauses=tuple(clauses)), position


def _and_expr(
    tokens: tuple[BooleanToken, ...], position: int, operators: frozenset[BoolOp]
) -> tuple[BoolExpr, int]:
    left, position = _not_expr(tokens, position, operators)
    clauses = [left]
    while position < len(tokens) and tokens[position].kind is BooleanTokenKind.AND:
        _require_enabled(BoolOp.AND, operators)
        right, position = _not_expr(tokens, position + 1, operators)
        clauses.append(right)
    if len(clauses) == 1:
        return clauses[0], position
    return BoolExpr(op=BoolOp.AND, clauses=tuple(clauses)), position


def _not_expr(
    tokens: tuple[BooleanToken, ...], position: int, operators: frozenset[BoolOp]
) -> tuple[BoolExpr, int]:
    if position < len(tokens) and tokens[position].kind is BooleanTokenKind.NOT:
        _require_enabled(BoolOp.NOT, operators)
        inner, position = _not_expr(tokens, position + 1, operators)
        return BoolExpr(op=BoolOp.NOT, clauses=(inner,)), position
    return _primary(tokens, position, operators)


def _primary(
    tokens: tuple[BooleanToken, ...], position: int, operators: frozenset[BoolOp]
) -> tuple[BoolExpr, int]:
    if position >= len(tokens):
        raise BooleanSyntaxError("expected a term or '(' but the query ended")
    token = tokens[position]
    if token.kind is BooleanTokenKind.TERM:
        return BoolExpr(op=BoolOp.TERM, term=token.text), position + 1
    if token.kind is BooleanTokenKind.LPAREN:
        inner, position = _or_expr(tokens, position + 1, operators)
        if position >= len(tokens) or tokens[position].kind is not BooleanTokenKind.RPAREN:
            raise BooleanSyntaxError("a '(' here has no matching ')'")
        return inner, position + 1
    raise BooleanSyntaxError(f"expected a term or '(' but found '{token.kind.value}'")


class BooleanPlan(ExtModel):
    """The parsed `BoolExpr`, attached to `QuerySet.ext` by `BooleanRetrieval` and carried
    forward to `Candidates.ext` by whichever `Retriever` a document places after it —
    `weft_retrieve.fusion.BooleanCombine` (`requires = (BooleanPlan,)`) is what reads it back
    to evaluate the tree against what was actually retrieved. See the module docstring for why
    the tree needs `ext` to cross that stage even though leaf identity does not.

    `producer` is the registered name of whichever `QueryTransform` built this plan — required,
    never defaulted to this module's own `NAME`, because `requires`/`provides` is what makes a
    second, independently-registered plugin composable with `boolean-combine` in principle
    (any `provides = (BooleanPlan,)` plugin resolves), and that composability is false in
    practice unless leaf attribution is read off *this* field rather than off a hardcoded
    prefix tied to `boolean-retrieval` alone. `BooleanCombine` derives the prefix each leaf's
    `Query.produced_by` must carry as `f"{producer}#{leaf_index}"` from this field — any plugin
    that provides `BooleanPlan` must stamp both the same way `BooleanRetrieval.run` does below.
    """

    __namespace__ = "weft-retrieve"

    expr: BoolExpr
    producer: str = Field(min_length=1)


class BooleanRetrievalConfig(BaseModel):
    """`BooleanRetrieval`'s `with:` config. Every field has a default, per this pack's own
    rule that a Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(default=BOOLEAN_PARSE_NAME, min_length=1)
    role: str = Field(default="parse", min_length=1)
    #: How deep the parsed tree may nest before this stage refuses it — a bound on the
    #: *finished* AST's own leaf-to-root distance, checked once by `parse_tokens` rather than
    #: threaded through the grammar's own recursion. Protects `weft_retrieve.fusion.
    #: BooleanCombine`'s recursive evaluator from a pathologically nested query, the same way
    #: `graded-retrieval`'s `max_graded` bounds a different kind of unbounded cost.
    max_depth: int = Field(default=3, ge=1)
    #: Which combinator keywords this document accepts. Narrowing it (`(AND, OR)`, say) is a
    #: real, useful restriction — a query using a keyword outside this set refuses naming the
    #: supported ones — never an invitation to widen it to a member `BoolOp` does not have;
    #: see the module docstring for why `xor` is not one.
    operators: tuple[BoolOp, ...] = (BoolOp.AND, BoolOp.OR, BoolOp.NOT)
    on_parse_failure: OnFailure = OnFailure.FAIL

    @field_validator("operators", mode="after")
    @classmethod
    def _combinators_only_and_at_least_one(cls, value: tuple[BoolOp, ...]) -> tuple[BoolOp, ...]:
        if not value:
            raise ValueError("'boolean-retrieval' needs at least one operator to parse with")
        if BoolOp.TERM in value:
            raise ValueError(
                "'term' is a leaf kind, never a combinator this config restricts or grants"
            )
        return value


class BooleanRetrieval:
    """Parses a Boolean query into a typed, precedence-respecting expression tree, and emits
    one operand `Query` per leaf. Satisfies `weft_retrieve.contract.QueryTransform`
    structurally.

    Christopher D. Manning, Prabhakar Raghavan, Hinrich Schütze, *Introduction to Information
    Retrieval*, Ch. 1 "Boolean retrieval", Cambridge University Press, 2008 — the technique
    this plugin is named after; `10` §1.1's own row records that no single paper is credited,
    since operational Boolean systems predate any citable one. Chaitanya Malaviya, Peter Shaw,
    Ming-Wei Chang, Kenton Lee, Kristina Toutanova, *QUEST*, ACL 2023, arXiv:2305.11694 — a
    model reading a query and surfacing its Boolean structure, the mechanism
    `weft_retrieve.prompts.BooleanParsePrompt` asks for. See that prompt's own docstring for
    what the model is and is not asked to decide.

    `cost_bound = (1, 1)`: like `hyde` and `step-back`, this transform is not conditioned on
    anything in the payload — there is no "nothing to tokenise" the way a follow-up rewrite has
    nothing to rewrite without history — so the floor and the ceiling are the same number.

    No `keep_question`, unlike every other transform in this pack. A Boolean query's own literal
    text (`cats AND dogs`) is not itself a retrievable question, so there is nothing honest to
    keep it alongside; the derived leaf `Query`s replace `payload.queries` outright.
    """

    config_model: ClassVar[type[BooleanRetrievalConfig]] = BooleanRetrievalConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, 1)
    provides: ClassVar[tuple[type[ExtModel], ...]] = (BooleanPlan,)

    def __init__(self, config: BooleanRetrievalConfig | None = None) -> None:
        self._config = config if config is not None else BooleanRetrievalConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        """`payload.origin`'s text, tokenised, parsed and split into one leaf `Query` per
        operand — plus `BooleanPlan` on the returned `QuerySet.ext`.

        `out.origin == in.origin` holds by construction: the `QuerySet` built below threads
        `payload.origin` through unchanged, the same obligation every query-path plugin in
        this pack carries.
        """
        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        operators = tuple(self._config.operators)
        values = BooleanQueryRequest(
            question=payload.origin.text,
            operators=", ".join(op.value.upper() for op in operators),
        )
        tokenized = await execute(
            llm=llm,
            prompt=prompt,
            values=values,
            output=BooleanTokens,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(tokenized, Produced):
            # `on_parse_failure` has one member today (`FAIL`): relaying the cascade's own
            # outcome *is* failing loudly — see `ContextualQueryRewrite.run`'s own comment on
            # the identical line.
            return tokenized

        parsed = parse_tokens(
            tokenized.value.value.tokens,
            operators=frozenset(operators),
            max_depth=self._config.max_depth,
        )
        if isinstance(parsed, Failed):
            # Same one-member arithmetic as the cascade failure above — a parse this plugin
            # could not make sense of is relayed exactly as it was found, never guessed at.
            return parsed

        indexed = index_leaves(parsed)
        derived = tuple(
            Query(
                text=leaf.term,
                origin=QueryOrigin.DERIVED,
                produced_by=f"{LEAF_PREFIX}{leaf.leaf_index}",
                locale=payload.origin.locale,
            )
            for leaf in leaves(indexed)
            if leaf.term is not None
        )
        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=derived,
                history=payload.history,
                ext={
                    **payload.ext,
                    BooleanPlan.__namespace__: BooleanPlan(expr=indexed, producer=NAME),
                },
            )
        )
