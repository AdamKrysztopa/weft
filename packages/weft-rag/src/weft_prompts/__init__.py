"""First-party prompt pack. Publishes the `Prompt` contract and the structured-output cascade.

Task **2.10**: "generation is a pack — the **prompt layer**, the **cascade**, model strings and
the `LLMError` taxonomy ship outside the kernel." This distribution is the first two of those
four; `weft-llm` is the other two.

**Its own distribution, per `.phase2-design.md` decision 19.** `docs/04-reference-inventory.md`:45-48
lands `TypedPrompt`/`PromptRegistry`/`override()` *and* the three-tier cascade in `weft-prompts`
and the taxonomy in `weft-llm`, so this split is followed as recorded rather than re-litigated.
The independent argument for keeping them apart is worth stating anyway: prompts are text-shaped
assets a **translator** ships, and a Polish prompt pack must not depend on an HTTP client and a
retry policy.

**Registers nothing, and declares no `weft.packs` entry point yet.** Fitness function 2 requires
every distribution declaring that entry point to be active *and contributing*, and every
first-party prompt belongs to the plugin that asks it a question — `cited-answer` is 2.9's,
`llm-rerank` is 2.7's, `hyde` and `step-back` are 2.16's and 2.17's. Shipping a prompt here that
nothing asks would be a plugin with no consumer, which is the shape `docs/07-extension-cost.md`
§1 calls "a capability nobody chose". The task that ships the first prompt adds the entry-point
line in the same commit, exactly as `weft-retrieve` did at 2.13.

There is therefore no `Settings` model and no `register` function here: a pack declaring no entry
point is never handed either, and declaring them unused would be two more things to keep true.
`weft_generate` takes the same shape for the same reason.
"""

from weft_prompts.cascade import RAW_TEXT_LIMIT, CascadeTier, Structured, execute
from weft_prompts.contract import PROMPT_CONTRACT_VERSION, Prompt, Prompts
from weft_prompts.errors import (
    MissingFallbackLocaleError,
    PromptInputMismatchError,
    TemplateVariableError,
    UnusedTemplateFieldError,
)
from weft_prompts.registry import PromptRegistry, prompts_service
from weft_prompts.rescue import rescue_json
from weft_prompts.template import placeholders, render_template, validate_template
from weft_prompts.typed_prompt import FALLBACK_LOCALE, PromptText, TypedPrompt

__all__ = [
    "FALLBACK_LOCALE",
    "PROMPT_CONTRACT_VERSION",
    "RAW_TEXT_LIMIT",
    "CascadeTier",
    "MissingFallbackLocaleError",
    "Prompt",
    "PromptInputMismatchError",
    "PromptRegistry",
    "PromptText",
    "Prompts",
    "Structured",
    "TemplateVariableError",
    "TypedPrompt",
    "UnusedTemplateFieldError",
    "execute",
    "placeholders",
    "prompts_service",
    "render_template",
    "rescue_json",
    "validate_template",
]
