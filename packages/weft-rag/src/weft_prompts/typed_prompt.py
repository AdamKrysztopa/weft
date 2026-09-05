"""`TypedPrompt` — the base a first-party prompt declares itself against.

A prompt is a Pydantic input model, an output model and a locale key: translatable by
construction, versioned, and already registry-based. That sentence is the specification;
everything below is written fresh against it, not lifted from any other implementation.

**Everything checkable is checked when the class is defined.** `__init_subclass__` runs the
two-direction validator over every declared locale, so a prompt whose template and input model
disagree cannot be imported, let alone registered. A prompt is data with a shape; a shape is
worth having only if something refuses the wrong one.

**Locales are class data, and the fallback is `en`.** Resolving locales relative to the
loader's own file location means a pack cannot ship its own prompts or translations. Here a
translation is a value in a dict on the class, a translator's pack ships its own prompts under
its own names, and nothing opens a file.
Selection is exact locale → primary subtag → `en`; a missing translation degrades the
*language*, which a reader can see, never the answer, which they cannot.
"""

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_llm.payload import Conversation, Message, MessageRole, Rendered
from weft_prompts.errors import MissingFallbackLocaleError, PromptInputMismatchError
from weft_prompts.template import render_template, validate_template

#: The locale every prompt must declare, and every lookup falls back to. Not configurable:
#: a fallback an operator can move is a fallback that can be moved to a locale nobody wrote.
FALLBACK_LOCALE = "en"


class PromptText(BaseModel):
    """One locale's text: an optional system turn and the user turn that carries the ask.

    Two turns rather than a free-form message list, because every prompt in this system has
    exactly this shape and a list would invite a prompt to encode a whole fake conversation —
    which is a technique (`weft-retrieve`'s few-shot work), not a translation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    system: str = ""
    user: str


class TypedPrompt:
    """Base for a declared prompt. Subclasses set the four class attributes and nothing else.

    Satisfies `weft_prompts.contract.Prompt` structurally: this class never imports it, the
    same path every third-party prompt pack takes.
    """

    #: The name this prompt is registered and selectable under.
    name: ClassVar[str] = ""
    #: The prompt's own version, carried onto every `Rendered` so a stored answer can say
    #: which wording produced it. Distinct from the *contract* version, which is
    #: `PROMPT_CONTRACT_VERSION` and is fitness function 6's subject.
    prompt_version: ClassVar[str] = "1.0.0"
    input_model: ClassVar[type[BaseModel]] = BaseModel
    output_model: ClassVar[type[BaseModel] | None] = None
    texts: ClassVar[Mapping[str, PromptText]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.texts:
            # An abstract intermediate base is legitimate; a prompt with no text is not, and
            # registration is where that shows up — a factory that renders nothing.
            return
        if FALLBACK_LOCALE not in cls.texts:
            raise MissingFallbackLocaleError(
                f"prompt '{cls.name or cls.__name__}' declares locales "
                f"{', '.join(sorted(cls.texts))} but not '{FALLBACK_LOCALE}', which every "
                f"lookup falls back to. Add the '{FALLBACK_LOCALE}' text: without it a run "
                f"under an untranslated locale has nothing to degrade to."
            )
        for locale, text in sorted(cls.texts.items()):
            where = f"{cls.name or cls.__name__}:{locale}"
            joined = f"{text.system}\n{text.user}" if text.system else text.user
            validate_template(joined, cls.input_model, where=where)

    def __init__(self, config: object = None) -> None:
        # One positional argument, always — the runner and every service constructor call a
        # factory that way, and a prompt has nothing per-stage to configure.
        del config

    async def render(self, values: BaseModel, ctx: Context) -> Outcome[Rendered]:
        """`values`, in `ctx.locale`'s text, as the conversation a provider will continue."""
        if not isinstance(values, self.input_model):
            raise PromptInputMismatchError(
                f"prompt '{self.name or type(self).__name__}' renders "
                f"{self.input_model.__name__}, and was handed a {type(values).__name__}. The "
                f"caller and the prompt disagree about what this question needs."
            )
        text = self._text_for(ctx.locale)
        messages: list[Message] = []
        if text.system:
            messages.append(
                Message(role=MessageRole.SYSTEM, content=render_template(text.system, values))
            )
        messages.append(Message(role=MessageRole.USER, content=render_template(text.user, values)))
        return Produced(
            value=Rendered(
                conversation=Conversation(messages=tuple(messages)),
                prompt=self.name,
                prompt_version=self.prompt_version,
            )
        )

    def _text_for(self, locale: str) -> PromptText:
        """Exact locale, then its primary subtag, then `en`. Three steps, no search."""
        exact = self.texts.get(locale)
        if exact is not None:
            return exact
        primary = self.texts.get(locale.partition("-")[0])
        if primary is not None:
            return primary
        return self.texts[FALLBACK_LOCALE]
