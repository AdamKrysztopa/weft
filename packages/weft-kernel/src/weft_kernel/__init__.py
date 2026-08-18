"""The Weft kernel.

What belongs here is settled in G1 and specified in `docs/01-high-level-plan.md`
under *The kernel boundary*: the kernel is what is required to express, load and
run contracts it knows nothing about, plus the domain types those signatures
unavoidably name — and nothing in the kernel performs RAG work.

Its two dependencies, `pydantic` and `opentelemetry-api`, are declared and
enforced by fitness function 1.
"""

from weft_kernel.blocking import BlockingCallError
from weft_kernel.context import (
    Context,
    DuplicateMessageError,
    DuplicateServiceError,
    MessageCatalogue,
    MessageFormatError,
    ServiceRegistry,
    UnknownMessageError,
    UnresolvedServiceError,
)
from weft_kernel.discovery import (
    ENTRY_POINT_GROUP,
    Disclosure,
    EntryPointLike,
    EnvInterpolationError,
    PackRegistrar,
    PackReport,
    PackSettingsError,
    PackStatus,
    allow_list_from_config,
    discover,
    interpolate_env,
)
from weft_kernel.errors import WeftError
from weft_kernel.payload import (
    ExtMap,
    ExtModel,
    Failed,
    Lineage,
    MediaType,
    Node,
    NodeId,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
    SyntheticOrigin,
    Vector,
)
from weft_kernel.registry import (
    DuplicateRegistrationError,
    Registry,
    RegistryEntry,
    UnknownPluginError,
)
from weft_kernel.runner import (
    FlushError,
    Lifetime,
    PipelineResolutionError,
    ResolvedPipeline,
    Runner,
    RunSummary,
    Stage,
    StageSpec,
    TenantMismatchError,
)
from weft_kernel.seam import wrap, wrap_flush

__all__ = [
    "ENTRY_POINT_GROUP",
    "BlockingCallError",
    "Context",
    "Disclosure",
    "DuplicateMessageError",
    "DuplicateRegistrationError",
    "DuplicateServiceError",
    "EntryPointLike",
    "EnvInterpolationError",
    "ExtMap",
    "ExtModel",
    "Failed",
    "FlushError",
    "Lifetime",
    "Lineage",
    "MediaType",
    "MessageCatalogue",
    "MessageFormatError",
    "Node",
    "NodeId",
    "NothingToProduce",
    "Outcome",
    "PackRegistrar",
    "PackReport",
    "PackSettingsError",
    "PackStatus",
    "PipelineResolutionError",
    "Produced",
    "Registry",
    "RegistryEntry",
    "ResolvedPipeline",
    "Runner",
    "RunSummary",
    "ServiceRegistry",
    "SourceId",
    "Stage",
    "StageSpec",
    "SyntheticOrigin",
    "TenantMismatchError",
    "UnknownMessageError",
    "UnknownPluginError",
    "UnresolvedServiceError",
    "Vector",
    "WeftError",
    "allow_list_from_config",
    "discover",
    "interpolate_env",
    "wrap",
    "wrap_flush",
]
