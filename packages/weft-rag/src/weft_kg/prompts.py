"""The two questions this pack asks a model, and the shape each asks for back.

Ledger **11.7** wrote the first: the one `llm-facts` asks per chunk, about a passage's own text.
Ledger **11.9** adds the second: the one `GraphStore.reconcile` asks per ambiguous pair, when
`weft_kg.adjudication`'s cheap band abstains and the expensive pass has to actually decide. Both
are reached the same way and carry the same stated wart — see `AdjudicateEntitiesPrompt`'s own
docstring below for it stated where a reader of *that* class meets it.

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

**Ledger `11.11` adds a third, optional clause: `render_allowed` and `ExtractFactsRequest.allowed`,
below.** When a curated schema is active, `weft_kg.extraction` hands this prompt the admitted
`(source_type, predicate, target_type)` arrangements as well as constraining what it keeps — the
"constrain and verify" pair that module's own docstring names, because verifying alone spends a
call to throw most of a wrong answer away and constraining alone trusts a model that may not
comply. The clause is data, not a rule this file states as prose, so it lives beside the templates
that carry it rather than inside `weft_kg.schema`, which has no model call to shape.

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
from enum import StrEnum
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field

from weft_kg.schema import GraphSchema
from weft_prompts.typed_prompt import PromptText, TypedPrompt

#: The name this prompt is registered and selectable under — see `weft_kg.register`.
EXTRACT_FACTS_NAME = "extract-facts"

#: The name the reconcile pass's prompt is registered and selectable under — see
#: `AdjudicateEntitiesPrompt`'s own docstring for how it is reached and the wart it carries.
ADJUDICATE_ENTITIES_NAME = "adjudicate-entities"


class ExtractFactsRequest(BaseModel):
    """What `extract-facts` renders: one passage, and the most facts it is worth writing.

    One passage, never a numbered batch — `weft_index.hypothetical_questions`' own argument
    applies unchanged: batching chunks would make the model's attention to any one passage a
    function of how many chunks happened to land in this run.

    **`allowed`, ledger `11.11` — the corpus's active curated schema, or nothing.** `render_allowed`
    below builds the whole value, introductory clause included, in the caller's own language; the
    templates append `${allowed}` directly onto their own closing sentence with no character
    between them, so an empty value — no schema active, today's ordinary case — leaves the
    rendered prompt byte-identical to what it was before this field existed. A fixed sentence
    written into the template itself, present whether or not a schema is active, would not have
    that property; putting the whole clause inside the value is what buys it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passage: str
    max_facts: int = Field(ge=1)
    allowed: str = ""


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
                "no relation between things it names, report none.${allowed}"
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
                "relacji między nazwanymi rzeczami, nie wypisuj żadnej.${allowed}"
            ),
        ),
    }


#: `render_allowed`'s own prose, per locale — the clause `ExtractFactsRequest.allowed` carries
#: when a curated schema is active. `{listing}` is `str.format`-substituted (never `${...}`,
#: which is `weft_prompts.template`'s own placeholder syntax and would collide with it), each
#: line one admitted `(source_type, predicate, target_type)` arrangement. Written as real prose
#: in both languages, on `ExtractFactsPrompt.texts`'s own register, rather than one English
#: sentence reused for both — the same argument that text's own module docstring makes for
#: `ExtractFactsPrompt` itself.
_ALLOWED_CLAUSE: Final[Mapping[str, str]] = {
    "en": (
        "\n\nThis corpus admits only the following arrangements of two named things and the "
        "relation between them. Report a relation only when its two types and its predicate "
        "together match one of these exactly; say nothing about an arrangement this list does "
        "not admit, even if the passage suggests one:\n{listing}"
    ),
    "pl": (
        "\n\nTen korpus dopuszcza wyłącznie następujące układy dwóch nazwanych rzeczy i relacji "
        "między nimi. Podawaj relację tylko wtedy, gdy jej oba typy i predykat razem dokładnie "
        "odpowiadają jednemu z poniższych układów; nie pisz o układzie, którego ta lista nie "
        "dopuszcza, nawet jeśli sugeruje go fragment:\n{listing}"
    ),
}


def render_allowed(schema: GraphSchema | None, *, locale: str) -> str:
    """`ExtractFactsRequest.allowed`'s value: `""` with no schema active, otherwise the schema's
    admitted `(source_type, predicate, target_type)` arrangements as one locale-appropriate
    clause, in `locale`'s own text — exact match, then its primary subtag, then `en`, the
    identical three-step fallback `TypedPrompt._text_for` already uses for the surrounding
    template, so the clause and the sentence it is appended to never disagree about which
    language they are answering in.
    """
    if schema is None:
        return ""
    listing = "\n".join(
        f"- {relation.source_type} {relation.predicate} {relation.target_type}"
        for relation in schema.relations
    )
    text = (
        _ALLOWED_CLAUSE.get(locale)
        or _ALLOWED_CLAUSE.get(locale.partition("-")[0])
        or _ALLOWED_CLAUSE["en"]
    )
    return text.format(listing=listing)


class SameEntity(StrEnum):
    """A model's verdict on one pair of surface forms — `Enum` over `Literal`, this project's rule
    for a string constant, and the third member is the one the whole prompt exists to make safe to
    give: a wrong `YES` merges two entities irreversibly, and a wrong `NO` is a graph that quietly
    stays split, so `UNSURE` is a real answer rather than a state the schema merely tolerates.
    """

    YES = "yes"
    NO = "no"
    UNSURE = "unsure"


class AdjudicateEntitiesRequest(BaseModel):
    """What `adjudicate-entities` renders: the two surface forms in question, nothing else.

    No score, no corpus context — the cheap pass's own number already decided this pair is worth
    asking about at all, and handing the score to the model would invite it to defer to a signal
    it cannot see the reasoning behind rather than to actually look at the two names.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    left: str
    right: str


class EntityVerdict(BaseModel):
    """One model's answer: the verdict, and a one-line reason in the passage's own language.

    The reason is not enforced or parsed by anything downstream — `weft_kg.adjudication` reads
    only `verdict` — it exists so a person reviewing a merge later can see what the model thought
    it was doing, the same argument `weft_kg.extraction` makes for storing a fact's own predicate
    rather than a bare boolean.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: SameEntity
    reason: str = ""


class AdjudicateEntitiesPrompt(TypedPrompt):
    """Ask a model whether two surface forms name the same real-world thing.

    **How this prompt is reached, and the wart it carries — the same one `ExtractFactsPrompt`
    states above, one task later.** `GraphStore.reconcile` is not a pipeline stage and resolves no
    `StageLookup`, so it constructs `AdjudicateEntitiesPrompt` directly rather than looking it up by
    name, exactly the reason `LlmFactExtractor` constructs `ExtractFactsPrompt` directly. It is
    registered anyway: this pack's `Disclosure` says that under `weft reconcile --mode full` two
    entity names leave the machine, one pair per ambiguous pair, and this class is the only
    artefact that says *how* they are asked about — hiding it from `weft plugins list` and from
    `manual/contract-reference.md` would trade a documented limitation for an undocumented one.
    The limitation itself: **a `[plugins]` pin on `adjudicate-entities` changes the listing and
    does not change what the reconcile pass asks**, because neither the ingest path nor a
    reconcile pass publishes a by-name capability lookup.

    The English text is the fallback every locale degrades to; the Polish one exists for the same
    reason `ExtractFactsPrompt`'s does — the measured corpus has a Polish subset (`09` §4) — and is
    written as Polish prose, not as a transliteration of the English.
    """

    name: ClassVar[str] = ADJUDICATE_ENTITIES_NAME
    input_model: ClassVar[type[BaseModel]] = AdjudicateEntitiesRequest
    output_model: ClassVar[type[BaseModel] | None] = EntityVerdict
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You are shown two names that a corpus used, and asked whether they name the "
                "same real-world thing — the same person, organisation, place, method, dataset "
                "or other entity, rather than two things that merely look alike. Three answers "
                "are possible: yes, no, and unsure. Unsure is a real answer, and it is the "
                "right one whenever the two names alone do not settle the question — prefer it "
                "to a guess. A wrong yes merges two entities into one with no way back; a wrong "
                "no leaves a graph that quietly stays split when it should not have."
            ),
            user=(
                "First name: ${left}\n"
                "Second name: ${right}\n\n"
                "Do these two names refer to the same real-world thing? Answer yes, no, or "
                "unsure. Give a one-line reason for your answer, in the same language as the "
                "names, so someone reviewing this later can see what you based it on."
            ),
        ),
        "pl": PromptText(
            system=(
                "Pokazano Ci dwie nazwy użyte w pewnym korpusie tekstów i pytamy, czy nazywają "
                "tę samą rzeczywistą rzecz — tę samą osobę, organizację, miejsce, metodę, zbiór "
                "danych lub inny byt, a nie dwie rzeczy, które tylko wyglądają podobnie. Możliwe "
                "są trzy odpowiedzi: tak, nie i nie wiem. Odpowiedź „nie wiem” jest odpowiedzią "
                "jak każda inna i należy jej udzielić, gdy same nazwy nie rozstrzygają pytania — "
                "lepiej ją wybrać niż zgadywać. Błędne „tak” scala dwa byty w jeden bez możliwości "
                "powrotu; błędne „nie” pozostawia graf podzielony tam, gdzie nie powinien być."
            ),
            user=(
                "Pierwsza nazwa: ${left}\n"
                "Druga nazwa: ${right}\n\n"
                "Czy te dwie nazwy odnoszą się do tej samej rzeczywistej rzeczy? Odpowiedz tak, "
                "nie albo nie wiem. Podaj jednolinijkowy powód swojej odpowiedzi, w tym samym "
                "języku co nazwy, aby osoba przeglądająca to później mogła zobaczyć, na czym "
                "oparłeś swoją ocenę."
            ),
        ),
    }


__all__ = [
    "ADJUDICATE_ENTITIES_NAME",
    "EXTRACT_FACTS_NAME",
    "AdjudicateEntitiesPrompt",
    "AdjudicateEntitiesRequest",
    "EntityVerdict",
    "ExtractFactsPrompt",
    "ExtractFactsRequest",
    "ProposedFact",
    "ProposedFacts",
    "SameEntity",
    "render_allowed",
]
