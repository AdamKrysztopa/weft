"""The one question `llm-facts` asks a model, and the shape it asks for back. Ledger **11.7**.

**Authored for Weft, and deliberately not carried.** `01` → Phase 11's *Lift* bullet lists what
this task takes from the owner's own `graph-study` under `NOTICE` case 2 — the non-atomic filter,
in `weft_kg.atomicity`, marked there — and it lists the extraction prompt under **Not lifted**,
*"whatever its origin"*. `CLAUDE.md`'s recoverability test is what decides: a prompt is a
text-shaped asset, so if the string cannot be reconstructed from a written specification then the
text *is* the asset and transcribing it is a copy. The specification this text was written from is
the paragraph below, and the donor's own recorded finding — that a prompt's prohibitions failed as
prose and had to become code — is why the prohibitions here are thin and `weft_kg.atomicity` is
thick.

**What the text has to establish, and each clause is here because leaving it out costs
something.** *An entity is a thing the passage is about*, never a fragment of its sentence, so a
model is told to name things rather than to quote spans. *Both endpoints carry a type*, because
`11.11`'s curated schema constrains exactly those two fields and a corpus extracted without them
cannot be re-read under a schema later. *The predicate is the passage's own claim*, which is the
entire difference between this rung and `index-with-cooccurrence` — a co-occurrence edge says two
names shared a chunk, and this one says what the text asserted about them. *Nothing the passage
does not say*, because a graph is read back as fact and an invented edge is indistinguishable
from a true one once it is a row. And *the passage's own language*, on the same footing every
other prompt in this tree states it: `09` §4's corpus has a Polish subset, and a Polish passage
read through an English instruction is the quiet quality loss locale-keyed prompts exist to
prevent.

**No count of facts is demanded, only a ceiling.** `hypothetical-questions` asks for *exactly*
`${count}` questions because a passage always answers some; a passage may genuinely assert no
relation between two named things, and a prompt that demanded three would get three inventions.
`weft_kg.extraction` enforces the ceiling and counts what it dropped, so an over-delivering model
is a number an operator can read rather than a silent truncation.

**How this prompt is reached, and the one wart in it.** `weft_cli.run_services.
build_index_services` publishes no `StageLookup` on the ingest path — deliberately, so an ingest
plugin cannot depend on the query path — so `llm-facts` cannot resolve a `Prompt` by name the way
`weft_retrieve.rerank` does, and constructs `ExtractFactsPrompt` directly. It is registered
anyway, under this name: this is the stage whose `Disclosure` says a chunk's text leaves the
machine, and this class is the only artefact that says *what* leaves, so hiding it from
`weft plugins list` and from `manual/contract-reference.md` would trade a documented limitation
for an undocumented one. The limitation, stated where a reader meets it: **a `[plugins]` pin on
`extract-facts` changes the listing and does not change what the stage asks.** Closing it needs an
ingest-path equivalent of `StageLookup.build_capability`, which is a `weft_cli` change and
therefore not this pack's to make — `11.5` settled that `weft_kg` costs zero lines outside itself.
"""

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_prompts.typed_prompt import PromptText, TypedPrompt

#: The name this prompt is registered and selectable under — see `weft_kg.register`.
EXTRACT_FACTS_NAME = "extract-facts"


class ExtractFactsRequest(BaseModel):
    """What `extract-facts` renders: one passage, and the most facts it is worth writing.

    One passage, never a numbered batch — `weft_index.hypothetical_questions`' own argument
    applies unchanged: batching chunks would make the model's attention to any one passage a
    function of how many chunks happened to land in this run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passage: str
    max_facts: int = Field(ge=1)


class ProposedFact(BaseModel):
    """One triple a model offered, before anything has judged it.

    **Every field is a plain `str` with no length bound, and that is the point.** A bound here
    would make one blank field fail the whole completion's validation, so the cascade would step
    down a tier and finally report a `Failed` naming none of the rows — and a candidate that
    disappears into a tier change is a candidate nothing counts. `weft_kg.extraction` checks the
    fields itself and counts a blank one under `DropReason.INCOMPLETE_ROW`, which is the repair
    for the donor's own recorded gap: that module skips a malformed row and says so in a comment,
    *"not counted as dropped"*.

    `source`/`target`/`predicate` rather than subject/object, because `weft_kg.payload.
    CooccurrenceEdge` already spells an edge that way and one pack should not hold two
    vocabularies for one shape.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    source_type: str
    predicate: str
    target: str
    target_type: str


class ProposedFacts(BaseModel):
    """Everything one call offered. The output model `weft_prompts.cascade.execute` is asked for.

    A wrapping object rather than a bare array because tier 1 hands this model's JSON schema to a
    vendor that checks it, and a top-level array is the shape vendors support least uniformly —
    `weft_retrieve.prompts.PassageRelevance` wraps its own list for the same reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: tuple[ProposedFact, ...] = ()


class ExtractFactsPrompt(TypedPrompt):
    """Ask a model for the relations one passage states, as typed triples, in its own language.

    The English text is the fallback every locale degrades to; the Polish one exists because the
    corpus this engine is measured against has a Polish subset (`09` §4). A locale nobody
    translated degrades the *language*, which a reader can see, never the answer, which they
    cannot — `TypedPrompt`'s own rule.
    """

    name: ClassVar[str] = EXTRACT_FACTS_NAME
    input_model: ClassVar[type[BaseModel]] = ExtractFactsRequest
    output_model: ClassVar[type[BaseModel] | None] = ProposedFacts
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You read one passage and report the relations it states between things it "
                "names. A thing is a person, an organisation, a place, a method, a dataset, a "
                "measure or any other entity the passage is about — never a clause, an "
                "equation, a citation, or a pointer to the document's own sections, figures "
                "or tables. Report only what the passage itself asserts: a relation you infer "
                "from what you already know is not in the passage, and once it is stored "
                "nothing can tell it apart from one that is."
            ),
            user=(
                "Passage:\n${passage}\n\n"
                "Report the relations this passage states, at most ${max_facts} of them, "
                "keeping the ones the passage makes most of. For each, give the two things "
                "related, a short type for each of them, and the relation itself as the "
                "passage puts it. Name each thing the way the passage names it, in the "
                "passage's own language, in as few words as it takes. If the passage states "
                "no relation between things it names, report none."
            ),
        ),
        "pl": PromptText(
            system=(
                "Czytasz jeden fragment tekstu i wypisujesz relacje, które ten fragment "
                "stwierdza pomiędzy nazwanymi w nim rzeczami. Rzecz to osoba, organizacja, "
                "miejsce, metoda, zbiór danych, miara lub dowolny inny byt, o którym fragment "
                "mówi — nigdy zdanie podrzędne, wzór, przypis bibliograficzny ani odsyłacz do "
                "sekcji, rysunku czy tabeli w dokumencie. Wypisuj wyłącznie to, co fragment "
                "sam stwierdza: relacja, którą wywnioskujesz z własnej wiedzy, nie znajduje "
                "się we fragmencie, a po zapisaniu nic już nie odróżni jej od prawdziwej."
            ),
            user=(
                "Fragment:\n${passage}\n\n"
                "Wypisz relacje stwierdzone przez ten fragment, najwyżej ${max_facts}, "
                "zachowując te, którym fragment poświęca najwięcej miejsca. Dla każdej podaj "
                "dwie powiązane rzeczy, krótki typ każdej z nich oraz samą relację tak, jak "
                "ujmuje ją fragment. Nazywaj każdą rzecz tak, jak nazywa ją fragment, w jego "
                "własnym języku, możliwie najkrócej. Jeśli fragment nie stwierdza żadnej "
                "relacji między nazwanymi rzeczami, nie wypisuj żadnej."
            ),
        ),
    }


__all__ = [
    "EXTRACT_FACTS_NAME",
    "ExtractFactsPrompt",
    "ExtractFactsRequest",
    "ProposedFact",
    "ProposedFacts",
]
