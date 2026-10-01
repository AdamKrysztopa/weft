"""The `[llm.roles]` role a pipeline's answer is generated under — carried repair **R44.20b**.

`weft_retrieve.engine.roles_needed` names every role any stage of a pipeline calls a model under;
which of them *writes the answer* is a narrower question, and the one a context-window fit depends
on: a corpus that fits `generate`'s window says nothing about a rung whose answer is written under
another role.

**The answer is the last `Generator` stage's own role field** — `answer_role` where a generator
declares one (`contradiction-check`, whose `critic_role` judges and does not write), else `role`.
Both are read only where the field is marked `LLMRole`; a Generator declaring neither has no
generating role this module can read, and says `None` rather than guessing `generate`.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from weft_generate.contract import Generator
from weft_kernel.resolution import ResolvedPipeline
from weft_llm.contract import LLMRole

#: In order of precedence. `answer_role` first: a generator that separates the role that
#: writes from the one that judges names the writer this way.
_ANSWER_FIELDS: Final[tuple[str, ...]] = ("answer_role", "role")


def generating_role(pipeline: ResolvedPipeline) -> str | None:
    """The role `pipeline`'s final `Generator` stage writes its answer under, or `None`.

    `None` when the last stage is no `Generator`, when its config is not a model, or when none of
    its role fields is marked `LLMRole`.
    """
    if not pipeline.stages or pipeline.stages[-1].contract != Generator.__name__:
        return None
    config = pipeline.stages[-1].config
    if not isinstance(config, BaseModel):
        return None
    for name in _ANSWER_FIELDS:
        info = type(config).model_fields.get(name)
        value = getattr(config, name, None)
        if info is not None and isinstance(value, str) and _is_role(info.metadata):
            return value
    return None


def _is_role(metadata: list[object]) -> bool:
    return any(isinstance(item, LLMRole) for item in metadata)
