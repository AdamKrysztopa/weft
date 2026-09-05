"""A loop-breaker for a model that gets stuck mid-stream — never a hallucination judgment.

Task **3.10**, `01` → Phase 3 **Lift**: the one lift this phase makes. What earns it that
status rather than a fresh design is that its thresholds are *measured* tuning, not a guess —
worked failing and passing examples back every constant below, and each field's own comment
says which example justifies its particular value, not only what the value is.

**What this is.** A small local model asked to keep generating sometimes settles into
repeating the same span of text forever — a known failure mode of greedy decoding once a
model's own output starts dominating its context. Left unstopped, `weft ask --stream` would
fill a reader's terminal with the same sentence for as long as the provider's own token limit
allows. This module answers one question — "does the answer generated *so far* look like it
has settled into a loop?" — cheaply enough to ask on every token, and separately answers "is
what looks like a loop actually a legitimate markdown table?", because a table's rows are
*supposed* to repeat a shape (`| --- | --- |`) and streaming a table one line at a time would
otherwise look identical to a degenerate loop until the whole table has arrived.

**This is not "hallucination detection" and must never be named or documented as such** —
`01`'s Lift note is explicit, and the distinction is real: this module has no opinion on
whether generated text is *true*. It only recognises text that stopped saying anything new.

**The cumulative-text contract — read this before calling `detect_generation_loop`.** The
guard must be handed the **whole answer generated so far on every call, never only the
newest delta**. It inspects the *tail* of the text it is given, so a caller that hands it only
the latest chunk can never see a repeat that spans more than one chunk — the guard would never
fire regardless of how badly a model loops. The cost of the correct contract is real and is
why several constants below exist at all: comparing an ever-growing string against itself on
every token is `O(n)` per call and `O(n²)` across a whole stream, so `min_period`, the
`min_text_length` floor and `fuzzy_step` all exist specifically to keep that `O(n²)` bounded —
none of the three is decoration. `weft_llm.client.LLMClient.complete` is the one call site in
this tree, and it already accumulates every provider chunk into a list before this module ever
sees it (task 3.6's own accumulation loop), which is exactly the shape this contract needs and
the reason the guard attaches there rather than inside a `TokenSink`.

**Ordering, stated rather than nested.** The table check must run — and be seen to run —
*before* either repetition pass. `_looks_like_table`'s own threshold is deliberately
aggressive — a single table-like line is enough — because a table streamed one row at a
time is legitimately repetitive until the last row arrives; running the
repetition passes first would cut a streamed table off mid-render. `detect_generation_loop`
below calls the two as two separate top-level functions with the table check first, rather
than nesting the repetition check inside the table check's negative branch — the ordering
constraint is then a fact a reader of `detect_generation_loop`'s body sees in three lines,
not a fact implied by how deeply one function calls into another.

**The similarity measure is deliberately cheap.** `_positional_similarity` trades exactness
for speed: positional character equality over the shorter of two windows, checked once per
token, rather than true edit distance. It fires as a loop only alongside low n-gram
diversity: a long answer that legitimately reuses
a phrase ("as mentioned in the sources...") has high similarity between two windows but stays
internally diverse, so the diversity half of the test is what keeps ordinary prose from
tripping this guard — the true/false pair every test in the mirroring test module reproduces.
"""

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field


#: `[llm.loop_guard]` — every constant this module needs, all parameterisable rather than
#: hard-coded, with the measured values kept as defaults because re-deriving them against
#: Weft's own evaluation harness is Phase 4's job, not this task's — see each field's own
#: comment for why its particular value was chosen, not only what it is.
class LoopGuardConfig(BaseModel):
    """How aggressively `detect_generation_loop` looks for a repeating tail, and how it tells
    a repeating markdown table apart from one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The shortest repeated span worth flagging. Raised from a smaller value that also proved
    #: too low, because a period that short matches ordinary short phrases repeating in normal
    #: prose — "the the", "and and" from a stutter mid-sentence — too often to be worth
    #: interrupting a stream for.
    min_period: int = Field(default=50, ge=1)
    #: The longest repeated span the fuzzy pass below will search for. A model stuck in a
    #: multi-paragraph loop is still a loop, but the search cost of every period up to an
    #: unbounded ceiling would defeat the point of a guard meant to run on every token.
    max_period: int = Field(default=500, ge=1)
    #: How alike two equal-length windows of the tail must be, on the cheap positional measure
    #: below, before a period is even a candidate. High on purpose: this alone is not the
    #: guard, only half of it — see `diversity_threshold`.
    similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    #: How internally repetitive the two-period window being compared must be — at or below
    #: this fraction of its own character n-grams being unique — before the guard actually
    #: fires. A worked pair is why both thresholds are required together: "Hello world.
    #: Hello world. Hello world." is high-similarity *and*
    #: low-diversity (fires, because the whole window is one short phrase repeating); a long
    #: answer that reuses "as mentioned in the sources..." once, between two otherwise-different
    #: paragraphs, has nowhere near this much of its surrounding window built from one repeated
    #: span, so its diversity stays high (does not fire).
    diversity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    #: Below this many characters, nothing is checked at all. Two reasons,
    #: not one: a short answer has no room for a period as long as `min_period` twice over, and
    #: skipping the check entirely below this floor is what keeps the per-token cost near-zero
    #: for the common case of a short answer that never loops.
    min_text_length: int = Field(default=100, ge=0)
    #: Above `max(min_period, 100)` characters, candidate periods are sampled every this many
    #: characters rather than walked one at a time — the other half of keeping the
    #: cumulative-text contract's `O(n²)` bounded.
    #: A period this sampling skips past would only be missed by up to `fuzzy_step - 1`
    #: characters, which the next token's check catches.
    fuzzy_step: int = Field(default=10, ge=1)
    #: The character n-gram length the diversity measure counts over. Higher than the
    #: function-level default a general-purpose diversity helper would reasonably carry (3,
    #: which is too short to distinguish "the cat sat" from three-word loops of ordinary
    #: prose) — both places this module calls the diversity measure pass this value
    #: explicitly rather than relying on a shared default.
    ngram_size: int = Field(default=5, ge=1)
    #: How far back, in characters, the table detector looks.
    table_lookback_chars: int = Field(default=500, ge=0)
    #: How far back, in lines, the table detector looks — a second, tighter
    #: bound alongside the character one, since a handful of very long lines could otherwise
    #: exhaust the character budget without ever reaching an actual table row.
    table_lookback_lines: int = Field(default=10, ge=0)
    #: How many table-like lines in the lookback window are enough to call it a table.
    #: Deliberately `1`, not `2`: during streaming, a table is being generated one row at a
    #: time, and a line starting with `|` and carrying more than one pipe is almost always a
    #: table row even before its closing pipe has arrived — waiting for a second row before
    #: believing it risks the repetition guard firing on the first row alone.
    table_line_threshold: int = Field(default=1, ge=1)
    #: A line whose characters are less than this fraction alphanumeric reads as formatting
    #: rather than prose — the worked examples this module's own tests reproduce: a
    #: `|---|---|` separator is roughly a tenth alphanumeric, a `====` rule is none of it, and
    #: an ordinary sentence is well above nine tenths.
    alphanumeric_ratio_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


_DEFAULT_CONFIG = LoopGuardConfig()


def detect_generation_loop(
    accumulated_text: str, *, config: LoopGuardConfig = _DEFAULT_CONFIG
) -> bool:
    """Whether `accumulated_text` has settled into a repeating span worth stopping for.

    **`accumulated_text` must be the whole answer generated so far, never a delta** — see the
    module docstring's cumulative-text contract. Below `config.min_text_length` this always
    returns `False` without looking further; above it, the table check runs before either
    repetition pass, and a text this module reads as a table never reaches them regardless of
    how repetitive its rows look — see the module docstring's ordering note.
    """
    if len(accumulated_text) <= config.min_text_length:
        return False
    if _looks_like_table(accumulated_text, config=config):
        return False
    return _has_repeating_tail(accumulated_text, config=config)


def _looks_like_table(text: str, *, config: LoopGuardConfig) -> bool:
    """Whether the tail of `text` reads as a markdown table being generated.

    Aggressive by design (see `LoopGuardConfig.table_line_threshold`'s own comment): one
    pipe-carrying or formatting-heavy line in the lookback window is enough, and a line is
    never required to end with `|` — mid-stream, the newest line in the window may simply not
    have its closing pipe yet.
    """
    window = text[-config.table_lookback_chars :]
    lines = [line for line in window.splitlines()[-config.table_lookback_lines :] if line.strip()]
    if not lines:
        return False
    pipe_lines = sum(1 for line in lines if line.strip().startswith("|") and line.count("|") >= 2)
    formatting_lines = sum(1 for line in lines if _is_formatting_line(line, config=config))
    return (
        pipe_lines >= config.table_line_threshold or formatting_lines >= config.table_line_threshold
    )


def _is_formatting_line(line: str, *, config: LoopGuardConfig) -> bool:
    """A line that reads as table syntax (a separator rule, a border) rather than prose."""
    return _alphanumeric_ratio(line) < config.alphanumeric_ratio_threshold


def _alphanumeric_ratio(line: str) -> float:
    stripped = line.strip()
    if not stripped:
        return 1.0  # an empty line is not "formatting" — it simply carries no evidence.
    alphanumeric = sum(1 for character in stripped if character.isalnum())
    return alphanumeric / len(stripped)


def _has_repeating_tail(text: str, *, config: LoopGuardConfig) -> bool:
    """Whether some period from `config.min_period` up to `config.max_period` shows the tail
    of `text` repeating itself: high positional similarity between two consecutive windows of
    that length, and low character-n-gram diversity across the two of them combined — both,
    per the module docstring's worked pair, or ordinary prose that reuses a phrase once would
    trip this too.
    """
    for period in _candidate_periods(config):
        window_length = period * 2
        if len(text) < window_length:
            continue
        window = text[-window_length:]
        earlier, recent = window[:period], window[period:]
        if _positional_similarity(earlier, recent) < config.similarity_threshold:
            continue
        if _ngram_diversity(window, n=config.ngram_size) <= config.diversity_threshold:
            return True
    return False


def _candidate_periods(config: LoopGuardConfig) -> Iterator[int]:
    """Every period `_has_repeating_tail` checks: walked one at a time from `min_period` up to
    the fuzzy floor, then sampled every `config.fuzzy_step` characters above it — see
    `LoopGuardConfig.fuzzy_step`'s own comment for why the sampled half is what keeps the
    cumulative-text contract affordable. Below the floor a full walk is still cheap, because
    the floor itself is small; skipping straight to a stepped search for the whole range would
    let a short repeating period slip between two sampled points.
    """
    fuzzy_floor = max(config.min_period, config.min_text_length)
    yield from range(config.min_period, min(fuzzy_floor, config.max_period + 1))
    yield from range(fuzzy_floor, config.max_period + 1, config.fuzzy_step)


def _positional_similarity(earlier: str, recent: str) -> float:
    """A cheap stand-in for edit distance: the fraction of positions where two equal-length
    windows agree — exact character alignment rather than an alignment-tolerant distance,
    because this runs once per token.
    """
    if not earlier or not recent:
        return 0.0
    matches = sum(1 for left, right in zip(earlier, recent, strict=True) if left == right)
    return matches / len(recent)


def _ngram_diversity(text: str, *, n: int = 3) -> float:
    """The fraction of `text`'s length-`n` character windows that are unique. `1.0` means every
    window differs from every other; near `0.0` means the text is one span repeating. The
    default of `3` is a general-purpose length for a helper with no context about what it is
    measuring; `_has_repeating_tail` always passes `config.ngram_size` (`5`) explicitly instead
    of relying on it, because a loop guard needs a coarser window than a generic caller would.
    """
    if len(text) <= n:
        return 1.0  # too short to have a repeated internal window — never itself a reason to flag.
    grams = [text[index : index + n] for index in range(len(text) - n + 1)]
    return len(set(grams)) / len(grams)


__all__ = ["LoopGuardConfig", "detect_generation_loop"]
