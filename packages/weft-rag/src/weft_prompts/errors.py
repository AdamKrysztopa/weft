"""What a mis-declared or mis-called prompt raises. Four classes, each one failure.

Every one of these is a *definition-time* or *call-time* refusal rather than a degradation.
`docs/02-extension-model.md` §5 records the failure mode: an unknown name that silently becomes
a default produces the consequence "registered but unreachable". A prompt whose
template and input model disagree has exactly that shape: it renders, it says something
slightly different from what its author wrote, and nothing anywhere goes red.
"""

from weft_kernel.errors import UnresolvedNameError, WeftError


class TemplateVariableError(WeftError, UnresolvedNameError):
    """A template names a placeholder its input model cannot supply, or is not a valid template.

    The first direction of the two-direction validator. Raised where the prompt class is
    *defined*, not where it renders, so a mis-declared prompt cannot reach a run at all — the
    same posture `weft_kernel.payload.applicability.Applies` takes for a bad keyword name.

    Fitness function 12's family, for the placeholder-not-supplied raise only: `valid_options`
    is every field the input model does supply. The other raise — the template string is not
    even a valid `${name}` template — has no alternatives to offer, so it carries `()`; there
    is no name that failed to resolve, only a template that does not parse.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class UnusedTemplateFieldError(WeftError):
    """An input model carries a field no template in the prompt's locale set renders.

    The second direction, and the one a translation quietly breaks: a translator who drops
    `${evidence}` has changed what the model is told without changing a single line of code,
    and the answer gets worse in one language only. Checked per locale for exactly that reason.
    """


class MissingFallbackLocaleError(WeftError):
    """A prompt declares translations but not the `en` one every lookup falls back to.

    The locale mechanism degrades the *language*, which a reader can see, and never the
    answer, which they cannot — but only if there is something to degrade to. Without a
    fallback, a run under an untranslated locale would have to either fail or pick a
    translation by ordering, and picking by ordering is the silent coercion this repository
    refuses everywhere else.
    """


class PromptInputMismatchError(WeftError):
    """`render` was handed a model that is not the prompt's declared `input_model`.

    Names both types. `Prompt.render` takes a `BaseModel` because the contract cannot be
    generic over every prompt's own input type; this is the check that gives that widening
    back its teeth, and it is what makes "a prompt is a Pydantic input model" true at runtime
    rather than only in a docstring.
    """
