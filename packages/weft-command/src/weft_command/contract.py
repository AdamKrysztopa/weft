"""The `Command` contract — published here, never by the kernel and never by `weft-cli`.

Task **3.1**: "a pack registers a command exactly as it registers a retriever, and a command
that declares no permission class fails to register while its author is standing there"
(`docs/build-ledger.md`). `docs/03-cli.md` → *Plugin-contributed commands*: "A pack registers
commands against the `Command` contract exactly as it registers a retriever."

**Why this distribution, and not `weft-kernel` or `weft-cli` — an architectural decision this
task took, which no prior document had settled.**

- **Not `weft-kernel`.** G1 draws the line exactly: the kernel expresses, loads and runs
  contracts it knows nothing about, and publishes none of its own (`docs/02-extension-model.md`
  §1 → *Who publishes a contract*). `Command` names a capability — "a CLI-invoked action" — the
  same way `Extractor`, `Chunker` and `Prompt` do, and CLAUDE.md states the test plainly: "if
  you cannot describe the kernel without naming a capability, it is too big."
- **Not `weft-cli`.** `weft-cli` is `docs/03-cli.md`'s **driving adapter** — "every operation it
  performs is a library call a FastAPI route could make identically" — and a pack that
  contributes a command is a **driven** side of that same call, exactly as a pack contributing a
  retriever is. Publishing `Command` from `weft-cli` would mean a third-party command pack
  depending on the adapter to implement the contract the adapter itself drives, which inverts
  the dependency direction the whole extension model is organised around (`docs/02` §1: "a pack
  depends on the pack that publishes the contract it implements, exactly as it would on any
  third-party protocol" — never on the thing that *calls* it). Concretely, `weft-cli`'s own
  `pyproject.toml` already names nine other distributions as dependencies
  (`weft-kernel`, `weft-extract`, `weft-chunk`, `weft-embed`, `weft-store`, `weft-llm`,
  `weft-prompts`, `weft-retrieve`, `weft-generate`); a command pack that had to depend on
  `weft-cli` to get `Command` would inherit every one of those transitively for the sole purpose
  of reading one Protocol.
- **The precedent is `weft-prompts`.** A distribution that publishes a contract and registers no
  plugin of its own is not a new shape — `weft_prompts.contract.Prompt` lived exactly this way
  from task 2.10 until the first prompt landed and added the entry-point line. `weft-command`
  takes the identical position: it publishes `Command` and `PermissionClass`
  (`weft_command.permission`), declares no `[project.entry-points."weft.packs"]` block (fitness
  function 2 requires every distribution declaring that entry point to be active *and
  contributing*, and this one contributes nothing of its own), and `weft-cli` gains it as a
  ninth-turned-tenth dependency the same way it already depends on `weft-prompts` for `Prompt`.

**`Command` is not a pipeline position**, on `weft_prompts.contract.Prompt`'s own footing and
for the identical reason: `.phase2-design.md` §3 groups `Prompt` and `LLMProvider` as "named and
registered, but not pipeline positions", and a CLI command is invoked once per `weft` invocation
(or once per REPL turn), never composed into an ingest or query `StageSpec` list. It therefore
declares no `Stage` base — `weft_kernel.runner.Runner.resolve` has no reason to see it, and
`weft_cli.contract_reference.capability_siblings`' own `_is_stage_protocol` filter, built for
exactly this family of "one method, several unrelated contracts sharing its name", never needs a
special case for it.

**`args_model` and `result_model` are declared in the Protocol body, deliberately** — the
identical choice `weft_prompts.contract.Prompt` makes for `input_model`/`output_model`, and for
the same reason stated there: a command whose arguments are an untyped `argparse.Namespace` is
the shape this contract exists to replace, and a renderer needs `result_model` to introspect a
result's shape without having been written against any one command by name. Required for
`isinstance` is the cost, stated once so nobody rediscovers it: `issubclass` against a Protocol
with non-method members raises `TypeError`, so a future walk over registered `Command`s must use
`isinstance` against a constructed instance, never `issubclass` against the class.

**`run` takes `args` at the call, not at construction — `Prompt.render`'s shape, not `Stage`'s.**
A `Stage` plugin binds its `with:` configuration once, at construction, because one pipeline
position runs many payloads through the identical configuration. A `Command` is the opposite: the
same registered instance answers a different, freshly parsed `args` on every invocation — one
shot from the CLI, or turn after turn in the REPL (`docs/03-cli.md` → *Two modes, one
implementation*: "Both go through the same command objects.") — so binding `args` at construction
would mean constructing a fresh instance per invocation for no reason `Lifetime.PROCESS` could
ever amortise.

**The governing property this task builds into the signature, per `docs/03-cli.md` → *Two modes,
one implementation*:** "a `Command` returns a typed result and never writes to a stream." `run`
returns a decided `Outcome[CommandResult]` — `Produced` / `NothingToProduce` / `Failed`, `02` §1's
own vocabulary applied here as it is everywhere else a contract answers — never a printed line and
never a bare value. `weft_cli` renders `Produced.value` for a human, `--json` renders the
identical value for a script, and the REPL renders it again with the session's context around
it; none of that is buildable if this method had already chosen a renderer by printing.

**`permission_class` is mandatory and declared nowhere in this file** — the same asymmetry
`weft_chunk.contract.Chunker` has with `destroys`, and for the identical reason. `docs/03-cli.md`
→ *Permissions*: "The class is a `ClassVar` on the `Command` contract, read at registration
alongside `lifetime`, `requires` and `provides`; a command that declares none fails to register,
loudly, while its author is standing right there. No default is safe." Declaring
`permission_class` directly in the Protocol body would make it a required `isinstance` member,
checked only once an *instance* exists — too late, since refusing at registration means refusing
before any instance is ever constructed. `Command.required_declarations = ("permission_class",)`
is instead read by `weft_kernel.registry`'s generalised mandatory-declaration check (task 3.1's
own repair to that module — see its docstring, *"`destroys` generalised into
`required_declarations`, not duplicated"*), the identical mechanism `Chunker.
publishes_property_vocabulary` already drives for `destroys`, applied to a second name without
the kernel ever learning the word `Command` or `permission`.

**What this task deliberately leaves to 3.2 and 3.4.** Namespacing a pack's commands under its
own name (`docs/03-cli.md`: "`weft graph build`") is a registration-*name* convention, not a
contract shape — `registrar.add(Command, "graph build", GraphBuildCommand)` registers under
`weft_kernel.registry` exactly as any other string name would, and turning that string into
argparse subcommand wiring, generated `--help` text and REPL completion is task 3.2's own
("`weft --help` cannot drift from what is installed, because core has no command list to edit").
Likewise, rewiring `weft_cli.cli.COMMANDS`'s five built-in commands onto this contract, and
building the renderer that actually turns a `CommandResult` into text/JSON/REPL output, are 3.4's
("the interactive session and the one-shot invocation are the same commands with a different
implementation") — `weft_cli.permissions.CliCommand` was expected to stay untouched a task
longer than it did: task 3.2 found the 3.2/3.4 split stated above too narrow (converting the
built-ins requires exactly the parser-generation and a minimal renderer it names, neither the
REPL nor the plural `--json`/REPL renderers 3.4 owns) and rewired all five onto this contract
immediately, deleting `CliCommand` and `weft_cli.permissions` as dead code — see
`weft_cli.commands`'s own module docstring for the full account.

**Task 3.2 adds `help` — the one piece of metadata 3.1 left this contract without, and the one a
generated `--help` cannot do without.** `docs/03-cli.md` → *Plugin-contributed commands*: "Core has
no list of commands to edit. The help text is generated from the registry" — which needs a
one-line string to generate *from*, and nothing on `Command` as 3.1 shipped it carried one.
`required_declarations` grows to `("permission_class", "help")` rather than gaining a second,
parallel mechanism: `help` is exactly as mandatory as `permission_class` and for the identical
reason — a command with no help text is not a smaller problem than one with no permission class,
it is `weft --help` printing a blank line or crashing outright for whichever plugin forgot it,
discovered by a stranger long after the author who could have been told at registration is gone.
Declared under `if TYPE_CHECKING:`, exactly like `version` and `required_declarations` themselves
— never a required `isinstance` member, for the same reason `permission_class` is not one: refusing
at registration means refusing before any instance exists to check, and `hasattr` on the class is
the only test available at that point.

**`COMMAND_CONTRACT_VERSION` was recorded as `"1.1.0"` here, and that was a mis-recorded major —
corrected to `"2.0.0"` at task **5.2a**, per `docs/README.md` → G9's settled two-audience rule
(`docs/09-release.md` §2.3).** Adding `help` to `required_declarations` is a minor change for a
*caller* — nothing that only ever reads a `Command` through this Protocol changes — but a **major**
change for an *implementer*: every existing `Command` that does not already declare `help` breaks
at registration, loudly, the instant this contract is depended on at the corrected range. G9's
table classifies exactly this row ("add a name to `required_declarations`") as `—` / **major** /
**major**, and the bump a Protocol change takes is the maximum of the two audiences, never the
caller's alone. At the time this docstring first recorded `"1.1.0"`, G9 had not yet settled that
rule, so the bump was chosen from the caller's side only; it is corrected here rather than left
mis-recorded once the rule existed to correct it against — the identical honesty G9's own settled
row applies to itself.
"""

from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import Outcome

#: Fitness function 6's subject for this contract — see the module docstring's note on the
#: correction at task 5.2a: the 3.2 bump to "1.1.0" (when `help` joined `required_declarations`)
#: was a mis-recorded major, per G9's two-audience rule, corrected to "2.0.0".
COMMAND_CONTRACT_VERSION = "2.0.0"


class CommandResult(BaseModel):
    """The typed result a `Command` returns — never printed text, per the module docstring.

    Frozen per CLAUDE.md ("Frozen where the value is a domain object"), and the base every
    concrete command's own result model subclasses with its own fields, the same relationship
    `weft_kernel.payload.outcome`'s `Produced[T]` has to whatever `T` a contract names: a
    renderer built against this base type can accept any command's result without having been
    written against that command by name, which is what lets `weft_cli` render a plugin's
    command exactly as it renders a built-in one. Carries no fields of its own — a bare
    `CommandResult()` states nothing, and every real command adds what it actually produced.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


@runtime_checkable
class Command(Protocol):
    """One CLI-invoked action a pack contributes, registered exactly as it registers a retriever.

    Not a pipeline position — see the module docstring's *"`Command` is not a pipeline
    position"* paragraph. `run` accepts the parsed, already-validated arguments and returns a
    decided `Outcome[CommandResult]`, never printed text — see the module docstring's paragraph
    on *"The governing property this task builds into the signature."*
    """

    if TYPE_CHECKING:
        #: See `weft_extract.contract`'s module docstring for the full `__protocol_attrs__`
        #: reasoning behind the `if TYPE_CHECKING:` / assign-after-the-class-body split, which
        #: applies here unchanged for both of these: neither may become a required `isinstance`
        #: member, or a structurally-conforming `Command` that never restates them would fail a
        #: capability check that has nothing to do with capability.
        version: ClassVar[str]
        #: See the module docstring's paragraph on `permission_class` — this names the class
        #: attribute every implementation must carry; it does not carry the value itself.
        required_declarations: ClassVar[tuple[str, ...]]
        #: The one-line summary `weft --help` prints beside this command's name — see the
        #: module docstring's *"Task 3.2 adds `help`"* paragraph. Mandatory via
        #: `required_declarations`, not a required `isinstance` member, for the identical
        #: reason `permission_class` is not one.
        help: ClassVar[str]

    #: The model `run` accepts. Required for `isinstance` — see the module docstring's
    #: `args_model`/`result_model` paragraph.
    args_model: ClassVar[type[BaseModel]]
    #: The `CommandResult` subclass `run` produces on success. Required for `isinstance`, for
    #: the identical reason `args_model` is.
    result_model: ClassVar[type[CommandResult]]

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]: ...


Command.version = COMMAND_CONTRACT_VERSION
Command.required_declarations = ("permission_class", "help")
