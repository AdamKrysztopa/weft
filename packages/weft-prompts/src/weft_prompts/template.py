"""The renderer, and the two-direction validator that makes a template checkable.

`.phase2-design.md` §7: "`weft-prompts` ships a renderer that takes a template plus a
validated model and **does not use `str.format`**, so the reference's constraint that every
JSON-example prompt must escape `{{`/`}}` disappears rather than being documented." That
constraint is not a style preference — a prompt telling a model to answer with
`{"verdict": "yes"}` is the *commonest* prompt in a RAG system, and `str.format` reads every
one of those braces as a placeholder. The reference's answer was a rule authors had to remember,
which `CLAUDE.md` records as the category of rule that decays.

**`${name}` instead, over `string.Template`.** Braces are literal, `$` is the one character
that needs care, and JSON contains none. Using the standard library's own parser rather than a
regex written here means `get_identifiers()` reports exactly what `substitute()` will consume —
the validator and the renderer cannot disagree about what a placeholder is, which is the defect
a hand-written scanner beside a hand-written substituter eventually produces.

**Both directions are checked, at class-definition time.** A placeholder no field supplies is a
crash waiting for a user's question; a field no placeholder consumes is dead configuration and,
in a *translation*, a silent change to what the model is told. `docs/04-reference-inventory.md`:128
records that the reference's prompt corner was the one place "the study found no defects", and this
is why: a prompt was "a Pydantic input model, an output model and a locale key", checkable
before anything ran.
"""

from string import Template

from pydantic import BaseModel

from weft_prompts.errors import TemplateVariableError, UnusedTemplateFieldError


def placeholders(template: str) -> tuple[str, ...]:
    """Every `${name}` in `template`, in order of first use, without duplicates.

    Order of first use rather than sorted, because the only reader of this tuple who cares
    about order is a human reading an error message about their own template.
    """
    seen: list[str] = []
    for name in Template(template).get_identifiers():
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def validate_template(template: str, input_model: type[BaseModel], *, where: str) -> None:
    """Refuse a template that disagrees with `input_model`, in either direction.

    `where` names the prompt and locale under check (`"judge:pl"`), so an error message points
    at one translation rather than at "a template".
    """
    if not Template(template).is_valid():
        raise TemplateVariableError(
            f"{where}: the template is not a valid ${{name}} template. A literal '$' must be "
            f"written '$$'; every placeholder is '${{name}}' or '$name'. Template: {template!r}",
            valid_options=(),
        )
    fields = tuple(sorted(input_model.model_fields))
    used = frozenset(placeholders(template))
    unknown = sorted(used - frozenset(fields))
    if unknown:
        raise TemplateVariableError(
            f"{where}: the template names placeholder(s) "
            f"{', '.join(repr(name) for name in unknown)} that "
            f"{input_model.__name__} does not supply. Fields it does supply: "
            f"{', '.join(fields) or '(none)'}.",
            valid_options=fields,
        )
    unused = sorted(frozenset(fields) - used)
    if unused:
        raise UnusedTemplateFieldError(
            f"{where}: {input_model.__name__} declares field(s) "
            f"{', '.join(repr(name) for name in unused)} that this template never renders. A "
            f"field nothing renders is configuration the model is never told about — remove "
            f"it, or use it. In a translation this is usually a dropped ${{placeholder}}."
        )


def render_template(template: str, values: BaseModel) -> str:
    """`template` with every `${name}` replaced by `values`' field of that name.

    `substitute` rather than `safe_substitute`: a missing key here would mean the validator
    let a template through, and quietly leaving `${question}` in the text a model is sent is
    exactly the failure that is invisible until someone reads an answer carefully.
    """
    return Template(template).substitute(
        {name: getattr(values, name) for name in type(values).model_fields}
    )
