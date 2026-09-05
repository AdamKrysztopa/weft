# 02 — The extension model

This is the load-bearing document. If the ideas here are right the project succeeds; the rest is
execution.

Three concepts, deliberately separate, because conflating them is a documented failure mode:

| Concept | What it is | Unit of |
|---|---|---|
| **Contract** | A published Protocol a plugin satisfies. `Extractor`, `Chunker`, `Retriever`, `Store` | **Extension** |
| **Pack** | An installable Python distribution that registers one or more plugins | **Distribution** |
| **Pipeline** | Data describing an ordered set of stages and their configuration | **Composition** |

One pack may register a dozen plugins across five contracts, and a pipeline may reference plugins
from ten packs. Keeping these three axes independent is what lets the graph add-on be a single
install while still participating in indexing, retrieval and the CLI.

---

## 1. Contracts

A contract is narrow by construction: one method, domain types on both sides. Interface shape is
rarely where a contract goes wrong — dispatch is. Weft's contracts are written fresh against that
shape; no third party's source enters this repository (`NOTICE`).

> **A narrow extractor base scales, and a nearly identical shape shows the failure mode too.** A
> minimal extractor base — one abstract method, domain types in and out, one concrete helper — can
> carry over a dozen subclasses cleanly; that is confirmation the shape in this section holds up in
> practice. Two things are worth carrying forward from that observation.
>
> - **The counter-example makes the rule teachable.** The identical one-abstract-method shape, called
>   a strategy the same way, fails the moment its one method returns a vendor SDK type straight out of
>   the port instead of a domain object. Left that way it decays: one implementation, no library
>   caller, a dead file behind it. Same shape, opposite verdict — the difference is entirely the type
>   at the boundary.
> - **The other half of the good design is the chain executor.** A combinator that takes an ordered
>   list of candidates and knows nothing about their contents is exactly the fallback-chain executor
>   that §3's `fallback: [...]` syntax needs. Its semantics decision — *"non-empty output means
>   success"* — is the right call for scanned-vs-digital PDFs (a text-layer extractor succeeds on a
>   scanned page and returns nothing, so the chain must fall through to OCR), and errors accumulate and
>   are reported together rather than last-one-wins. **Two traps come with it.** A `fail_silently` path
>   that returns an empty result *indistinguishable downstream from a successfully-parsed empty
>   document* must be killed in favour of an explicit outcome type. And a backend that legitimately
>   extracts zero text needs a way to say so, so **G2/G5 must answer: can a backend report definitive
>   success-with-no-content and stop the chain?**

Phase 0 publishes exactly three contracts. Everything else stays internal until a second
implementation forces it, because a published contract you regret is expensive and an unpublished
one is free.

Rules that apply to every contract:

- **Domain types at the boundary.** No vendor SDK types, no framework objects. A port that leaks a
  vendor SDK type is a real shape — one codebase's own architecture-decision record flagged exactly
  this as debt after the fact.
- **Widening a signature to `Any` is not a fix.** A parameter typed `Any` so a vendor object
  satisfies it structurally is the same coupling with the type information deleted.
- **Narrow over convenient.** When a caller needs only half an interface, that is two contracts.
  Splitting vision and text models into separate interfaces rather than one wide one is exactly the
  judgement this rule protects, and it holds here too.
- **Versioned.** Every contract carries a version, enforced by fitness function 6.
- **A capability declares its own metadata.** An extractor states which extensions and MIME types
  it handles. This is not decoration — it is the fix for the accept-then-fail bug, because there is
  then no second list to fall out of step with **and no way to declare a format whose implementation
  is not there** (fitness function 5).
- **A contract's registration API carries a typed configuration model, or the extension point is
  decorative.** See the note on `with:` in §3.

> **The boundary leak, measured, is far larger than one type in one port.** In a comparable codebase
> examined ahead of this design, **14 port signatures carried a vendor SDK type**, across 4 of 17 port
> modules, including a module-level, unguarded, runtime import of that vendor library into the
> innermost ring. A further 6 signatures carried inner- or outer-ring concrete types and 12 carried
> `dict[str, Any]`/`Any`. **Only 11 of 55 contracts were clean.**
>
> The `Any`-widening rule above is the honest version of the same leak: one such port's own comment
> explained its parameters were typed `Any` in order to remain compatible with a vendor's concrete
> types without ever importing them — i.e. the boundary was widened until it could no longer see the
> vendor type. That is not domain typing; it is the same leak with the evidence removed.
>
> The whole debt was tracked as a single open backlog item, with 23 lines flagged against it — a
> backlog item not to inherit.

> **Corrected in G5 — that backlog item was read closely, and it is not a node specification.** It was
> first assumed that those 23 flagged lines enumerated exactly which fields a domain node type has to
> carry. All 23 were read. Most were `dict[str, Any]` or `Any`-typed configuration and LLM-call
> parameters, scattered across several unrelated modules — and **exactly one** concerned a node value
> object at all, flagged with a comment to *"replace with a domain value-object once defined."* The
> backlog item was a *typed-it-as-`Any`-everywhere* ticket, and it specified nothing about a node's
> fields.
>
> **The empirical specification is what was actually found stuffed into a node's metadata field** —
> one untyped dict, 40+ distinct keys. That surface is what G5 designed the payload model against, and
> it is better evidence than the ticket ever was: it shows which data is universal (identity, lineage,
> content), which is one pack's private business (the seven `raptor_*` keys RAPTOR support once
> needed), and which had no business being on a node at all (a tenant identifier).

### Who publishes a contract

**Settled in G1.** The kernel publishes the contract *mechanism* — registration, versioning, the
`Outcome` type, the domain node type — and **no capability contract of its own**. `Extractor`,
`Chunker` and `Store`, the three Phase 0 publishes, ship from the first-party packs that own them;
so do `Retriever`, `LLM` and everything after. A pack depends on the pack that publishes the
contract it implements, exactly as it would on any third-party protocol.

The risk accepted is rival contracts — nothing structurally stops a second pack publishing its own
`Retriever`. The mitigation is ordering, not enforcement: the first-party contract ships first and
every built-in satisfies it. The reasoning for taking that risk is in `01` → *The kernel boundary*.

### What a plugin receives

Two seams, deliberately, because configuration and ambient identity have different lifetimes.
Conflating them is what fissions one passport into three overlapping bags — 10 fields on one context
object, 11 on a second, 14 on a third, with `tenant_id` placed on the one bag plugins never actually
received.

```python
class Stage[In, Out](Protocol):
    async def run(self, payload: In, ctx: Context) -> Outcome[Out]: ...


# A plugin may set these on itself — read defensively, never required:
class MyStage:
    lifetime: ClassVar[Lifetime] = Lifetime.RUN
    requires: ClassVar[tuple[type[ExtModel], ...]] = ()
    provides: ClassVar[tuple[type[ExtModel], ...]] = ()
    config_model: ClassVar[type[MyConfig]] = MyConfig

    def __init__(self, config: MyConfig) -> None: ...
    async def run(self, payload: In, ctx: Context) -> Outcome[Out]: ...
```

- **Configuration arrives at construction.** The kernel validates the stage's `with:` block against
  the Pydantic model the plugin declares, *before* instantiation, and fails naming the stage and the
  field. A contract whose registration API carries no typed configuration model is decorative.
- **The passport arrives at the call, and there is exactly one.** `Context` carries `tenant_id`, run
  and trace ids, cancellation, locale, and `require()`. **The admission rule for new fields:** a
  field is admitted only if it is needed by *every* plugin regardless of contract **and** is
  meaningless to resolve as a service. Tuning knobs fail the second test, which is precisely how one
  of those three overlapping bags above acquired seven of them.
- **Services are resolved by contract.** `ctx.require(LLM)` returns a typed handle or raises naming
  the pack that provides it. This is what makes `llm: Any` — the shortcut a codebase reaches for when
  it wants "typed `Any` for flexibility in tests" — structurally impossible: the handle is typed by
  the contract you asked for. It is a late-binding point, and the distinction from a service locator
  is real: a locator resolves **literal module paths** at import time, untyped and unregistered,
  reaching outward past its own boundary; this resolves exactly what discovery registered, keyed by a
  published contract.

  > **Narrowed in Phase 0 step 4 (2026-08-16), re-dated at step 5 (2026-08-16).**
  > *"raises naming the pack that provides it"* is not yet reachable: which pack provides a contract
  > is known only once discovery reads entry points, and step 4 builds the passport before that
  > exists. So `UnresolvedServiceError` names the contract that was wanted and every contract that
  > *is* resolvable on the run — the same standard `UnknownPluginError` sets, minus the provenance
  > nothing can supply yet. This is a narrowing of the message, not of the promise. This note
  > originally said step 5 would make it true; **it did not, and the reason is structural rather
  > than an omission.** Discovery attributes *plugin* registrations to a distribution
  > (`Registry.add(..., distribution=…)`), but a **service** is not registered through discovery at
  > all: `ServiceRegistry` is per-run, keyed by contract alone, populated by whatever assembles the
  > run, and `PackRegistrar` — the whole surface a pack's `register()` receives — has no service
  > seam. Naming the providing pack therefore waits on a step that lets a pack contribute a service,
  > which no Phase 0 step does.
- **Every contract returns an `Outcome`**, never a bare value: `Produced` / `NothingToProduce` /
  `Failed`. This is what lets the kernel own a fallback combinator without knowing what any stage
  does — it matches on the outcome and never inspects payload content. It also kills the worst
  extraction trap by construction: a `fail_silently` fallback path that returns an empty result
  *indistinguishable downstream from a successfully-parsed empty document*, leaving a backend that
  legitimately extracted nothing with no way to say so. It now can, and it stops the chain. **This
  constrains G5** — the payload envelope is still G5's to design, but its result type is settled.
- **A plugin declares its own lifetime.** `Lifetime.RUN` by default: a fresh instance per pipeline
  run, no thread-safety obligation on the author. `Lifetime.PROCESS` is opt-in and accepts the
  obligation — the instance must be reusable and safe under concurrent `run()`. The kernel's cache
  is keyed `(tenant_id, contract, name, config_hash)`; the tenant is in the key or multi-tenancy is
  broken on day one. A comparable cache seen elsewhere, keyed `f'{tenant_id}:{config.model}'` and one
  of only four locks in a 52,021-line codebase, is the one piece of real tenancy machinery worth
  citing as precedent for keying by tenant at all — what not to copy is that it was cleared only by a
  manual `clear_cache()`.

  > **Narrowed in Phase 0 step 6 (2026-08-16).** `config_hash` is a content hash — `sha256` over a
  > Pydantic model's `model_dump_json()`, or `repr()` for anything else — computed by
  > `weft_kernel.runner._config_hash`, not the config object used as a key directly: a config
  > carrying an unhashable field (a plain `dict`, say) would otherwise make caching impossible even
  > though `frozen=True` alone does not fix that. And `lifetime`, along with `requires` and
  > `provides` below, is read off a stage's *constructed instance* via `getattr(..., default)`,
  > tolerant of a plugin that satisfies its contract only structurally and never literally inherits
  > `Stage`, rather than assumed present. Neither is a reversal — both are exactly what "declares its
  > own lifetime" and "the kernel's cache is keyed…" already say, made concrete by the runner that
  > actually owns the cache.

  > **Narrowed in Phase 0 step 7 (2026-08-16).** `Stage`'s own body carries `run` and nothing
  > else — `lifetime`, `requires` and `provides` are not `ClassVar`s on it, contrary to the code
  > block above, which shows the shape a plugin *may* choose to give itself, not `Stage`'s actual
  > declaration. The reason is `typing.Protocol` internals: `__protocol_attrs__` — the set
  > `isinstance` checks on a `@runtime_checkable` Protocol — is computed once, at class-creation
  > time, by walking every base class's own body. `Extractor`, `Chunker` and the store family all
  > inherit `Stage[In, Out]` so the runner can read `In`/`Out` off `__orig_bases__`; had `Stage`
  > declared those three `ClassVar`s, every one of those contracts would have inherited them as
  > *required* `isinstance` members, silently reopening the `hasattr`-with-better-manners defect
  > `01` §1 condemns — a third-party plugin implementing only `run` would fail a capability check
  > for attributes capability never needed. `getattr(instance, name, default)` already supplies the
  > documented defaults whether or not a plugin inherits `Stage` at all, so nothing about
  > correctness depended on the declaration — only the docstring's account of it did, and that
  > account is now corrected in `weft_kernel.runner`. The same reasoning is why each contract's
  > `version` (below) is declared under `if TYPE_CHECKING:` and assigned after its class body,
  > rather than as a plain `ClassVar` in the body.
- **Errors have a root and an origin.** Packs raise subclasses of `WeftError`, which carries a
  `transient` marker so a pack can say what is worth retrying. Anything escaping a plugin seam is
  wrapped with pack, contract, plugin and stage, `__cause__` preserved so no traceback is hidden.
  The kernel raises its own: unknown plugin name *listing the valid options*, unresolved contract,
  invalid configuration, contract version mismatch. There is **no kernel retry engine** — resilience
  stays at the model seam per `01`.
- **The author supplies no observability.** Span name and `span_kind` are derived at the registration
  seam from contract and plugin name. Hand-written spans are a known decay path — one measured
  instance had drifted to 38 of 54 names off-convention and 5 with no kind, because both were an
  author's job; here there is nothing to forget and nothing to get wrong.

  > **Narrowed in Phase 0 step 3 (2026-08-15).** `stage` is the fourth field on `WeftError`, and
  > this section did not say where it comes from. A pipeline *position* — which slot in an ordered
  > list a plugin fills — is not knowable at registration; it is knowable only once a runner (step
  > 6) resolves a pipeline, and nothing that early exists at step 3, where the wrapper itself is
  > built. So `wrap` — `weft_kernel.seam` — takes the same kind of minimal, reversible choice `06`
  > takes for G2's open questions elsewhere: `stage` is `f"{contract}:{plugin}"`, the one
  > identifying label already available at registration time, and every span is `SpanKind.INTERNAL`
  > — the seam cannot know whether a contract is a store, a client, or neither, so a per-capability
  > kind would mean the kernel naming a capability. This is a narrowing of what "derived from
  > contract and plugin name" means in practice, not a reversal: whatever calls `wrap` once a
  > pipeline exists (the runner, step 6) is free to pass a richer `stage` label, and this is not
  > that decision.
- **Error text is an English literal at the raise site** (G11, settled 2026-08-18). A plugin writes
  its message where it raises, in English, and does not look it up. What a reader gets *instead* of a
  translation is two things a translation never gave them: a `manual/troubleshooting.md` entry, held
  by a coverage ratchet that fails the build for any `WeftError` subclass without one; and **fitness
  function 12** — an error reporting an unknown name carries the valid options as a typed field, so
  requirement 5's second clause is machine-checked rather than a convention each author remembers.

  > **This bullet used to read *"Messages are looked up, never formatted in place"***, describing
  > `ctx.t('graph.node_dropped', n=3)` resolving against a merged catalogue namespaced by pack. **G11
  > retired that seam (2026-08-18)** and this section now owns what replaced it. The reasoning, in
  > short: the gate was opened because two documents disagreed about whether *kernel* errors were
  > among the catalogue's addressees, and the measurement taken to settle it found something larger —
  > after three phases the catalogue had **zero registered messages and zero `ctx.t()` call sites**,
  > and the 51 first-party pack error classes that are its intended clientele had all chosen literals
  > too. G11 settled that Weft's **interface** is English-only as a product decision, and that the
  > **content**-language axis is the one it invests in — `Query.locale`, `Applies(Language)`, the
  > Polish cleaner, per-locale prompt texts. A locale-keyed message store with one locale is a dict
  > with a constant key, so `MessageCatalogue`, `Context.messages`, `ctx.t()` and their three error
  > classes are gone, taking the kernel from 33 error classes to **30**. Two open questions this
  > closes rather than defers: `add_messages` is not merely unbuilt, it is **not going to be built**;
  > and `09-release.md`'s flag that a pack's message-catalogue keys are *"not on G9's Bring list"* no
  > longer needs an answer, because there are no such keys. `Context.locale` **stays**, and its
  > meaning is sharpened — the run's configured *content* language, whose only consumer is prompt text
  > selection, deliberately distinct from `Query.locale`, "a fact about the ask".
- **Every contract method is `async def`** (G6). There is no sync protocol and no declared colour: a
  CPU-bound stage is still `async def` and offloads its own blocking work. Fitness function 7 fails
  the build on any blocking *call* made while a stage runs — file IO, sockets, `time.sleep`, a
  synchronous driver — which is the realistic mistake; a stage that hogs the loop with pure
  computation is visible in its span rather than caught by a gate. No plugin ever writes
  `asyncio.run`: the library contains exactly one, in `weft-cli`.
- **Cancellation is native, and must not be swallowed.** `ctx` carries cancellation, and under an
  async core that is task cancellation. A stage must let `CancelledError` propagate; the way it gets
  swallowed by accident is `except Exception` around an `await`, which is already forbidden by the
  catch-specific-exceptions rule and is worth stating twice. Cleanup belongs in `finally` or a
  context manager, not in a handler that returns `Failed`.
- **Streaming is a service, not a second contract.** A generator resolves `ctx.require(TokenSink)`
  and emits tokens as it produces them, then returns a decided `Outcome[Answer]`; the CLI provides a
  printing sink and a batch run provides a no-op. One generator contract, and `Outcome` keeps the
  meaning §1 gives it — it is decided when the stage returns, not when a stream is drained. The shape
  being refused is a real one: **paired registration decorators — one non-streaming, one streaming —
  10 sites each, kept symmetric by hand with no test asserting it.** A sink fails the passport's
  admission rule — only generators need it — which is exactly why it is a service and not a field.

### The payload model

**Settled in G5.** What flows between stages, and what a pack may attach to it.

```python
class Node(frozen):
    id: NodeId  # digest — see Identity below
    lineage: Lineage  # parents: tuple[NodeId, ...] (never empty except at a root)
    # sources: frozenset[SourceId] — derived, never authored except at a root (Node.synthetic)
    content: str
    media_type: MediaType
    embedding: Vector | None
    ext: ExtMap  # namespaced, typed by declaration
```

**The core is narrow by an admission rule**, the same shape as the passport's: a field is admitted
only if **every store and every retrieval strategy must understand it to function**. That admits the
six above and excludes everything else. A real counter-example is the specification here — one
untyped `metadata` dict, seen elsewhere, that reached **40+ distinct keys**. Page numbers, parser
names, captions, entities and the seven `raptor_*` keys are all namespaced extension data under this
rule; a tenant identifier, which that same dict also carried, is on the passport instead.

**Extension data is declared, not stuffed.** A pack declares a model that owns a namespace, and the
kernel validates on write:

```python
class GraphData(ExtModel):
    __namespace__ = 'weft-graph'          # the distribution name — collision-free by construction
    entities: list[Entity]
    relations: list[Relation]

node = node.with_ext(GraphData(entities=…, relations=…))    # validated on write
data = node.ext_as(GraphData)                               # typed, or None if absent
```

Namespace strings never appear in plugin code, so `metadata['entites']` — silently `None` forever —
has no equivalent. RAPTOR's seven loose keys become one `RaptorTree` model no other pack can read
or corrupt by accident.

> **Narrowed in Phase 0 step 8 (2026-08-16).** The block above is the *write* side. Reading a node
> back off a store needs the inverse and the kernel does not have it: `ExtMap`'s declared value type
> is the base `ExtModel`, so a dumped namespace — a plain dict in a JSONB column — cannot be
> re-validated into the subclass that owns it without a namespace-to-class map. Per `06` step 8
> that map is **`weft_store.rehydrate.ext_models`, an ordinary `weft_kernel.registry.Registry`**
> rather than a hand-rolled dict, so an unregistered namespace raises `UnknownPluginError` naming
> every namespace that *is* known, and a namespace claimed twice raises naming both claimants —
> rule 5 applied to storage rather than to plugin lookup.
>
> **A pack's `register()` did not contribute one automatically, until task 5.2g — see the block
> below.** Until then, a pack shipping its own `ExtModel` had to call `weft_store.register_ext_model`
> itself, a second, explicit call beyond `register()`, or nodes carrying it would not survive a
> round trip through this store. That was the same gap step 5's narrowing note records for
> `add_messages` below (G11 has since retired that one outright, rather than closing it); this one
> is closed, not merely recorded, and how is below.

> **Built in Phase 5 task 5.2g.** A pack now declares its own `ExtModel` the same way it declares a
> plugin — through the `PackRegistrar` its `register()` already receives —
> `registrar.add_ext_model(GraphData)`, buffered exactly like `add_pipeline_resource` and
> `deprecate` (`weft_kernel.discovery`'s own module docstring). The kernel stays capability-blind:
> `ExtModel` is a payload primitive it already owns (`Node.ext`'s own declared value type), not a
> capability, so buffering a bare class reference teaches the kernel nothing about stores. Turning
> the buffer into something `weft_store.rehydrate.rehydrate_ext` can read is
> `weft_store.rehydrate.register_from_reports`'s job — the generic consumer of every
> `PackReport.ext_models`, called once by whatever already calls `discover()`
> (`weft_cli.registry_bootstrap.build_dependencies`), with no pack named at that call site and no
> edit owed to it by a future pack. `weft_chunk`, `weft_clean`, `weft_enhance`, `weft_pdf` and
> `weft_index` all call it now, and so does the out-of-tree stranger pack
> `examples/weft-example-ingest` for its own `WordCount` — the real proof, since that
> distribution is installed rather than linked (fitness function 9(a)) and reaches
> `ext_models` with nobody here having anticipated it. `_ensure_chunk_offset_rehydrates` — the
> shim that proved the gap, hand-registering `ChunkOffset` alone from inside `weft-cli` — is
> deleted.
>
> **Not every `ExtModel` a pack owns calls `add_ext_model`, and that is a finding of this task
> rather than an oversight.** `weft_retrieve.boolean.BooleanPlan`, `weft_retrieve.corrective.
> CorrectiveTrace` and `weft_retrieve.iterative.IterativeRetrievalTrace` share
> `__namespace__ = "weft-retrieve"`; `weft_generate.contradiction.Agreement` and `weft_generate.
> refine.RefinementTrace` share `"weft-generate"`. All five attach to `QuerySet.ext`/
> `Candidates.ext`/`Answer.ext`, never to `Node.ext`, and only a `Node` is ever handed to a
> `NodeStore` — `rehydrate_ext` reconstructs a *node's* `ext` map and is never called with a
> query-path payload's, so none of the five needs this registry to survive anything. Registering
> all five would do worse than nothing: `ext_models` holds one class per namespace, globally, so
> the second pack-owned class sharing a namespace would raise `DuplicateRegistrationError` the
> moment both are active — which two retrieval or two generation techniques routinely are in one
> run. `add_ext_model` is therefore for an `ExtModel` that reaches a `Node`, not for every
> `ExtModel` a pack happens to own; `docs/lessons.md` L5.20 records the measurement. Fitness
> function 14 (`01`) is the runtime property that keeps every namespace that *does* reach a `Node`
> reachable for rehydration, checked against real, installed packs rather than asserted.

**A schema version is carried in the data, and it is a second axis (G9, 2026-08-21).** An
`ExtModel` is a *schema in a user's database*: `GraphData` is validated on write and persisted inside
every node the pack touched, so adding a required field, renaming one or changing a type breaks rows
already stored. A contract version cannot cover this, and the reason is mechanical rather than
philosophical — **the contract version is not available at the read site.** When a store rehydrates a
JSONB blob, the pack that wrote it may not be installed at all. A version read off the importing
module would be exactly whatever is installed and could never disagree with it, which is the defect
`lessons.md` L5.6 records in another costume.

So every `ExtModel` declares `__schema_version__`, mandatory at class definition beside
`__namespace__`, and the kernel writes it into the dumped namespace. A reader **upgrades or refuses**:
`upgrade(data, from_version)` is a classmethod whose default **refuses**, naming the namespace, the
stored version and the current one. Silence is refusal, the same posture §2 takes for permissions,
and the alternative is a contaminated fallback whose success and failure paths are indistinguishable.

The rule is uniform across every surface that is data at rest — the `ext` map, the store's own table,
the filter AST, pipeline documents, `RunRecord` and `weft.toml` — while the mechanism belongs to
whoever owns each. `Filter.version` is the worked example of why the rule says *in the data*: it is a
`ClassVar`, and pydantic never serialises one, so a filter stored inside a pipeline has always
carried no version at all.

> **Built in Phase 5 task 5.2c.** `__schema_version__` rides the identical seam `__namespace__`
> already uses — `ExtModel.__pydantic_init_subclass__` — rather than `weft_kernel.registry`'s
> `required_declarations`, because that mechanism checks a plugin at *registration*, and an
> `ExtModel` is never registered; it is a `BaseModel` a pack imports and instantiates directly, so
> class-definition time is the only seam that exists for it. The version travels *in the bytes*
> via `SCHEMA_VERSION_KEY`, written by `weft_kernel.payload.ext._dump` — the one place a
> namespace's dumped dict is already assembled, so it is the one place the version can be added to
> it rather than dropped the way `Filter.version` was. `upgrade`'s default raises
> `SchemaVersionRefusedError`, naming the namespace, the stored version and the current one; this
> is not itself a fitness-function-12 family member (`NAME_RESOLUTION_FAMILY`) because there is no
> alternative *name* to offer, the same reasoning that already excludes
> `DuplicateRegistrationError`.
>
> **A stored namespace carrying no version at all — every row written before this task — is not
> assumed to be current.** `weft_store.rehydrate.rehydrate_ext` reads `stored_version` as `None`
> when the key is absent and routes it through `upgrade` exactly like a real mismatch, so the
> default still refuses rather than silently accepting it; the message says "no version at all
> (written before schema versioning existed)" rather than naming a version that was never written.
> The one row this task's own binary run met in the running container took exactly this path.
>
> **Every `ExtModel` in the tree gained the declaration**, all at `1.0.0` — nothing had shipped a
> second shape of any of them, so there is no earlier version for `1.0.0` to be a bump from:
> `weft_kernel.payload.node.SyntheticOrigin`, `weft_chunk.payload.ChunkOffset`,
> `weft_clean.language.Language`, `weft_enhance.keywords.Keywords`, `weft_pdf.document.PdfPages`,
> `weft_index.payload.Representation`, `weft_retrieve.corrective.CorrectiveTrace`,
> `weft_retrieve.boolean.BooleanPlan`, `weft_retrieve.iterative.IterativeRetrievalTrace`,
> `weft_generate.refine.RefinementTrace`, `weft_generate.contradiction.Agreement`, and the stranger
> pack's own `weft_example_ingest.enhancer.WordCount`.

**Transience is a property of the declaration.** `__transient__ = True` on an ext model means the
kernel strips that namespace before any `Store` sees the node. A pipeline that instead needed a
dedicated stage for this — guarding against multi-MB base64 blobs serialised into a JSONB column when
a vision enhancer is absent or fails — could not remove that guard without removing the whole stage. A
stage is a legal target for `remove:` in a derived pipeline; a declaration is not, and it holds
whether or not the producing stage ever ran.

**Stages declare what they read and write.** `requires` and `provides` name ext models, and the
resolver checks the chain at load: a stage requiring `ChunkData` that no upstream stage produces
fails with the stage, the namespace and the providing pack named — the same standard §3 already sets
for a missing plugin. **Reading an undeclared namespace raises**, always, so the declarations stay
load-bearing rather than decaying into documentation the way an unenforced span-kind convention
decays elsewhere. At run time `ext_as` returning `None` is legitimate — the upstream stage may have
produced nothing for this node — and the stage answers with `NothingToProduce` or `Failed`.

**Nodes are frozen, and lineage cannot be omitted.** There are three ways to make one:

```python
child = parent.derive(content=chunk_text)  # lineage carried
summary = Node.combine(members, content=text)  # parents explicit, never empty
probe = Node.synthetic(reason="…")  # explicit, greppable, doctor-reportable
```

`Lineage.sources` is **computed by the kernel** as the union of the parents' sources, so a level-3
RAPTOR summary automatically carries the source ids of every document beneath it. This is the fix for
a real and costly class of data bug: a summary node built with no explicit source reference can carry
none at all, and a deletion path that only deletes by a single source id then leaves it stranded — so
**one class of node becomes unreachable by every deletion path, and deleting a document leaves its
summaries describing it forever**. The justification such a shape usually gets is *"global summary: no
single source document,"* which conflates *no single source* with *no parents*: a summary of this kind
has just clustered a dozen nodes it was built from. Under `combine` that information cannot be
discarded, and under derived `sources` it cannot be forgotten.

**The one exception is a root.** `sources` may be authored directly — not derived — only where
`parents` is empty, because a document's very first node has no parents to derive a `SourceId` from:
extraction has no upstream `Node`, only a source document. `Node.synthetic` is the constructor for
that case: it states the document's id as `sources` explicitly and stamps a kernel-owned
`SyntheticOrigin` onto `ext` carrying why. Everywhere `parents` is non-empty, authoring `sources`
directly is refused: a node claiming a source unrelated to what it actually descends from would make
cascade delete either miss it or delete it under the wrong document, the same defect class as the
unreachable-summary bug above, one field over.

**Two invariants carry that, and neither is a rule an author must remember.** `Lineage` refuses
`sources` supplied alongside non-empty `parents`, and `Node` refuses a parentless node that does not
carry `SyntheticOrigin` — so an unexplained rootless node is unconstructable by *any* path, not only
by the three factories being well-behaved. The second is what makes "explicit, greppable,
doctor-reportable" a fact about the type rather than a convention.

> **Widened in Phase 0 step 1 (2026-08-15).** `Node.synthetic` was specified above with only
> `reason=`. Implementation surfaced the gap this note closes: a document's first, parentless node
> must still get a `sources`, and nothing upstream of it can derive one, so `synthetic` also accepts
> `sources` — the sole remaining place `Lineage.sources` is authored rather than computed. This is a
> widening of a settled decision (G5), not a reversal: derivation still owns every non-root node, and
> `Lineage` itself now refuses `sources` supplied alongside non-empty `parents`, so the exception is
> enforced, not merely documented.

**Deleting a source cascades.** Every node whose derived `sources` contain the deleted document is
deleted with it, and the store reports the removed set so a rebuild knows what to re-derive. This is
deliberately the aggressive reading: a node kept but hidden from retrieval looks like deletion to a
user and is not deletion at all to a regulator. The honest cost is that the RAPTOR root summary
descends from every document, so removing any one document removes the top of the tree. The
mechanism — transactionality, and what `delete` returns — belongs to **G4**.

**Identity is a content-addressed digest** over media type, content, sorted parent ids, and an
ordinal within the parent. Re-indexing unchanged content therefore produces the same ids, which is
what makes re-index idempotent and gives dedup and cache reuse for free. The ordinal is there
because identical content is not hypothetical — a RAPTOR row-recovery implementation that compares
cluster assignments by **exact float equality** cross-assigns cluster ids for two identical chunks
silently. The digest excludes the
embedding (derived from content, and it would bind ids to a model) and the stage configuration (so
two pipelines producing byte-identical output produce one node, which is what lets evaluation
compare them).

**Composition is typed and checked at load.** `Stage[In, Out]` means the ingest path is
`Stage[Seq[Node], Seq[Node]]` throughout while the query path is not: `Retriever` is
`Stage[Query, Seq[Scored[Node]]]`, `Generator` is `Stage[Seq[Scored[Node]], Answer]`. The resolver
checks that consecutive stages compose and fails naming both types. **The score lives on
`Scored[Node]`, not on `Node`** — it is a property of one retrieval, not of the node, and it would
fail the admission rule above. A stage takes and returns a *sequence*; the kernel runner owns
batching, so memory is bounded by batch size rather than corpus size while each stage invocation
stays eager and `Outcome` stays decidable at return.

> **Narrowed in Phase 0 step 6 (2026-08-16).** `Stage[In, Out]` is written once per *contract*
> above — "the ingest path is `Stage[Seq[Node], Seq[Node]]` throughout... `Retriever` is
> `Stage[Query, ...]`" — not once per plugin, and `weft_kernel.runner`'s composition check takes
> that reading literally: it reads `In`/`Out` off the *contract* type passed in each pipeline
> stage's spec, via `__orig_bases__` (Python's own record of a class's declared generic
> parameterisation), never off the plugin implementing it. A plugin satisfying a contract only
> structurally, with no explicit inheritance, is unaffected — the type pair the check compares
> belongs to the contract, which every published contract is expected to state once, at its own
> declaration (`class Extractor(Stage[Seq[SourceDoc], Seq[Node]], Protocol)`), per `06` step 6.

> **Narrowed in Phase 2 task 2.4 (2026-08-17).** The two query-path pairs written above are the
> shape, not the types. As published by `weft-retrieve` and `weft-generate`, `Retriever` is
> `Stage[QuerySet, Candidates]` and `Generator` is `Stage[Passages, Answer]`, with `QueryTransform`,
> `Fuser`, `Reranker` and `ContextPacker` filling the span between them. **The reason is fan-in.**
> The sentence above is right that the query path is not one type throughout; what it does not yet
> say is *why more than two*. A retriever run over n queries across two store arms produces k ranked
> lists, and something must reduce k to one before a reranker, a packer or a generator can mean
> anything. Expressing that reduction as a combinator is impossible here — the composition check
> reads `In`/`Out` off the contract class once, so no stage's types can depend on its configuration
> — so it is expressed as *types*: `Candidates` means "k lists", `Ranking` means "one", and a
> `Fuser` is by definition `Stage[Candidates, Ranking]`. The consequence is the point: a pipeline
> that reaches a reranker before it has fused does not resolve, and the check that refuses it is
> `weft_kernel.runner`'s own, with no inspector in any pack. Neither **G5** nor **G2** is reopened —
> the `Node` payload is untouched and this is still one pipeline model over one ordered list.

### The store contract family

**Settled in G4**, published by `weft-store`. Backends differ genuinely — hybrid search, filtering,
full text, graph traversal — and a real system shows what happens when a contract pretends otherwise:
**17 dispatch sites over backend identity and zero registry lookups**, capability determined by
`hasattr(adapter, 'hybrid_search')`, an error string hard-coding a single backend's own environment
variable name, and `isinstance` guards against one concrete local-filesystem class that made three
safety checks report failure for every remote store.

```python
class NodeStore(Protocol):                         # the base; every store implements all of it
    async def add(self, nodes: Seq[Node]) -> None          # may buffer
    async def flush(self) -> None                          # idempotent; the runner calls it
    async def get(self, ids: Seq[NodeId]) -> Seq[Node]
    async def delete_source(self, sid: SourceId) -> Removed
    async def scan(self, cursor: Cursor | None) -> Page[Node]
    async def count(self) -> int
    async def put_source(self, rec: SourceRecord) -> None
    async def get_source(self, sid: SourceId) -> SourceRecord | None
    async def list_sources(self) -> Seq[SourceRecord]

class VectorSearch(Protocol):
    async def search_vector(self, vec: Vector, top_k: int, filter: Filter | None) -> Seq[Scored[Node]]

class TextSearch(Protocol):
    async def search_text(self, text: str, top_k: int, filter: Filter | None) -> Seq[Scored[Node]]

class MetadataFilter(Protocol): ...                # marker: supports the whole operator set
```

> **Narrowed in Phase 0 step 7 (2026-08-16).** The block above lists `NodeStore`'s capability
> methods but not `run` — and the pipeline example above it (§3) selects `store` as an ordinary
> stage, `- id: store\n    use: pgvector`, through the same `StageSpec` mechanism as `extract` or
> `chunk`. `weft_kernel.runner` resolves every pipeline stage's contract via `Stage[In, Out]`, read
> off the contract's own `__orig_bases__` (`06` step 6), so a contract usable in that stage
> position must declare it. `NodeStore` therefore also declares `Stage[Sequence[Node],
> Sequence[Node]]` as one of its own bases and carries `run(self, payload, ctx) -> Outcome[...]`,
> additive to the eight capability methods above, not a replacement for `add`: a `NodeStore`
> plugin's `run` calls its own `add` and passes its input through, so the runner's batch counting
> and `flush()` ownership keep meaning what this section says they mean for every other stage.
> This is a narrowing, not a reversal: every method above is unchanged, and `VectorSearch` carries
> no `run` of its own — nothing in an ingest pipeline calls `search_vector`, so it stays a pure
> capability Protocol, checked by `isinstance` against whatever instance `NodeStore` resolved.
> Phase 0 also publishes only `NodeStore` and `VectorSearch` — `06` step 7 scopes the family to the
> two capabilities Phase 0 has a built-in for; `TextSearch` and `MetadataFilter` remain this
> section's design for when a store implementing them exists.

> **Narrowed in Phase 2 task 2.5 (2026-08-17): three of the four tiers are published, and the
> fourth cannot be published as written.**
>
> **`TextSearch` is published**, exactly as the block above specifies, and `PgVectorStore` satisfies
> it over a generated `tsvector` column. `STORE_CONTRACT_VERSION` moves `1.0.0` → `1.1.0`: the
> family grew a capability, so fitness function 6's subject for it moves too. That is a mechanical
> record of a changed surface and nothing more — **G9 is Open** and owns what a version number
> *means*, so nothing here should be read as a compatibility policy.
>
> **`MetadataFilter` is still not published, and the reason is a measurement rather than a
> schedule.** As written above it is a bare marker — `class MetadataFilter(Protocol): ...` — and a
> `@runtime_checkable` Protocol with an empty body has an empty `__protocol_attrs__`, which makes
> `isinstance(x, MetadataFilter)` `True` for *every object in the language*, `42` included.
> Published in that form it would be a capability every store advertises and none has to implement:
> capability derived, but derived from nothing, which is a worse version of the declared flag the
> paragraph below rules out. Making it real needs a member that *is* the capability — an entry point
> taking a `Filter` and nothing else — and that member's shape should be settled against a store
> that translates the whole operator set. pgvector translates none of them today, so choosing it
> now would be a guess against zero implementations, which is what task **2.6** exists to remove.
> **This is a correction to the block above, not a deferral of it**: whoever publishes
> `MetadataFilter` must give it a member, and the four-tier design stands otherwise.
>
> **Repaired 2026-08-17: `needs_store` is checked for every plugin in a stage's chain, not for
> its `use:` alone.** A `fallback:` name is a candidate that really runs — `weft_kernel.runner`
> already refuses one that is unregistered or not substitutable, for exactly that reason — so a
> stage written `{use: vector-top-k, fallback: [hybrid]}` against a vector-only store used to
> pass assembly and then raise a bare `AttributeError` mid-batch, after the run had done work.
> The refusal names which candidate in the chain cannot be served. A fallback name nothing
> registered is left to the runner's own `UnknownFallbackError`, which answers that question
> better; the pipeline is refused either way, so nothing runs unchecked.

> **Narrowed in Phase 2 task 2.6 (2026-08-17): the family is complete, and `MetadataFilter`
> arrives with a member.** The obligation the note above left is discharged — `MetadataFilter`
> publishes `async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]`,
> which is "an entry point taking a `Filter` and nothing else" made real: no vector, no text, no
> `top_k`, the filter alone deciding membership, with the same paging vocabulary `scan` already
> uses. Its shape was settled against a store that translates the whole operator set, as that note
> required: `weft-qdrant` registers `qdrant` under `NodeStore` and satisfies `VectorSearch` and
> `MetadataFilter`, and `pgvector` gains SQL translation for the whole set at the same time.
> `STORE_CONTRACT_VERSION` moves `1.1.0` → `1.2.0` because the family grew a capability. **G9 is
> Open** and owns what a version number means.
>
> **`weft-qdrant` deliberately does not satisfy `TextSearch`, and the asymmetry is the point.**
> Qdrant's text matching is a filter predicate, not a scored ranking, and `search_text` returns
> `Scored[Node]`; a shim returning a constant score, or an index this pack maintained beside the
> collection, would be the second copy of the corpus task 2.5 exists to forbid. So a `hybrid`
> retriever configured against Qdrant is refused by name, and the promise this section makes
> — *"failure names the store, the missing capability and the backends that provide it"* — is
> demonstrable against a real backend rather than against a mock.
>
> **Three narrowings to *"the closed operator vocabulary"*, each forced by two engines having to
> agree**, published in `weft_store.fields` so one parse and one operator table feed both
> translators. What a `field` may name is `Node`'s own shape — `id`, `content`, `media_type`,
> `lineage.parents`, `lineage.sources`, `ext.<namespace>.<field>` — and an extension value that is
> an array is compared element-wise. Then: **ordered comparison (`lt`/`lte`/`gt`/`gte`) takes a
> number and an `ext.` path**, because ordering text means whatever a database's collation means,
> which is a fact about a deployment and not about the filter; **`eq`/`ne` on a set is refused,
> naming `contains`**, because a document store matches a payload array element-wise and SQL
> compares the whole list — one spelling, two meanings, no error; and **identity comparison against
> a floating-point number is refused**, because a document store indexes floats for ranges and not
> for matching, so the same `eq` that selects in SQL selects nothing there. `FILTER_AST_VERSION`
> moves `1.0.0` → `1.1.0`: a filter this AST used to accept no longer validates, which is a change
> to what the data *is*.
>
> **Task 5.2b: the closed operator vocabulary is now dispatched exhaustively, and its permitted
> sets are stated rather than derived.** `docs/09-release.md` §2.3 found that adding a `FilterOp`
> member is textbook-additive everywhere it is *declared* but silently answered the wrong query at
> nine dispatch sites across both translators and the shape validator — `weft_qdrant.store`'s three
> functions, `weft_store.contract.Filter._shape_matches_op`, and `weft_store.pgvector_store`'s SQL
> equivalents of the same translation, `_predicate`/`_text_predicate`/`_text_set_predicate`/
> `_extension_predicate`. Every one now ends `match self.op: ... case _: raise
> UnhandledFilterOpError(...)` rather than a bare fallthrough. `weft_store.fields._ADMITTED[
> FieldKind.EXTENSION]` carried the same defect in its own shape — not a fallthrough but a *widen*,
> since it read `frozenset(FilterOp) - {AND, OR, NOT}` and so admitted whatever the enum gained next
> with nobody having decided that operator belongs on a pack's own namespaced data — and is now the
> nine members named by hand, refused everywhere else by `field_for`'s existing
> `FilterOpMismatchError`. Fitness function 13 (`01`) is the runtime property that keeps this true:
> a manufactured operator none of the twelve real members equal must be refused by every one of
> these sites, not merely by the ones a reviewer happened to look at.
>
> **Recorded rather than hidden:** `01` → *Runtime shape* also names an **ephemeral in-memory
> store** — "a dict with brute-force cosine, never persisted, used by the conformance kit and by
> pack authors' unit tests so writing a plugin does not require Docker". It does not exist, no
> ledger task claims it, and this task did not build it: the conformance kit runs against the two
> real containers and skips, with a reason, when they are absent.

> **Extended by G7 (2026-08-21): two more Protocols, because derived data outlives its source.**
> `delete_source` sat on `NodeStore` from G4 and **nothing in the tree called it** — while `02` §4's
> graph pack holds entities and relations derived from nodes it would never hear about. That is the
> RAPTOR-summaries-no-deletion-path-can-reach scar (§1's *worst data bug*, above) reappearing
> first-party, and G7 found it by asking what the graph pack genuinely cannot do rather than by asking
> whether a bus would be nice. Both additions are `@runtime_checkable` members
> of this family, per the paragraph above: a pack satisfies them or it does not, and nobody declares
> a flag.
>
> ```python
> class SourceDeletable(Protocol):
>     async def delete_source(self, sid: SourceId) -> Removed
>
> class Reconcilable(Protocol):
>     async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport
> ```
>
> **`SourceDeletable` is the fast path.** Deletion fans out synchronously, in-command, across *every*
> registered plugin that satisfies it — not just the node store — and a participant that fails is
> reported rather than swallowed. It is a separate Protocol rather than a reuse of `NodeStore`
> because a graph store is not a node store: it would otherwise owe `scan`, `count` and the three
> source methods to answer one question about deletion, which is the optional-method design this
> family exists to refuse.
>
> **`Reconcilable` is the safety net, and it is why there is no bus.** A bus reaches only subscribers
> live when the event fired; it cannot repair a pack installed *after* the corpus was built, a drain
> killed mid-flight, or a second machine sharing one database. Convergence can, and it needs nothing
> new to ask its question: `list_sources`, `scan` and `count` already answer *what should exist*.
>
> **Measured false for `list_sources`, 2026-08-22 at task 6.21, and corrected here rather than
> left standing.** The sentence is true of the *contract* and was false of the *running system*:
> nothing on the ingest path calls `put_source` — one caller exists in the whole tree, inside
> `weft_qdrant.store` itself — so `weft_sources` is empty after a real `weft index` and
> `list_sources()` returns `()`. A `repair` pass built on it deleted every graph node the `kg`
> pipeline had just written, found by running the binary and not by the tests, whose hand-written
> corpus double populated the method the system does not. **`scan` and `count` do answer**, because
> every writer populates the nodes they read; until ledger task **6.24** gives `SourceRecord` a
> writer, a participant asking *what should exist* by source must derive it from `scan`'s own nodes
> and their lineage. `docs/lessons.md` L6.14.
> `reconcile` is idempotent, `O(corpus)`, cursored and interruptible — `CancelledError` propagates
> per G6, so a half-finished pass resumes rather than restarting.
>
> **`ReconcileMode` is an `Enum` with two members, and the distinction is a consent boundary.**
> `repair` removes derived state whose source is gone; `full` also **backfills** state that was never
> built. The automatic pass that runs at the end of an index run always uses `repair`. `full` is
> reached only by a person, per run — `weft index --reconcile full`, or `weft reconcile`, which
> defaults to it because someone typing that word means it — and it states its cost before spending
> it. That split is what keeps §3's rule below unamended: backfill runs LLM calls and writes, so an
> *ambient* backfill would silently change what an existing pipeline does by a second route, which is
> G3's installed-and-ambient threat wearing a different coat. A per-run human choice is not ambient.
> `03` owns the command surface and the permission class each mode carries.
>
> **Built in Phase 5 tasks 5.1a and 5.1b.** `STORE_CONTRACT_VERSION` moves `1.2.0` → `1.3.0` →
> `1.4.0`, a minor each time under G9's now-settled rule: a capability added without breaking
> anything that already satisfied the family. `NodeStore` satisfies `SourceDeletable` by
> construction, since `delete_source` was already one of its own methods — so the fan-out finds the
> node store without naming it, which is what "capability is derived, never declared" buys here.
>
> **`ReconcileReport` carries `schema_version` as a serialised field**, not a `ClassVar`, which is
> this section's own G9 rule applied to the report rather than argued about: `Filter.version` is the
> worked example of the mistake, and pydantic never serialises a `ClassVar`.
>
> **A *node* store converges tombstones, not orphans — a narrowing this section's wording does not
> anticipate.** `repair` is described above as removing "derived state whose source is gone", which
> is a graph pack's job. A node store holds the primary data, so it *is* the authority on what
> exists, and a pass that deleted nodes because no `weft_sources` row named them would erase a
> corpus indexed before source records were written — which is every corpus in this tree today,
> since nothing on the index path calls `put_source`. What a node store genuinely owns is the other
> half of `SourceRecord.status`'s reason for existing: every `DELETING` tombstone is a deletion that
> started and did not end. **That is also where "resumes rather than restarting" stops being a
> promise about a cursor**: the backlog is durable rows, so a cancelled pass loses only its own
> progress. `full` backfills nothing here and says so, because a node store holds no derived state
> to build. Proven on both real backends by the conformance kit, and by a stranger's own pack
> (`examples/weft-example-ingest`), which needed no new state to satisfy either Protocol.
>
> `STORE_CONTRACT_VERSION` moves for a grown family, as it did at 2.5 and 2.6. **G9 owns what the
> number means** — and G7 has made that session's job larger, not smaller: these are two freshly
> published capability Protocols, and `ReconcileReport` is persisted by any pack that records what it
> repaired, so it is the *schema in a user's database* problem G9's brief already calls its sharpest.

> **Task 5.1c adds a second method to `Reconcilable`, and `STORE_CONTRACT_VERSION` moves
> `1.4.0` → `2.0.0` because of it — a major, not another minor.** `estimate(self, ctx,
> mode) -> ReconcileEstimate` is what lets `03`'s "full states its cost before it spends it"
> be asked of a participant rather than guessed at: `list_sources`/`scan`/`count` answer *what
> should exist*, never *what converging one of them would cost*. It is a required member, not
> an optional duck-typed one — CLAUDE.md's "cross-cutting concerns live at the registration
> seam, never in a rule authors must remember" applied to a pack's own promise about its own
> cost, which is why this is unlike `weft_command.contract.Command.describe_impact`'s
> optional shape. **G9's two-audience rule is what makes the bump major rather than minor**:
> adding a method to a published Protocol is minor for a caller (nothing that already called
> `reconcile` breaks) and major for an implementer (`PgVectorStore`, `weft_qdrant.store.
> QdrantStore` and the out-of-tree `examples/weft-example-ingest` all stop satisfying
> `Reconcilable` at all until they add the method) — the bump is the maximum of the two, per
> `docs/README.md`'s own G9 row. `ReconcileEstimate` carries `mode`, `pending`, `description`
> and `model_calls: int = 0`: a bare `str` for `description` rather than a structured
> breakdown, because `03`'s own worked example output is one pack's own prose about its own
> outstanding work, and a fixed shape here would force every future `Reconcilable` into one
> vocabulary for "pending" (nodes? sources? entities?) that does not fit all of them. Every
> first-party implementor's own honest floor is `model_calls=0` — a node store holds the
> primary data and has no derived state to backfill, whichever mode is asked about — proven on
> both real backends by the conformance kit and by the stranger's own pack, exactly as
> `reconcile` itself already is.

> **Extended by G13 (settled 2026-08-22) — who a fan-out reaches, and what a participant that is not
> the primary store may ask for.** Phase 5's independence test ran and found the two clauses above
> both untrue in practice for the one pack they were written for. This is the correction, and it is
> stated here because §1 is where both Protocols are published.
>
> **Participation follows use.** `SourceDeletable`'s *"every registered plugin that satisfies it"* was
> narrowed at task 5.1a to the single `NodeStore` that `[services] store` names, so that a project
> with pgvector and Qdrant both installed does not connect to the backend it does not use. The
> narrowing is right about the backend and wrong about the graph store, which registers under
> `NodeStore` too (§4) and is therefore excluded from the fan-out that exists for it. **The rule is
> now: the configured `[services] store`, plus every `NodeStore` named by a pipeline in the project's
> catalogue or by a persisted run record — every other contract still contributes every plugin
> registered under it.** A store this project has actually run data through participates; a store
> nothing selects and nothing names does not. Nothing is declared, so nobody can declare it falsely,
> and no pack author has a rule to remember — which is the same standard *capability is derived,
> never declared* holds registration to, applied to reach. **The cost, stated rather than discovered
> later:** the delete path now reads the pipeline catalogue and the run history, and a store dropped
> from every document that also never ran is out of the fan-out — visible in `weft delete`'s own
> participant list, which names who was asked.
>
> **Built at task 6.18 (2026-08-22).** `weft_cli.participation.stores_in_use` computes the set —
> the configured name, plus every stage name in `full_catalogue` or in a persisted `RunRecord`
> that is registered under `NodeStore` — and `weft_cli.fanout.participants_for` filters
> `NodeStore` down to that set rather than to one name, for `weft delete` and `weft reconcile`
> alike, since both read the same walk and must not disagree about who participates. The set is
> unordered and nothing here makes the configured store lead the list: `[services]` chooses
> which store this project *writes* to, not the order a fan-out asks in, and inventing one would
> be policy this section never argued. A run record that will not parse is refused by name
> (`UnreadableRunRecordError`) rather than skipped — the history is read precisely to find a
> store no document names any more, so the unreadable record may be the only one naming it.
>
> **A participant asks through the passport, not through a wider signature.** `reconcile(ctx, mode)`
> hands a participant nothing that names the corpus, which made `full` backfill unbuildable by
> anyone but the primary store — requirement 4 failing in the open. It needed no contract change:
> `Context.require` is G1's one resolution seam and `NodeStore` already answers *what should exist*
> with `list_sources`, `scan` and `count`. **The CLI registers the configured store into the
> `Context` a reconcile pass carries, and a participant reaches it with `ctx.require(NodeStore)`.**
> A pack that wants to backfill depends on `weft-store` — which the graph pack already does, to
> satisfy these Protocols at all — and asks the corpus what it holds. `STORE_CONTRACT_VERSION` does
> not move: nothing about either Protocol changed, and a contract bumped for a fact about the CLI's
> service registry would be the mis-recorded version G9 spent a session correcting.
>
> **Built at task 6.19 (2026-08-22), and it cost no contract line.** `weft_cli.commands.
> _register_corpus` puts the configured `NodeStore` on the `Context` inside `ReconcileCommand.run`
> and `IndexCommand._auto_reconcile` — inside `run`, never inside `describe_impact`, because a
> confirmation prompt must not open a connection to the corpus before consent. A `[services] store`
> that resolves to nothing registers nothing, and a participant that then asks gets
> `UnresolvedServiceError` naming what it wanted and what is available: the loud failure stays at
> the seam that can diagnose it rather than being translated twice. `examples/weft-example-graph`
> deleted `GraphBackfillUnavailableError` outright — the class was a truthful design finding while
> the access did not exist, and would have been a lie the moment it did — and `full` now backfills
> for real: 2 nodes, 4 entities, from an installed wheel, in a project outside this repository.
> `repair`'s own half of §4's table, *"drops orphans left by anything the fan-out missed"*, is
> deliberately **not** built here: it needs the same access but is a separate promise, and task
> 6.21 is where §4's table is checked row by row.

**Capability is derived, never declared.** At registration the kernel computes which protocols a
store class satisfies, and that set *is* its capability. Nobody writes a flag, so nobody writes a
false one — which matters because a declared flag is `hasattr` with better manners, and a real
signature bug elsewhere is a capability declared unconditionally whose implementation is inserted
conditionally (`.doc`/`.ppt`). **Fitness function 5 holds here by construction**, provided the second
half is respected: a pack with optional dependencies **probes at `register()` and registers the class
that actually works**, so declaration and verification are one act. `weft plugins doctor` prints what
registered, what didn't, and why.

**Retrievers declare what they need.** `needs_store = (VectorSearch, MetadataFilter)`, checked at
resolution against the configured store; failure names the store, the missing capability and the
backends that provide it. There is no adaptation and no degradation: a pipeline that wanted hybrid
search does not quietly become vector-only, because *"quality silently dropped"* is the failure rule
5 exists to forbid. Hybrid is not a third method — it is a store satisfying both search protocols,
with fusion staying where it belongs, in the retriever.

> **Narrowed in Phase 2 task 2.4 (2026-08-17), in two places.**
>
> **`needs_store` is checked at run assembly, not at resolution.** Neither resolver can do it:
> `weft_kernel.runner.Runner.resolve` and `weft_kernel.resolution.resolve` are both kernel code, the
> kernel names no capability, and neither of them knows what a store *is*. The first place that
> holds both the resolved pipeline and the configured store is whatever assembles the run — in this
> tree, `weft-cli` — so the check lands there, reading `needs_store` off the registered factory
> through `weft_kernel.registry.unwrap_factory`. Only the location moves: it is still **before any
> stage runs**, so the promise this paragraph makes — no adaptation, no degradation, failure naming
> the store, the missing capability and the backends that provide it — is unchanged. The check
> itself is built at task **2.5**; the placement is settled here because it is the contract shape's
> consequence, not that task's discovery.
>
> **Fusion does not stay in the retriever.** That clause was written before the query path had a
> type algebra, and Phase 2 publishes `Fuser` as `Stage[Candidates, Ranking]` — a position of its
> own, in the pipeline document, between the retriever and everything downstream. The reason is
> ledger task 2.7's ("fusion and reranking are composable plugins a third party can retune, not a
> fixed ladder") and it is the same reason as `Retriever`'s own narrowing above: fusion inside a
> retriever is a fusion nobody can replace, reweight or omit without replacing the retriever, and a
> hybrid retriever and a query-fan-out retriever would then each need their own copy of it. As one
> stage over `Candidates` there is one implementation for both, because both arrive in the same
> shape. What the original clause was right about is unchanged: hybrid is still not a third search
> method, only a store satisfying both search protocols.

> **Built in Phase 2 task 2.5 (2026-08-17).** The check is
> `weft_cli.run_services.check_store_capabilities`, run over the resolved stage list before the run
> starts, and it refuses with `StoreCapabilityMissingError` naming the stage, the plugin, the
> missing capability, the store, **what that store does advertise**, and which registered stores
> provide what is missing. Two properties of it are worth recording here because they are what keep
> it honest. It **names no capability itself**: the plugin names what it needs, `isinstance` answers
> whether the store has it, and what a store advertises is derived by walking the store contract's
> own pack for versioned capability Protocols — so a store pack shipping a capability this check has
> never heard of is still reported correctly. And a `needs_store` it cannot evaluate — a string, or
> a Protocol without `@runtime_checkable` — raises `MalformedNeedsStoreError` rather than being
> skipped, because skipping it would run the pipeline the declaration existed to stop. The caller
> that assembles a query run is task 2.8's and 2.10's; until then `weft ask` keeps its own narrower
> refusal, since it resolves no plugin that could carry a declaration.

**Stores never embed.** `VectorSearch` takes a vector, `TextSearch` takes text; a store is therefore
not coupled to a model and can be used with two, or with none. A storage port shaped as `query(query:
str, top_k, strategy_name)` does the opposite — it embeds internally *and* carries a retrieval
concept inside the storage port.

**Filters are data.** A serialisable Pydantic AST — `eq ne in lt lte gt gte exists contains and or
not` — with field paths as strings **validated at pipeline load** against the registered ext models,
so `weft-graph.knd` fails at resolution naming `GraphData`'s real fields rather than matching
nothing at query time. One representation serves YAML and Python, which is also what makes a
resolved pipeline diffable. `contains` is not optional: cascade delete is a filter over
`lineage.sources`.

**Durability is a guarantee, not a call.** There is no `persist()` and no `load(force_rebuild)` — a
pairing that, seen elsewhere with no transactional semantics across 9 call sites, imposes disk-index
lifecycle on backends with no such concept. `add()` may buffer; **the kernel runner calls `flush`**
at the end of a run and on cancellation, so no plugin can forget it: a completed run is durable, a
cancelled one durable to its last finished batch.

> **Narrowed in Phase 0 step 6 (2026-08-16).** The kernel names no capability, so `weft_kernel.runner`
> cannot single out "the store" to flush. Instead every resolved stage instance that happens to
> expose an async `flush()` is flushed, once, after the last batch or on the way out when an
> exception cuts the run short — whether or not it is a `NodeStore`. That is safe only because
> `flush` is documented as idempotent: calling it on something that has nothing to flush is a
> legitimate no-op, not a hazard, so the runner does not need to know which stages are stores to
> keep this guarantee. **A flush that itself fails on that second path never replaces the
> exception already propagating** — `CancelledError` above all, which `01` → *Colour* requires to
> reach the caller untouched; the flush failure is attached to it as a note instead, so a cancelled
> task is still a cancelled task.

**Deletion is idempotent and resumable rather than atomic**, because atomicity would disqualify
every backend without transactions and `05` requires two backends satisfying this without stubs.
`delete_source` writes a tombstone — a status on the `SourceRecord` — deletes by filter on
`lineage.sources`, then clears it. A crash leaves the tombstone, so the next call or `weft doctor`
finishes the job, and nothing is ever half-deleted invisibly. It returns counts and affected
sources with a cursor for ids rather than materialising a cascade that can span a corpus.

**`SourceRecord` closes the last reach-through.** `id`, `uri`, `content_hash`, `indexed_at`,
`pipeline`, `status` — one structure serving change detection (re-index skips an unchanged file
instead of re-paying for every enhancer's LLM calls), cascade resumption, and `doctor`'s inventory.
`pipeline` is what lets `weft index` say *"already indexed, by a different pipeline"* rather than
silently skipping or silently duplicating.

Taken together the four names retrieval used to reach through for are gone: `_vector_indices` sits
behind `VectorSearch`, `_strategy_for_nodes` names a concept a store no longer has, `indices_dir`
has nothing to hold because **retrievers never build an index** — text search is a store capability,
so the BM25 pickle cache has no successor — and `update_file_metadata` is `SourceRecord`.

## 2. Packs and discovery

A pack declares one entry point. That is the entire integration surface:

```toml
# in the graph add-on's own pyproject.toml — nothing in weft changes
[project.entry-points."weft.packs"]
graph = "weft_graph:register"
```

`register` receives the registry and adds whatever the pack provides. One call site, many
registrations, any mix of contracts.

**Built-ins ship as first-party packs through the same entry point.** They live in the same
repository for release convenience and get no shortcut. This is fitness function 2, and it is the
difference between a plugin API that works and one that is theoretically supported.

**Discovery is eager.** When a command needs the registry, every permitted pack is imported and its
`register()` is called. Enumeration on its own — `importlib.metadata` reading `.dist-info` — imports
nothing and is always safe; execution begins at `register()`. And because `register()` is where a
pack contributes, it is also the only thing that knows what a pack contributes: nothing can answer
*"who provides `docling`?"* without running it.

> **Corrected in G3 (2026-08-15).** This paragraph read: *"Discovery is lazy: entry points are
> enumerated at startup, but a pack's module is imported only when one of its plugins is actually
> requested. A pack that registers a heavy dependency costs nothing until used."* **That cannot be
> true as written.** Pipelines select plugins by bare name (§3 — `use: docling`), and entry-point
> metadata says nothing about what a pack will register, so resolving a bare name means importing
> packs until one claims it. Lazy import and bare names are mutually exclusive. Bare names win,
> because pipelines-as-data is what Phase 1 exists to prove, and namespacing every reference to a
> distribution (`use: weft-docling/docling`) would couple the data format to packaging and make every
> derived pipeline worse.
>
> The two designs that would have preserved laziness both die on **G4**: per-plugin entry points,
> where the metadata *is* the registration, and a cached resolution index. Neither can express
> **conditional registration** — a pack probing its optional dependencies and registering only what
> works. The true registration set depends on the *environment*, not on the installed distributions,
> so any answer computed without executing `register()` is a second source of truth that can disagree
> with the first. That is the *17 of 23 evaluators* bug (below) in a new costume.

Eager discovery is paid for at the registration seam rather than by asking authors to be careful:

- **`register()` is import-light.** It registers factories, not instances — `registry.add(Retriever,
  'graph', partial(GraphRetriever, settings))` — and a pack imports its heavy dependencies inside the
  factory, not at module top. That is an author obligation, and author obligations decay, so it is
  **measured**: the registration wrapper times each `register()` and records what it added to
  `sys.modules`, and `weft plugins doctor` prints both. Not enforcement — a fact instead of a hope.
- **Discovery runs when a command needs the registry, never at process start.** `weft --version`
  complete with zero pack code executed. `weft --help` *does* need it, because `03` generates help
  from the registry so the command list cannot drift from what is installed. That cost is accepted
  rather than bought off with a second, static entry-point group for commands, which would buy a
  fast `--help` by reintroducing precisely the declared-versus-actual drift this model exists to
  prevent.

  > **Corrected at Phase 3 task 3.7 (2026-08-20).** This paragraph used to name `weft init` and
  > `weft config get` alongside `weft --version` as commands needing no registry — true only
  > before task 3.2 unified command dispatch behind one registry-driven parser. Since 3.2, every
  > subcommand's own argument grammar is generated by walking the *whole* registry
  > (`weft_cli.cli.build_parser`/`_add_command_level`), so recognising `weft init` or
  > `weft config get` as a valid subcommand at all already requires the same discovery `weft
  > --help` pays for — neither command's own `run()` body happens to read anything discovery
  > found, but the cost is paid before either gets the chance not to. `weft --version` remains
  > the **one** categorically pack-code-free command, because it alone never reaches the
  > registry-driven parser at all (`weft_cli.cli.wants_version`'s own mini-parser decides it
  > first) — proven by the same, unweakened subprocess test fitness function 8(b) has carried
  > since Phase 0. See `weft_cli.pipeline_commands`'s own module docstring for the full argument,
  > including why a third, hand-coded pre-scan for `init`/`config get` was rejected: it would be
  > the "second dispatch path" task 3.7's own brief refuses.

Two things this buys immediately that a hand-wired bootstrap could not do at all:

- `uv add weft-graph` adds a capability. `uv remove weft-graph` removes it. Core is untouched both
  times.
- A private, unpublishable, customer-specific pack works exactly like a public one.

**Settled in G3** — entry points execute third-party code at discovery. The posture, the allow-list
and what a refused pack does are specified in *The trust model* at the end of this section.

> **Three things this section should say explicitly, each confirmed against a real codebase.**
>
> **1. Late binding bound in the wrong direction is a real shape, not a hypothetical one.** A
> codebase can have no discovery mechanism of any kind — zero hits for any entry-point or
> package-walking mechanism across hundreds of files — while still carrying **15 dynamic-import
> sites, all against hardcoded literals, 11 of them importing a fixed `'adapters.…'` path**: the
> library dynamically reaching *outward* into its own deployment layer by name, via a module-level
> hook that resolves a concrete adapter class by importing a hardcoded module path. That is **a
> service locator, not dependency injection**, and it is the anti-pattern the entry-point model
> replaces.
>
> **2. Built-ins registering through private import lists is not hypothetical — such lists go wrong
> in practice.** Three mutually inconsistent bootstrap mechanisms in one codebase (eager sibling
> imports in one package's `__init__.py`, a lazy literal tuple of module names in another, a
> comment-annotated import pair in a third) produced two consequences measured in a cold process:
> importing one module registered **17 of 23** evaluators, because two of the plugin subpackages
> were docstring-only — asking for one of the missing ones returned no error and no score; and
> importing another module yielded **3** enhancers while calling its own "list available" function
> yielded **4**. Two sources of truth for "what exists" that disagree until a specific function is
> called. This is why fitness function 2 must be a runtime check.
>
> **3. A pack needs somewhere to put its settings, and this is a documented gap, not a guess.** One
> such strategy-configuration model had exactly **3 fields** — an unvalidated type string, an opaque
> parser-config blob, and a bare list of enhancer names. Enhancers get names only. A graph add-on
> contributing an enhancer, a retriever and a store has no place for its configuration at all. **A
> per-pack config namespace is a distinct requirement from per-stage config** (§3's `with:`), and §4
> needs both.
>
> **This requirement has no gate that owns it, which is itself the defect to fix first.** Item 4
> below routes to G2 and G4; this one routed nowhere, so nothing in the execution script would have
> forced a decision before the pack contract is published. It belongs to **G1**, because G1 draws the
> kernel/pack line and Phase 0 publishes the contracts a pack is written against — a pack contract
> shipped without a settled place for pack settings is a contract that breaks on its first real
> add-on, which is Phase 5's entire test. Added to G1's agenda in `05` §G1 rather than left as prose
> here.
>
> **4. Collision policy left undefined is also a documented failure, not a hypothetical.** Six
> registration decorators in one codebase produced four different collision behaviours: two warn then
> overwrite, and four **overwrite silently with no check at all**. Two plugins both registering the
> same name has no defined outcome in that codebase and none here yet. **Open question for G2 and
> G4** — *"what arbitrates when two plugins claim the same thing?"*

### Pack settings, and what `register` receives

**Settled in G1** — this is the answer to item 3 above. Per-stage `with:` config and per-pack
settings are different lifetimes: `with:` is *this stage in this pipeline*, pack settings are *this
installation of this pack* — credentials, an endpoint, a cache directory, a default model — shared
across every plugin it registers. A codebase with nowhere at all for the second kind forces a pack
contributing an enhancer, a retriever and a store to repeat its connection details three times and
hope they stay in sync.

```yaml
# weft.yaml
packs:
  graph:                            # keyed by the pack's own weft.packs entry-point name
    endpoint: bolt://localhost:7687
    api_key: ${env:GRAPH_KEY}
```

```python
# weft_graph/__init__.py
class Settings(BaseModel):
    endpoint: str
    api_key: SecretStr


def register(registry: Registry, settings: Settings) -> None:
    registry.add(Retriever, "graph", partial(GraphRetriever, settings))
    registry.add_messages(ns="graph", resources=files("weft_graph") / "locales")
```

- **Keyed by pack name — the `weft.packs` entry-point name.** `graph`, not `weft-graph`.

  **This reverses what G1 settled, and the reason G1 gave is what stopped being true.** G1 chose the
  distribution name because "entry-point aliases can collide between two packs; distribution names
  cannot". That held while every pack shipped in a distribution of its own. It stopped holding at
  G10's re-settlement, where `weft-rag` ships twelve registering packs: keyed by distribution, their
  twelve settings blocks collapse into one namespace, so `[packs.weft-rag]` would hand the store's
  `dsn` to the chunker. A key that cannot address one pack is not a per-pack settings namespace.

  So the two identities are separated rather than conflated. **`pack` is what an entry point names**
  — the row `weft plugins list|doctor` prints, the `[packs.<pack>]` settings key, and the name in a
  settings or disclosure failure. **`distribution` is what an index ships** — `[packs] allow`, the
  version column, and G9's deprecation clock. `weft_kernel.discovery`'s own module docstring carries
  the same split at the seam that applies it.

  **What G1's argument was right about, and what now covers it.** Two distributions *can* both
  declare an entry point named `graph`; nothing in Python packaging prevents it. Weft does not
  refuse that — a stranger's pack is not ours to rename, and failing both would punish an operator
  for something only an uninstall can fix — but it does not pass in silence either: `weft plugins
  doctor` reports the collision as an environment fact in its own trailing block, beside version
  skew and inert pins, naming both distributions and saying that one `[packs.<pack>]` block reaches
  both. Reported, not fatal, is the identical posture `ambient` already has for the identical
  reason. (Plugin-*name* collisions remain a separate mechanism — `[plugins]` pins, below.)
- **Typed, validated at discovery.** The pack declares a Pydantic model; the kernel validates before
  `register` is called and fails naming the pack and the field. Never `dict[str, Any]`.
- **Handed to `register`, not injected into plugins.** The pack wires its own settings into its own
  factories, which is why the `Stage` protocol in §1 stays at `__init__(config)` with no second
  injection path and no extra passport field.
- **Secrets are `SecretStr`, with `${env:VAR}` interpolation performed by the config loader**, so no
  component reads the environment itself.
- **A `packs:` key naming a pack that is not installed is an error**, per rule 5 — loud, naming
  every pack that *is* installed so the reader can see the name they meant. A config block that is silently ignored is how a machine ends up running
  without the pack nobody noticed was missing. The remedy is `weft plugins doctor`, not a warning.

**A pack addresses its own resources through its own distribution** (`importlib.resources`), never a
computed path. No component ever computes a path to another package's files — which is what a
`PromptLoader` resolving locales via a hardcoded relative path (`Path(__file__).parent.parent /
'locales'`) gets wrong, making it impossible for a third-party pack to ship its own prompts or
translations at all. The bug is not fixed here; it is
unreachable. `weft-prompts` is the worked case: a `TypedPrompt` carries its own per-locale texts as
class data, checked at class-definition time for the fallback locale's presence, so a pack ships its
own prompt text without asking the kernel for anywhere to put it.

> **This paragraph used to read *"Catalogues are contributed the same way"***, describing
> `registrar.add_messages(ns=…, resources=…)`. **G11 retired the catalogue (2026-08-18)** — see §1's
> *Error text is an English literal at the raise site*. `add_messages` is therefore not an unbuilt
> design any more; it is one that will not be built, and the resource-addressing rule above is the
> part of this paragraph that was always true and is doing the work on its own.

> **Narrowed in Phase 0 step 5 (2026-08-16).** Two things about the example above are not what the
> code does, and both are narrowings rather than reversals.
>
> **`register` receives a `PackRegistrar`, not the `Registry`.** `weft_kernel.discovery.PackRegistrar`
> is `Registry.add` minus its keyword-only `distribution` argument, so the real signature is
> `register(registrar: PackRegistrar, settings: Settings) -> None` and the body is
> `registrar.add(Retriever, "graph", …)`. Attribution is filled in from the distribution discovery is
> currently importing, because attribution is not a pack author's to supply and therefore not theirs
> to get wrong. The registrar also **buffers**: nothing reaches the shared registry until `register`
> returns, so a pack that raises halfway contributes nothing rather than half of itself.
>
> **`add_messages` was never built, and G11 settled that it will not be.** This note used to record
> it as an unbuilt Phase 0 promise whose API status was undecided under G9. Both halves are closed:
> the catalogue is retired, so there is no contribution seam to build and no message keys for G9 to
> rule on. See the paragraph above and §1.
>
> **Built in Phase 5 task 5.2g — `PackRegistrar` gains a third buffered call, `add_ext_model`,
> beside `add_pipeline_resource` and `add`/`deprecate`.** §1 has the full account of why and what
> it excludes; the point that belongs here is the shape: a pack contributes an `ExtModel` at
> registration through the identical seam and the identical buffer-then-commit discipline it
> already uses for a plugin, never a second call outside `register()`. The kernel still learns
> nothing about stores — `ExtModel` is kernel-owned payload data, and `PackReport.ext_models` is
> read back by `weft_store.rehydrate.register_from_reports`, a `weft-store` function, never by
> anything under `weft-kernel`.

### The trust model

**Settled in G3, 2026-08-15.**

**The threat, named precisely, because the convenient framing answers the wrong question.** *Malicious
pack* is the framing that suggests itself and it does not survive contact: if you deliberately
install a hostile distribution, entry points changed nothing — its code was already in your
environment and already ran at the first `import`. Under that framing there is no gap and no decision
to make.

The framing that survives is narrower and true. **Entry points convert *installed* into *executed
with the application's privileges and configuration*.** The gap is not malicious versus benign, it is
**installed-and-intended versus installed-and-ambient**: a pack you never chose, arriving as a
transitive dependency of something you did choose, whose `register()` runs inside your process, at
your credentials, against your data — with nothing in `uv add some-rag-toolkit` telling you it
happened. That is the only risk entry points create, and it generalises past malice to the case that
will actually occur, which is a pack somebody forgot was installed, quietly contributing to
production. Under eager discovery this is not an edge case: **every installed pack executes on every
command that touches the registry.**

**What cannot be built, recorded so that it is not re-proposed.** A two-tier model — discovery open,
but filesystem, network and shell capabilities granted explicitly — is not implementable here. A pack
runs in your interpreter, and CPython has no in-process boundary that constrains `open`, `socket` or
`subprocess`; `sys.audit` hooks are advisory and removable by the code they audit. Enforcement needs
a process or container boundary, which costs a serialisation format for every payload that crosses
it, eliminates the shared `Context`, and contradicts G6's single event loop. A grant weft cannot
enforce is only *a declaration a pack makes about itself*, and a control that looks like enforcement
but is not is worse than an acknowledged gap, because people build policy on it. **Weft therefore
states the posture instead of simulating a control: a pack runs with your full privileges, and
installing is trusting.**

**The posture: open by default, exact pin available.**

```toml
# weft.toml — optional. Absent means open.
[packs]
allow = ["weft-extract", "weft-chunk", "weft-store", "weft-graph"]
```

- **Exhaustive when present.** Everything unlisted is refused. A list that only adds is not a
  control.
- **Distribution names, never versions.** Version pinning belongs to `uv.lock`; duplicating it here
  would create the second list that drifts from the first — the failure the control file in
  `README.md` exists to prevent.
- **Absent by default**, and the reason opt-in security is acceptable *here* specifically: the harm
  under this threat model is unchosen code executing, not credentials exfiltrated. A posture that
  demanded a manual step on every install would be disabled wholesale with `allow = ["*"]`, which is
  open with extra ceremony and a false sense of safety.
- **Malformed is refused, never absorbed into absent.** `packs = ["weft-store"]` — the plausible typo
  for `[packs]` / `allow = [...]` — parses as a list, not a table; a `weft.toml` that writes it is not
  the same document as one with no `[packs]` key at all, and reading the two identically is the
  open-by-default posture reached silently, by typo, with the operator's allow-list never consulted.
  Loud instead: naming `weft.toml`, the `[packs]` key, the shape found and the shape expected. Task
  **1.16** — an audit found both call sites (`weft_kernel.discovery.allow_list_from_config`,
  `weft_cli.registry_bootstrap.pack_settings_from_config`) collapsing this case into absence, which
  is the bug fixed there, not a second posture.

Two things run **always**, opted in or not, and they carry most of the practical weight:

- **The executed pack set is recorded on every run.** Not as a security feature: **Phase 4 requires it
  anyway.** `weft eval compare` across two pipelines is meaningless if the installed pack set differed
  between them, and `weft trace` prints it as one of the facts a persisted run carries. The record
  therefore has an owner and a user outside security, which is what keeps it correct — and the trust
  model gets its answer to *"what was in this process?"* for free.
  > **Corrected by task 4.6 (2026-08-20):** this bullet previously said `weft trace` "claims to
  > replay what a run actually did" — Phase 4 ships no exporter pack (`01` → *The kernel boundary*:
  > exporting a span is a pack's job), so nothing here persists a stage-level trace to replay.
  > `weft trace` reads task 4.4's own persisted run record instead — `docs/03-cli.md` → *Command
  > surface* has the narrowed promise and the argument in full.
- **`weft plugins doctor` flags packs that are not direct dependencies.** Deriving trust from the
  dependency graph was considered as the *mechanism* and rejected: installed metadata does not record
  which distributions a human named, `uv` knows and `pip` does not, and `uvx weft` has no project
  manifest at all — so the fallback would be "open", and a control that evaporates when a file is
  absent is one nobody can reason about. Demoted to reporting, its unreliability is harmless:
  *"cannot determine, no manifest"* is a fine thing for a report to say and an unacceptable thing for
  a gate to say. It makes ambient arrival visible on every doctor run.

**One status vocabulary, shared with G4's conditional registration.** A refused pack and a pack that
lost half its registrations to a missing optional dependency are the same question asked twice —
*why is this not contributing?* — and they get one answer surface, not two:

| Status | Meaning |
|---|---|
| `active` | Imported, `register()` ran, *n* contributions |
| `refused` | Unlisted under an active pin. **Never imported** — refusal precedes execution, or it is not refusal |
| `failed` | `register()` raised |
| `partial` | Registered, but conditional registration skipped something — *what*, and *why* (G4) |
| `allowed, not installed` | Named in `allow`, absent from the environment |
| `ambient` *(flag on `active`)* | Running, and not a direct dependency |
| `deprecated` *(flag on `active`)* | The pack marked one of its own surfaces deprecated at registration |

> **Built in Phase 5 task 5.2e.** `weft_kernel.discovery.PackRegistrar.deprecate(surface,
> reason=...)` is the marking call — a plugin name, a `"Contract:name"` pair, or the pack
> itself, buffered exactly like `add_pipeline_resource` so a pack whose `register()` raises
> marks nothing. `docs/09-release.md` §3's own rule — "the warning is emitted by the
> registration wrapper" — is why the actual `DeprecationWarning` is not this method's job:
> once a pack's buffer commits, `discovery._activate` hands it to
> `weft_kernel.seam.warn_deprecated`, so a pack author states the fact once and the warning
> is never a line they have to remember to print. `weft plugins list`/`doctor` read
> `PackReport.deprecations` as a flag beside a pack's status, exactly the row above states —
> no `PackStatus` member gained, on the identical reasoning `ambient` already settled.

The behaviours that vocabulary implies:

- **An `allow` entry for a pack that is not installed is reported, not fatal.** This is a deliberate
  asymmetry with the rule above that a `packs:` key naming an uninstalled pack *is* an error, and the
  distinction is exact: **`packs:` expresses a requirement, `allow` expresses a permission.** Running
  without something you configured is the "machine quietly missing the pack nobody noticed" failure;
  permitting something absent costs nothing, and making it fatal would break sharing one config across
  environments.
- **`failed` skips the pack and continues**, with one line to stderr naming the distribution and
  pointing at doctor, on every command, suppressed only by `--quiet`. A broken pack silently absent is
  the accept-then-fail shape exactly — the same shape §2's evaluator gap above already illustrates.
- **Every unresolvable plugin name carries its reason**, taken from doctor's own data — *"`docling` is
  provided by `weft-docling`, which is refused"* — never a bare `unknown plugin 'docling'`. This
  states the property in one sentence that the evaluator gap above lacked entirely: asking for a
  registered-but-broken capability there returned **no error and no score**.
- **Exit codes distinguish policy from data.** A pipeline naming a plugin from a `refused` pack exits
  **3**, refused, and names the config key that would permit it. A name provided by no pack at all
  stays **4**; a name lost to `failed` or `partial` stays **4** with its reason attached, because
  neither is a policy decision. A CI job can act on that difference; collapsed into one code, it
  cannot.

**Disclosure, which grants and denies nothing.** A pack may publish what it touches. The kernel reads
a module-level `DISCLOSURE` immediately after import and before calling `register()`:

```python
DISCLOSURE = Disclosure(
    network=("bolt://localhost:7687",),
    filesystem=("~/.cache/weft-graph",),
    subprocess=(),
    note="Reads and writes the configured Neo4j database.",
)
```

- **Concrete strings, not booleans.** `network: true` is noise; a hostname is information.
- **Optional.** Doctor prints `not disclosed` when it is absent. The asymmetry with the mandatory
  command permission class below is principled rather than convenient: **a permission class is
  enforced**, the kernel acts on it, so demanding it is fair; **disclosure is not**, so requiring it
  would produce only text, and required unverifiable text reliably degrades into copy-pasted
  boilerplate. `not disclosed` is honest, informative, and applies the same social pressure without
  manufacturing false data.
- **It is a disclosure to the operator, never a claim weft checks.** Weft refuses nothing on the basis
  of it. Stated in this form deliberately: a field that reads as *"this pack does not use the
  network"* is unverified, unenforced, and fails silently in the unsafe direction; a field that reads
  as *"this pack talks to `bolt://…`"* is documentation with a fixed location and a machine-readable
  shape, which nobody can mistake for a sandbox.
- **A near-miss worth naming, because a builder will find it and think it is clever.** G6's fitness
  function 7(b) already installs a blocking-call detector that intercepts `open`, `socket` and
  `subprocess` at the stage seam. It must **not** be reused as a capability observer. It sees only
  *blocking* calls on the loop thread, so an async HTTP client or anything behind `to_thread` is
  invisible to it — it would report "no network access" for a pack that spent the whole stage
  exfiltrating over `aiohttp`. Sound for colour, unsound for security, and a detector reused across
  that line is how false assurance gets built.

**What this model does not solve, stated so nobody assumes otherwise.** Signature verification,
sandboxing, per-pack privilege separation, and any defence against a pack that is hostile once
running. All four are out of reach without a process boundary. If weft ever wants them it wants an
out-of-process pack host, and that is a new decision with its own gate — not an extension of this
one.

## 3. Pipelines as data

A pipeline is an ordered list of stages. Each stage names a contract, selects a plugin by name, and
carries that plugin's configuration. Because it is data, it can be diffed, versioned, generated,
compared in evaluation, and — the point — derived.

**Settled in G2, 2026-08-16.** Everything from *One model, two directions* onward is that session's
outcome. The rule that shapes all of it: **the written order is the pipeline.** Resolution checks an
order and refuses a bad one; it never reorders behind the author's back, because a resolver that
silently finds a working arrangement is the same species as a silent fallback, and `01` rules those
out everywhere else.

**One model covers both paths.** A query pipeline is a pipeline — same operators, same slots, same
constraint checks, same frozen resolved form — typed by its endpoints through `Stage[In, Out]`. This
is what makes a retrieval configuration derivable and therefore comparable, which Phase 4's exit
criterion requires. It obliges Phase 2 to express the router as a stage rather than as an engine.

The example below is **an example, not a canonical order** — see *No canonical ingest order*.

```yaml
# base.yaml — one pipeline, not the pipeline
name: base
stages:
  - id: extract
    use: docling
    fallback: [pdfplumber, ocr]
  - id: clean
    use: standard
  - id: chunk
    use: sentence
    with: {size: 512, overlap: 50}
  - id: embed
    use: bge-m3
  - id: store
    use: pgvector
```

> **A `fallback:` chain is executed, as of Phase 2 task 2.28 — by the runner, and not yet from this
> document.** `StageDeclaration.fallback` holds the per-stage list a document writes, "tried in order
> until one produces" per `11` §4, and `weft_kernel.fallback.try_in_order` is what walks it — the
> fallback-chain executor described in §1 above, built as a combinator over *any* contract per `01` →
> *The kernel boundary* and never specific to extraction. `Runner._invoke_stage` calls it for a stage
> whose `StageSpec.fallback` is non-empty and makes the single wrapped call it always made for one
> whose list is empty.
>
> **What is not built, stated here because this is the page a `fallback:` block is written against.**
> Nothing carries *this document's* list onto a `StageSpec` yet: `resolve()` below produces
> `ResolvedStage.fallback` as data, `weft_cli/ingest.py` builds `weft index`'s four specs by hand
> with no fallback at all, and the module that would join the two — `weft_cli/compile.py`, turning a
> resolved document into specs — is tasks 2.4 and 2.8 (`docs/build-ledger.md`). So the example above
> is executed by a caller that hands the runner such a spec, which today means a test or a Python
> caller; the `weft index` route arrives with that task. Everything below describes the mechanism as
> built, not a path a document already takes.
>
> **Corrected, ledger task 4.0 (2026-08-20): the prediction above was wrong, and 2.29's own note is
> the record of it.** 2.4 built the document-to-`StageSpec` bridge and 2.8 wired it into `weft ask`'s
> routed default; neither one touched `weft index`, which kept naming its four stages in Python —
> `[services] embed`/`[services] store` select a plugin and carry no configuration, so a stage's own
> `with:` (this section's `size`/`overlap`, or an embedder's own model name) stayed unreachable from
> a file for the ingest path specifically. Task **4.0** is what actually gives `weft index` a route:
> `weft index <path> --pipeline <name>` resolves a document through the same bridge, so the
> `fallback:` list in the example above now reaches `weft index`'s own stages exactly the way it
> already reached `weft ask`'s — see `weft_cli.ingest`'s own module docstring and `manual/
> operations-guide.md` → *Choosing an embedder* for the worked example. The default, no-`--pipeline`
> path is unchanged: three of the four stages are still chosen at run time as this section already
> describes, with no fallback and no `with:` reachable from `[services]` alone.
>
> **The three outcomes, and the author rule that makes them honest.** `Produced` stops the chain with
> a success. `NothingToProduce` **also stops it** — this section's own sentence above, that a backend
> which legitimately extracted nothing "now [can say so], and it stops the chain", read literally: a
> second backend adds nothing to the claim *"I looked, and there is nothing here"*. Only `Failed`, or
> a `WeftError` the registration seam already wrapped, continues to the next candidate; an exhausted
> chain answers one `Failed` naming every candidate and what each said, in order. The rule that makes
> the middle row safe is stated on the combinator and on every backend that ships one:
>
> > Return `NothingToProduce` only when you can distinguish "there is nothing here" from "I could not
> > see it". If your backend cannot tell those apart for this input, return `Failed`.
>
> `weft-pdf` ships both cases as unit tests — a page whose text layer draws no glyphs against a page
> with no text and an embedded image, empirically verified to be distinguishable through both `pypdf`
> and `pdfplumber` — so the distinction the chain rests on is checked rather than promised.
>
> **A fallback name is deliberately never looked up *here*, unlike `use:`, and Phase 2 answered the
> question this paragraph used to leave open.** `resolve()` refuses an unregistered `use:` loudly, by
> name, with the valid options — the ordinary rule. A `fallback:` entry is carried through to
> `ResolvedStage.fallback` exactly as written, checked against nothing, because it may legitimately
> name a plugin that is not installed *yet*: the pipeline above names `ocr` as `docling`'s fallback
> before any pack ships one, and the document should not have to be re-edited the day one does.
> `tests/architecture/test_ff11_pipeline_integrity.py`'s "every shipped pipeline resolves" clause is
> scoped to `use:` for the same reason. What Phase 2 added is a refusal one step later:
> `Runner.resolve` raises `UnknownFallbackError` for an unregistered fallback name, so the *document*
> stays authorable while the *pipeline* refuses to run. Not at try time — that would make the failure
> depend on encountering a document the primary cannot read, so a pipeline could be green for a year
> and fail in production — and never by skipping, which is `01` rule 5's silent fallback with extra
> steps, degrading quality precisely on the inputs the fallback existed for.
>
> **A fallback must be substitutable for the plugin it stands in for.** `Runner.resolve` compares the
> two plugins' class-level `requires`, `provides`, `intact` and `destroys` and raises
> `FallbackNotSubstitutableError` when the fallback demands more or promises less: every check the
> pipeline passed was answered by the *primary*'s declarations, so a fallback that destroys a
> `Property` a later stage needs intact would corrupt the run — and only on the documents the primary
> could not read, which is where nobody looks. Declaring more in the safe direction (an extra
> `provides`, one fewer `destroys`) invalidates no check and is not refused.
>
> **A fallback carries no `with:` block, so a *configured* second attempt is not expressible today.**
> `fallback:` is a list of bare names and a fallback runs on its plugin's own defaults; there is
> nowhere in the grammar to put a configuration, and no substitute mechanism — Weft does not route a
> stage's failures into another pipeline, so writing a differently-configured second pipeline and
> running it over what the first could not read is a manual act, not a feature. Widening the grammar
> is a later task, and the narrowing is stated rather than left to be discovered because the natural
> chain — one parser in two modes — is exactly the one it forbids.

> **A rival ingest order exists, differently ordered, and it is load-bearing to say so.** A comparable
> pipeline chunks first and cleans second, and includes two stages this example omits, by its own
> numbering: **0** separate atomic content (tables and figures, which bypass the parser) from ordinary
> text; **1** chunk; **2** clean; **3** attach chunk-index metadata; **4** enhance; **4.5** scrub
> transient metadata; **5** store. There is **no separate embed stage** in it — embedding happens
> inside storage.
>
> **Settled in G2, 2026-08-16 — Weft adopts no canonical ingest order, and neither does this
> document.** See *No canonical ingest order* below. Stage 0 and stage 4.5 above are both answered
> without being stages: stage 0 becomes *applicability* (a chunker declares it does not operate on
> atomic nodes, and the runner routes them past it), and stage 4.5 is already a seam concern —
> transient stripping attaches at registration alongside spans and error attribution, per `01` →
> *Fitness functions*. The embed question is closed the other way: **G4 forbids a store to embed**,
> so `bge-m3` stays a stage beside the store and never inside it, which is also what keeps `11`'s
> pixel-embedding path buildable.

> **An ordered list is not enough — three findings, all for G2.**
>
> **Ordering constraints exist, and treating them as prose only is a real failure mode.** One cleaning
> pipeline's own docstring is the highest-value scar available: it states, in English, that a
> hyphenation fixer must run before whitespace normalization while newlines still exist (a word broken
> across a page break must still show its embedded newline for the fixer to find it), that a
> column-detector must run before whitespace normalization collapses the gaps it depends on, and that
> whitespace normalization is destructive and must run last — with a warning that changing the order
> breaks functionality. The four derivation operators below let a third party insert a stage between
> the hyphenation fixer and the whitespace normalizer and **silently corrupt text**, because nothing
> enforces the order the docstring only describes. Pipeline-as-data therefore needs an
> **ordering-constraint concept**, not just an ordered list — a fifth position for G2 to attack.
> **G2 settled it as `intact` / `destroys`** — see *Ordering constraints* below.
>
> **A stage list the executor does not read is worse than no stage list.** A cleaning configuration
> can declare an ordered `processors: list[str]` field shaped exactly like this YAML and have it
> **never read** — the executor reads six individual boolean flags instead. Declaring a mechanism and
> then routing around it is worse than declaring none, because a reader trusts the declaration.
>
> **Language-conditional stages are a real requirement this YAML cannot express.** Two of those six
> booleans can additionally be gated on a run-wide language setting — a hardcoded language check
> inside a supposedly generic pipeline. Weft's model needs an answer for it. **G2's answer sharpens
> the diagnosis:** the defect is not the absence of a conditional, it is what the condition reads. A
> run-wide language setting is uniformly wrong for one language on a corpus holding two, with no
> signal, and a 243-word language-specific exception set built for one language will fire on the
> other's text with no way to suppress it. Language is a fact about a **node**. See *Language, and
> what a var is for*.

### Derivation — driving use case A

> *"I need to add KeyBERT to the `specific` pipeline — that pipeline is created from an existing
> one but with KeyBERT added."*

```yaml
# specific.yaml
name: specific
extends: base

insert:
  - after: chunk
    stage: {id: keywords, use: keybert, with: {top_n: 8}}
```

That is the whole change. The parent is referenced, never copied, so improvements to `base` reach
`specific` automatically.

> **The `with:` block deserves to not be an afterthought — the identical mistake shows up
> independently in two unrelated subsystems, which is what makes it a pattern rather than a slip.**
> One evaluation subsystem has a `params` field **literally commented out**, so every metric is
> constructed with zero arguments — no metric there can be parameterised at all. A separate registry
> carries a `TODO: enhance registry to support enhancer-specific configuration`, because its factory
> function accepts a name, an LLM handle, a language and arbitrary kwargs but has nowhere to carry a
> typed, per-plugin configuration. `{top_n: 8}` above and the multi-registration pack in §4 both
> depend on this being solved, which is why §1 now states it as a contract rule.

Four operators, and the set stays closed until something real needs a fifth — **enforced, not merely
stated**: the set is pinned by a ratchet with an empty waiver constant, so a fifth operator fails the
build until someone changes a constant in a diff and records why.

| Operator | Effect |
|---|---|
| `insert` | Add a stage, positioned `after:` or `before:` an existing stage id |
| `replace` | Swap the plugin at a stage id, keeping its position |
| `remove` | Drop a stage by id |
| `set` | Override configuration of an existing stage without changing the plugin |

> **Settled in task 1.4 — the serialisation question 1.1 raised and left open.** `docs/build-ledger.md`
> flagged that four independent model *fields* cannot honour both "operators apply in written order"
> and the `specific.yaml` shape above: a field's position in a `BaseModel` is fixed once, for every
> document, so whichever order the four fields were *declared* in would make one of *remove-then-insert*
> and *insert-then-remove* on the same id permanently unwritable. The operators stay **four keyed
> blocks** — `insert`, `replace`, `remove`, `set` — exactly as printed above and in `specific.yaml`; they
> are not flattened into one tagged sequence, because a YAML mapping cannot repeat a key, and a document
> already says `remove:` above `insert:` or the reverse without any wrapper syntax to invent. What
> changes is where *application order* comes from: it is read off the **document's own key order** (a
> parsed mapping preserves it) rather than assumed from the model's field declarations, and a Python
> call gets the identical treatment — `Pipeline(remove=..., insert=...)`'s keyword arguments preserve
> call order into the same mapping shape `model_validate` receives, so there is one mechanism computing
> "the order", not one per direction. `Pipeline.operator_order` is that mechanism's public face; the
> resolved form's stage list is folded by walking it literally, one block at a time. Round-tripping a
> document — `model_dump(mode="json", by_alias=True, exclude_defaults=True)` — reproduces the exact key
> order it was read from, operator blocks included, because pydantic's own serialisation walks fields in
> declaration order and would otherwise silently undo the ordering choice on the way back out.

**`extends` takes one parent, at any depth.** Resolution is *resolve the parent completely, then apply
this pipeline's operators to that result*, which is the same operation at depth one and depth five —
depth adds no new case. A cycle is a resolution error naming the whole chain. Multiple parents are
refused: merging two stage lists needs interleaving rules no driving use case asks for.

**Every operator is strict.** A target id absent from the resolved parent fails resolution, naming the
id, the pipeline that wrote the operator, the parent it resolved against and the ids that do exist.
`insert` fails equally when its *new* id collides with an existing one, or a child would silently
shadow a parent's stage. `remove` gets no exemption: G4's idempotent deletion is about network
retries against a store, whereas a pipeline is authored text resolved at load, and a `remove` line
matching nothing is evidence the parent moved under you.

**Operators apply in written order**, each validated against the running result, because `02`'s
governing rule is that the written thing is authoritative. Several operators may touch one id.
`remove` followed by `insert` expresses a move, which is why there is no fifth operator for it — and
because application order is read from the document rather than assumed, writing `insert` above
`remove` on that same id is a different pipeline: the insert runs first, while the old stage still
occupies the id, and collides.

**A parent's improvement reaches its children.** Resolution reads live parents, so a parent's edit
flows through and the child's overrides land on top of it. Every stage in the resolved form records
which pipeline or pack put it there, so depth stays forensically readable.

Resolution produces a frozen, fully-explicit pipeline: every stage, plugin, version and
configuration value named, with no inheritance left to interpret. That resolved form is what runs,
what gets logged, and what evaluation compares — so two runs can always be diffed exactly, which is
a real gap this fixes rather than a hypothetical one.

> **"Missing" understates the gap this closes.** A comparable evaluation subsystem had **no
> comparison capability at all**, not a weak one — its own A/B and sweep helpers were entirely dead
> (all public functions, zero references anywhere in the tree), and **nothing in 6,632 lines of that
> subsystem persisted a result anywhere**. Diffing the resolved form therefore only works if resolved
> runs are *stored*; `01` Phase 4's exit criterion now says so.

If KeyBERT is not installed, resolution fails at load with the valid options named. Not at first
document. Never a silent fallback.

**Resolution checks three things, not one** (G5). The plugin exists; the stage's `requires` are
produced by some upstream stage; and consecutive stages **compose by type** — `Stage[In, Out]`, so a
pipeline that reranks before it retrieves fails at load naming both types rather than on the first
query. Everything a resolved pipeline can be wrong about is therefore wrong *before* it runs, which
is the whole reason resolution produces a frozen, fully-explicit form. G2 adds three more checks:
ordering constraints, slot placement, and var definition.

### Ordering constraints — `intact` and `destroys`

G5 solved ordering by **data dependency**. It cannot solve the cleaning chain, because a whitespace
normalizer must run last for being *destructive*, not because anyone reads its output. No dependency
graph can see that.

The representation is the **mirror of `requires` / `provides`**, declared on the plugin class and read
at the seam beside them, so it travels with the plugin into every pipeline including derived ones:

| Declares | Means |
|---|---|
| `requires` | some **earlier** stage must have produced this ext model |
| `provides` | this stage produces it |
| `intact` | no earlier stage may have **destroyed** this property |
| `destroys` | this stage annihilates it |

The properties are published by whichever pack publishes the contract — namespaced marker classes
exactly as G5 gives ext models their namespaces. **No plugin ever names another plugin**, which is the
whole point: a hyphenation fixer from one pack is protected from *any* whitespace normalizer from
*any* pack, and "must run last" stops being a special case — it falls out of destroying everything
downstream needs.

**`destroys` is mandatory** wherever a contract publishes a property vocabulary, an explicit empty
tuple included; registration is refused otherwise, naming the missing declaration. `intact` stays an
optional convention. The asymmetry is deliberate: forgetting `intact` harms only your own stage and
you find out, while forgetting `destroys` silently corrupts a stranger's, and the pack that caused it
never sees a failure.

### Applicability — what a stage operates on

A stage declares what it operates on; the runner routes everything else past it, untouched. This is
the atomic-content-bypass stage (see *No canonical ingest order*, below) turned into a mechanism
instead of a rule an author must remember — a third-party chunker that has never heard of tables
still leaves an atomic table unsplit, because the seam does it.

It also disposes of branching. A pipeline stays one straight line, and "the table path" is simply the
stages whose applicability includes tables. There is no `when:`, no branch, no rejoin, and the
resolved form still prints one order.

**Settled in task 1.6 — the predicate is data, never a callable.** A callable can be *run*; it cannot
be *printed*, checked at registration, or diffed between two resolutions of the same pipeline — the
same complaint *One model, two directions* makes about a second construction path, one level down. So
`Applies` is a frozen model **the kernel publishes** (`weft_kernel.payload.applicability`), on the
same footing `Property` already gives `intact`/`destroys`: data a plugin's class carries, evaluated by
whoever runs the pipeline, never executed by the plugin itself.

A stage declares `applies_to` as a tuple of `Applies` values — a class attribute, read at the seam
exactly as `requires`/`provides`/`intact`/`destroys` already are. `Applies` wraps an **ext model**:
`Applies(Language)` matches any node carrying that fact at all; `Applies(Language, code="pl")` narrows
to nodes whose `Language` additionally has `code == "pl"`. The keyword names are checked against the
fact's own fields **the moment `Applies(...)` is constructed** — which, for a class-level `applies_to
= (Applies(Language, code="pl"),)` tuple, is the moment the plugin's module is imported for
registration — so a typo'd field name fails on the pack's own import, naming every field the model
actually has, rather than shipping a stage that silently never applies to anything. That is the exact
silent-failure class rule 5 rules out everywhere else: a typo and a stage correctly declining every
node it sees are indistinguishable from the outside, and there is no `doctor` command that can tell
them apart after the fact.

Evaluation happens at the seam, in `weft_kernel.runner`, never in the plugin. The fact **absent**
means the stage does not apply — failing to the safe side, exactly as *Language, and what a var is
for* already says unknown language flows past a language-specific stage. The fact **present** means
every constrained field must be equal; there is no third spelling and no negation. This is what makes
"the chunker does not have to know that tables exist" literal rather than aspirational: a chunker
declares the one fact its own splitting logic actually needs — the prose it knows how to find sentence
boundaries in, say — never "not a table". A table simply never carries what the chunker asked for, and
routing it past is a consequence of that requirement going unmet, not a rule about tables the
chunker's author had to think to add. **Vars never participate in applicability** — nothing about
`applies_to` is document-authored at all, so there is no `${var:NAME}` token for `vars:` substitution
to ever reach; a var can say *translate into English*, and applicability can still only ever read what
a node actually *is*.

**A stage that declares no `applies_to` applies to everything.** That is the default, and it stays
silent: every stage written before this task — none of which declares one — keeps running exactly as
it did, and an empty tuple costs nothing to check because there is nothing in it to fail.

Routing is what makes the declaration true. The runner splits a batch into its **maximal contiguous
runs** of "every `Applies` matches" and "at least one does not" — a single filtered call over every
matching node is not enough, because a chunker's `Sequence[Node] -> Sequence[Node]` does not preserve
shape, and once matching nodes have been pooled into one call there is no record of where an untouched
node originally separated two of them. The stage runs once per matching run; every non-matching run
passes through unchanged, in the position it already held; the results are concatenated back in
original order. A pack shipping a chunker that has genuinely never heard of tables can still be handed
this mechanism and prove it: a stage with no conditional on node content anywhere in its own `run` —
one that would happily split anything it is handed — still leaves an atomic node it was never routed
to completely alone.

The resolved form prints each stage's `applies_to`, since a predicate is data: `weft_kernel.
resolution.ResolvedStage` carries it, read off the registered plugin the same defensive way
`requires`/`provides`/`intact`/`destroys` already are.

### Slots — how a pack contributes

A pack may ship complete named pipelines, and it may **contribute into a slot a pipeline opted into**.
It may never rewrite a pipeline that did not ask: installing a package — possibly a transitive
dependency — must not silently change what an existing pipeline does, which is G3's *installed and
ambient* threat applied to your data.

> **Tested by G7 (2026-08-21), and unamended.** This rule governs what an *installed* pack may do,
> and G7 put two candidates against it. An **event bus** was refused by it: a pack observing every
> node a pipeline touched is the same consent problem as rewriting that pipeline, arriving by a
> quieter route. **Reconcile backfill** was not, and the reason is the boundary this rule actually
> draws — a `Reconcilable` pack creating derived data during an automatic pass *would* breach it, so
> the automatic pass never does; backfill is reached only by a person's per-run flag (§1, and `03`).
> The rule bites on *installation*, not on what someone deliberately asks for at the command line.
>
> **Built in Phase 5 task 5.1c.** `weft_cli.commands.IndexArgs.reconcile` is a hardcoded
> `ReconcileMode.REPAIR` default, read from no config at all — `weft_cli.reconcile_policy`'s
> own `[reconcile] mode` governs `weft reconcile` typed by hand, never `weft index`'s automatic
> pass, so a project cannot make the automatic pass reach `full` by editing `weft.toml` once.
> `weft index --reconcile full` is the per-run flag this rule requires; `03` → *Command
> surface* has the fuller argument and the transcript.

- A contribution targets a **named slot**, never a stage id. Stage ids are internal detail that
  `replace` and `remove` exist to change; a slot is a stable, deliberate promise.
- **Two contributions in one slot** are ordered by the declared relations above. Genuine ties break by
  **distribution name**, so two machines with the same installs resolve identically. An author may pin
  an order, which must still satisfy every constraint.
- **A contribution with no matching slot is a recorded no-op** — listed in the resolved form as
  unplaced, and `weft plugins doctor` flags a pack whose contributions land in *no* pipeline at all,
  so "installed and doing nothing" is visible without breaking every pipeline lacking that slot.
- **Slots fill after the extends chain resolves.** Operators address the author's own stages and
  slots; `remove: enrich` drops the slot itself, which is how a pipeline refuses contributions without
  naming any pack. A contributed stage may be **`set` but never `replaced` or `removed`**, and its
  configuration otherwise comes from the pack's own `packs:` settings namespace (§2).
- Contributed stage ids are qualified by distribution (`weft-graph:entities`) so they cannot collide
  with the author's — which holds because the qualified spelling is **reserved**: an authored
  document naming a stage `weft-graph:entities` is refused where it is read, with no registry
  consulted, rather than colliding later when that pack happens to be installed. That is a *stage
  id*, not a plugin name, so G3's ruling that pipelines keep bare names in `use:` is untouched.
- **Installation-dependent targets are recorded, never fatal.** `set: weft-graph:entities` where that
  pack is absent is an unapplied operator in the resolved form, not a resolution failure — the same
  reasoning as an unplaced contribution, and it keeps a tuned pipeline portable. Strictness governs
  targets the pipeline's own extends chain defines.

> **Built in Phase 5 task 5.3a (`S8`).** Everything above was true of the *resolved form* since
> task 1.11 and untrue of anything a pack could actually do: `weft_kernel.resolution.Contribution`
> existed, `resolve()` took a `contributions=` tuple, and placement, qualification and the
> unplaced-recording all worked — but nothing built the producing half, so every property in this
> section was demonstrated only by a test file constructing a `Contribution` by hand. This task
> built it, following `add_ext_model`'s own shape (task 5.2g) rather than inventing a third
> mechanism: `weft_kernel.discovery.PackRegistrar.add_contribution(slot, stage)` buffers one,
> attributed to the calling pack exactly as `add`/`deprecate`/`add_ext_model` already are —
> `distribution` is filled in by the registrar, never stated by the pack — and `PackReport.
> contributions` carries the buffer once `register()` commits. `weft_cli.registry_bootstrap.
> build_dependencies` is the one assembly point `Contribution`'s own docstring already named as
> "whatever assembled the `Registry` from every installed pack's own registration": it
> concatenates every report's own tuple into `Dependencies.contributions`, and all three
> `resolve()` call sites in `weft-cli` (`weft_cli.pipeline_commands`, `weft_cli.ingest`,
> `weft_cli.route_ask`) read it back off that one field — never their own re-derived tuple —
> which is what fitness function 15 holds true after this task as much as at it.
>
> Of the properties this section states, two were genuinely new demonstrations rather than new
> code: "a contribution with no matching slot is a recorded no-op" and "installation-dependent
> targets are recorded, never fatal" were already implemented in `resolve()` at task 1.11 and were
> proven here for the first time against a contribution an installed pack actually produced,
> rather than one a test built by hand. `weft plugins doctor` flagging a pack whose contributions
> land in no pipeline at all is new work: `weft_cli.pipeline_catalogue.declared_slot_ids` and
> `weft_cli.plugins_report.render_doctor`'s own `unreachable_contributions` parameter did not
> exist before this task, because there was no contribution for either to have anything to say
> about. `examples/weft-example-ingest` — installed rather than linked, per fitness function 9(a)
> — is the pack that contributes: it offers its own already-registered `Enhancer` plugin into a
> slot named `enrich`, the same name this section's own worked example (`weft-graph:entities`)
> already uses for the identical kind of position.

### Language, and what a var is for

Two different things wear the word *language*, and separating them is what fixes a real defect: a
run-wide language setting applied uniformly to a corpus that is not uniformly one language.

**A fact about a node.** The source language is provided per node by the extractor or by an ordinary
`detect` stage, and language-specific stages declare applicability over it. A Polish fixer applies to
Polish nodes; English nodes flow past; unknown language flows past, which fails to the safe side. A
mixed corpus becomes correct in one pass instead of uniformly wrong.

**A decision about the pipeline.** A `vars:` block carries values several stages must agree on — a
translation target, a reply language. Vars are inherited, and **a child's override re-resolves every
inherited stage that references it**, so retargeting a whole pipeline is two lines:

```yaml
# base-de.yaml — the entire file
extends: base
vars: {target_lang: de}
```

Scalars only; no var may reference another; referenced only inside `with:` values, never in `use:` or
a stage id, so plugin selection stays a literal name the registry can check. An undefined var is a
resolution error naming the var and the pipeline. The frozen form records every final value.

**Vars never participate in applicability.** Applicability reads the node's facts, always. A var can
say *translate into English*; it can never say *pretend this document is English*. That is what keeps
the two mechanisms from ever disagreeing.

Translation itself needs no new concept: a stage that `requires` the language, rewrites the text and
provides the new one. Everything after it sees a single language, so downstream stages need no
configuration at all.

### No canonical ingest order

**Weft asserts no ingest order, and neither does this document.** A pipeline is data; whether it
cleans at all, and where, is the author's choice. What replaces the blessed list is stronger than it:
any particular order is **proved** by `requires`/`provides` and `intact`/`destroys` rather than
asserted by a plan. Where a plugin has an ordering opinion it declares it, and a violation fails at
load naming the positions that would be legal.

This is also why the "chunk then clean or clean then chunk" question dissolves. Cleaning is not one
thing: hyphenation repair wants to precede chunking, since a word broken at a page break and chunked
is embedded as two fragments and no later stage can rejoin it, while whitespace normalization must
follow a structure-aware chunker whose section and column detection it would destroy. Those are
opposite sides of the same stage, and both are now declarations rather than doctrine.

### One model, two directions

The pipeline **is** a frozen Pydantic model published by the kernel. YAML is a serialisation of it;
Python code constructs the same model directly. That is "both" with one implementation — one
validator, one error set, one resolved form, no builder DSL and therefore no second grammar to keep
in step. Pipelines are YAML; operator policy stays TOML in `weft.toml`, split by shape rather than by
taste: one is a nested document of stage lists, the other is flat policy edited rarely.

**The kernel publishes the model and opens no file.** G1 fixes its dependencies at `pydantic` and
`opentelemetry-api`, so a YAML loader is not among them: the model validates the *mapping* a loader
hands back, and whoever opened the file brought the parser — the same division §2 already makes for
`weft.toml`, where `weft-cli` is the only thing that reads a file. It is also what keeps *one
validator* true rather than aspirational: both directions reach the same validator because neither
passes through a parser the other does not.

**The authored form is not the resolved one, and its error set is `ValidationError`.** A document is
refused where it is read for the invariants that hold with no registry present — it is named, its
keys are keys the model has, **its stage ids are unique**, and its vars are scalars — while
everything needing a parent, a plugin or a distribution belongs to resolution. So a malformed
document is not one of *When resolution fails*' subclasses: it has no resolved parent and no
distributions to name, and filing it there would hand the failure-mode ratchet one
already-documented name to hide behind. Unknown keys are still answered by name, the keys that exist
printed beside the key that does not, per `01`'s loud-failure rule.

That leaves one thing open rather than settled, and it is named here so it is not settled by
accident: **how the CLI reports a malformed document.** `03` reserves exit 4 for *fix the pipeline*
and 1 for *fix the environment*, and a mistyped key is as fix-the-pipeline as a failure gets — but a
`ValidationError` is not a `WeftError`, so today it would reach the CLI's last-resort handler and
exit 1, and the failure-mode ratchet, which derives its required set from `WeftError` subclass
names, cannot see it either. Nothing reaches that path yet, because nothing opens a pipeline file
until the driving use case does. The translation and the manual entry belong to whichever of those
tasks first hands a document to the CLI.

### When resolution fails

Each failure is **its own `WeftError` subclass** under a `PipelineResolutionError` family base, all
carrying the same required fields — the pipeline, the stage ids, the distributions in conflict, and
the remedy. One class per kind rather than one class with a `kind` field, because the failure-mode
ratchet derives its documented set from subclass *names*: a fat class would present one
already-documented name and let a dozen new failure modes ship undocumented, which is the hole that
ratchet exists to close. The CLI maps the whole family to exit code 4 (`03`).

A `(contract, name)` collision is refused at **registration**, naming both distributions and printing
the pin that resolves it. G3 settled that pipelines keep bare names, so the data cannot break the tie
and the operator does, in the file where operator policy already lives:

```toml
# weft.toml
[plugins]
"Enhancer:keybert" = "weft-kw"
```

The displaced registration is recorded and reported by `weft plugins doctor`. This relaxes Phase 0's
blanket refusal rather than tightening a silence, which is the direction `06` required of G2.

> **Narrowed in Phase 1 task 1.12 (2026-08-17), repaired the same day.** A pin's story does not end
> once one real collision is resolved. Two more shapes surface once discovery is otherwise finished,
> and both are refused the same way the registration-time collision above already is — loudly,
> naming what is wrong, never silently honoured and never silently dropped:
>
> - **A pin naming a distribution that did not claim the name.** `[plugins]` names a `(contract,
>   name)` pair and a winning distribution; if neither distribution actually contending for that
>   name is the one the pin names, resolving it anyway would silently start honouring a pin for a
>   pack that never contended. In short: a pin naming a distribution that did not claim the name
>   must fail loudly rather than being ignored, because an inert pin is a lie about what is running.
>   `weft_kernel.registry.UnresolvedPluginPinError`.
> - **A pin for a pair that has no collision at all** — the name was never claimed twice, or never
>   claimed at all, so nothing ever needed arbitrating. In short: a pin for a pair that has no
>   collision must fail loudly too, rather than being read as a harmless no-op — an inert pin is a
>   lie about what is running whether or not it ever had a fight to arbitrate. Checked once
>   discovery finishes enumerating every pack, rather than folded into any one pack's own report,
>   since it is not one pack's failure: `weft_kernel.discovery.InertPluginPinError`.
>
> Both read `[plugins]` from the same `weft.toml` that already carries `[packs] allow`, and neither
> is read by the kernel. In short: the pin is read by the operator-policy loader in weft-cli, never
> by the kernel — `weft_cli.registry_bootstrap` is that loader, on the identical split *One model,
> two directions* below already states for the pipeline document itself, extended here to the file
> the pin lives in.
>
> **Repaired the same day, after review.** `InertPluginPinError` shipped unconditionally fatal to
> every registry-needing command, `weft plugins doctor` and `weft plugins list` included — the two
> commands whose whole job is explaining what discovery found, one of which
> `manual/troubleshooting.md`'s own remedy for this error named as the next thing to run. Fixed by
> `weft_kernel.discovery.discover`'s `strict_pins` parameter: `weft_cli.cli.dispatch` passes
> `strict_pins=False` only for those two commands, so an inert pin no longer stops either from
> reporting what it found — `Registry.unconsulted_pins()` is unaffected either way, and
> `weft plugins doctor` now prints it as its own loud block when it is not raised.

> **Narrowed in Phase 1 task 1.13 (2026-08-17) — the audit this section's own rule asks for.**
> Two gaps, neither a reversal of anything settled above. First, `weft_kernel.runner.Runner.
> resolve` — the explicit `StageSpec`-list mechanism `06` step 6 built, before this section's
> `extends`/operators/slots existed to resolve a *document* against — raised the bare
> `PipelineResolutionError` family base directly for three of its four checks, told apart only
> by reading the message: exactly the fat-class shape this section's own rule rules out, one
> module over from where `weft_kernel.resolution.resolve` had already solved it correctly.
> Fixed by moving `UnmetRequiresError`, `StageCompositionError` and `IntactViolationError` to
> `weft_kernel.runner` (`weft_kernel.resolution` now imports rather than re-declares them) and
> raising the specific class at both of `Runner.resolve`'s and `resolve()`'s call sites — one
> class per kind, shared correctly across the two mechanisms that both need it, rather than two
> classes coincidentally sharing three names or one class covering four kinds under one name.
>
> Second, "all carrying the same required fields" was true only of each subclass's *message* —
> the four facts were readable by a person, not by a caller without parsing English. Every
> `PipelineResolutionError` subclass now carries `pipeline`, `stages`, `distributions` and
> `remedy` as real, structured attributes on the family base itself, populated at every raise
> site; `pipeline` is `None` and `stages`/`distributions` are `()` wherever a failure genuinely
> has none to name (an anonymous `StageSpec` list has no pipeline name at all; a cycle has no
> distribution in conflict), the identical honest-absence reasoning this section already gives
> `UnknownParentPipelineError`'s "no stage ids and no distribution to name" — never a fabricated
> placeholder. The CLI mapping this section states — "the whole family maps to CLI exit code 4" —
> is now one function, `weft_cli.exit_codes.exit_code_for`, rather than duplicated by hand inside
> two command handlers; see `03`'s own narrowing note for what that closes.

**The stage payload's type model is `G5`**, settled separately; it is the hardest question in the
design and defaulting it would have been a mistake.

## 4. Add-ons — driving use case B

> *"I need to add graph — a simple and independent add-on, easily plugged into the system."*

The graph pack, complete:

| It registers | Against contract | Effect |
|---|---|---|
| Entity and relation extractor | `Enhancer` | Usable as a stage in any pipeline |
| Graph store | `Store` | Sits beside the vector store |
| Graph-walk retriever | `Retriever` | Selectable by any retrieval strategy |
| `weft graph build`, `weft graph show` | `Command` | Appear in `--help` and REPL completion |
| A named pipeline, and a slot contribution | — | Ships a ready-made derived pipeline users can extend further, and contributes into any pipeline that declares the slot it targets. Never rewrites a pipeline that did not opt in — §3, *Slots* |

Install:

```bash
uv add weft-graph
weft pipeline derive kg --from base --insert-after chunk graph.entities
weft index ./docs --pipeline kg
```

Nothing in core changed. Nothing in core knows what a graph is. If the pack is uninstalled, the
`kg` pipeline fails to resolve with a message naming the missing plugin and the pack that provides
it — which is the correct behaviour, and is what "loudly" means in rule 5.

**Deletion, and what the graph owes the corpus.** The table above is what the pack *adds*; G7
(2026-08-21) found what it *owes*. A graph store holds entities and relations derived from nodes,
so when a source is deleted the vector store drops its nodes and the graph keeps every entity
extracted from them — dangling, unreachable, and wrong. The pack therefore registers two more things,
both narrow store-family Protocols (§1), and neither of them a new concept:

| It registers | Against contract | Effect |
|---|---|---|
| The graph store, again | `SourceDeletable` | `weft delete` fans out to it in-command, so the graph loses what the corpus lost — because the `kg` pipeline names it, per §1's *participation follows use* |
| The graph store, again | `Reconcilable` | `repair` drops orphans left by anything the fan-out missed; `full` backfills entities for nodes indexed by a pipeline that had no graph stage, reading the corpus through `ctx.require(NodeStore)` (§1) |

```bash
weft reconcile                       # repair and backfill — a person asked for it
weft index ./more-docs --pipeline kg # repair runs automatically at the end
```

This is what makes G7's answer *"no bus"* honest rather than merely cheap: the graph pack was walked
case by case, and the two cases that looked like they needed one did not. A cross-corpus pass —
entity resolution, community detection — has the runner's `flush()`, which already runs once per
resolved stage at end of run and on cancellation. Shape-level observation has the OTel spans the
registration seam already emits on every call. Only deletion had nothing, and it needed a contract
method, not a mechanism.

**The independence test.** Phase 5 exists to check this honestly: the graph pack is built by
someone who has not worked on the core. If they need a core change, the extension model has a hole,
and finding it that way is much cheaper than finding it after publishing contracts.

> **It ran on 2026-08-22, and it failed — which is the result this section says is worth having.**
> `examples/weft-example-graph` was written with **zero edits under `packages/`**: six extension
> points, one entry point, one `register()`, one settings model, a shipped `kg` pipeline and a slot
> contribution. Then three things it needed did not work, and all three were core's, not the pack's:
> `weft delete` never reached the graph store, `reconcile --mode full` could not be built by a pack
> at all, and `weft example-graph show` printed JSON at a person because the CLI's renderer table is
> first-party. The first two are the two rows immediately above — this section was describing
> behaviour the tree did not have, which is why the ledger's 5.7 entry calls the exit **not met**.
> **G13 settled all three on the same day** (`README.md` → *Decision log*): reach follows use, a
> participant asks through `ctx.require`, and a renderer registers at the seam. The repairs are Phase
> 6 tasks **6.18–6.20**, and **6.21 re-runs this test against the pack** — until then the two rows
> above state what the design promises, not what a `weft delete` in your terminal does today.

**The second add-on G7 produced, and the reason it matters more than its size.** The session brought
an **audit log** as a deliberately awkward capability — something wanting to observe everything,
including runs that never opted into it. Half of that want is refused by §3's rule and stays refused.
The other half turned out to be already built and merely unreachable: the registration seam emits an
OTel span for every plugin call, carrying distribution, contract and plugin, but **nothing in the tree
configured a `TracerProvider`**, so every one of those spans went to the no-op default.

`weft-otel` closes it as an ordinary pack. Its `register()` sets the provider; discovery is eager
(§2), so it runs before any pipeline does. It registers no plugin against any contract, contributes
to no pipeline, and needs no core change — `01`'s rule that *everything that exports a span is a
pack* is not worked around here, it is used.

That is why this pack belongs in this section beside the graph one. The graph pack demonstrates the
extension model on the case it was designed for. `weft-otel` demonstrates it on a case nobody
designed for — a capability that is not a stage, not a store, not a retriever and not a command,
arriving with no extension point of its own and needing none. **An add-on serving the awkward case
through the published model, with no core edit, is a stronger result than a bus would have been**,
and it is Phase 5's exit criterion met early, on the hardest example available.

> **Built in Phase 5 task 5.1d.** `packages/weft-otel/` ships as a first-party pack exactly like any
> other, one `[project.entry-points."weft.packs"]` line, one `register(registrar, settings)`, zero
> lines anywhere under `packages/weft-kernel/`. Its `register()` never calls `registrar.add(...)` —
> there is nothing to buffer, because setting the process's `TracerProvider` is not a capability a
> pipeline selects among. `OtelSettings.exporter` (`NONE`/`CONSOLE`/`OTLP`) governs whether it does:
> `OTLP` is probed and verified together, per §1's rule for a pack with an optional dependency
> (`weft-otel[otlp]`) — checked for the extra being importable and an `endpoint` being configured,
> never for the collector being reachable, the same "connection is lazy" restraint
> `weft_store.pgvector_store` already takes — and falls back to `CONSOLE`, loudly, on stderr, when
> either check fails.
>
> **`exporter` defaults to `NONE`, not `CONSOLE`, and that default was corrected by measurement, not
> chosen twice.** `opentelemetry.trace.set_tracer_provider` succeeds exactly once per process, and
> this repository's own test suite calls `weft_cli.registry_bootstrap.build_dependencies` — the real,
> open-by-default discovery path — from dozens of existing tests with nothing to do with tracing.
> A `CONSOLE` default let whichever of those a given `pytest tests -q` process happened to run first
> claim the provider slot for good, non-deterministically defeating
> `tests/unit/weft_kernel/test_seam_trace_visibility.py`'s own SDK-configured exporter later in the
> same process — `docs/lessons.md` L5.1's own shape one level up, caught the same way L5.1 was: by
> running it, not by asserting it worked. `NONE` makes installing `weft-otel` necessary but not
> sufficient; `weft plugins doctor`'s `tracing:` line — assembled in `weft-cli`, from
> `opentelemetry.trace.get_tracer_provider()`, pack-agnostically, after discovery has run, since
> nothing on a `PackReport` can carry a fact `register()` decided before the report exists — says so
> plainly when it is not yet done, and says what set it when it is, whoever set it.
>
> **This narrows what the task line above literally asks for** — "`weft-otel` sets the
> `TracerProvider` in `register()`" reads as unconditional, and `register()` now only does that once
> a `weft.toml` says to. Recorded here rather than left implicit because the narrowing is not only a
> test-suite accommodation: a pack that silently redirected a process-global provider the moment it
> was installed is exactly §3's *slot* rule broken by a quieter route — a contribution reaching
> somewhere without anyone opting in — and G3's *installed-and-ambient* threat in miniature, the gap
> between "a pack you chose" and "a pack whose effect you did not." `weft-graph`'s own `endpoint`
> needing a `weft.toml` entry before it dials a real Neo4j instance is the identical shape one layer
> down; `weft-otel` needing one before it touches a process-wide singleton is the same shape at the
> layer this session's audit-log question was actually about.

## 5. Why this survives where a hand-wired registry did not

| A known failure mode | What prevents it here |
|---|---|
| A chunker factory reached via function-local imports on the production path, with no published extension point behind it | Plugins are discovered, never constructed by a hand-written factory |
| A capability enum plus five more structures across three files plus a separate extension list | Capability metadata is declared on the plugin. There is no second list |
| A closed enum used as the **key type** of a builder registry — hard-closed at the type level, which is worse than a string key and which no grep can see | Fitness function 4 **clause (b)**: `set(valid_names) == set(registry.keys())` asserted at every selection surface, as a runtime property |
| A 10-member "valid names" enum declared in a different module from the registry it is meant to mirror, kept in sync by hand, with no test asserting it | Fitness function 4 clause (a). And the rule behind it: valid names *are* the registry's keys |
| A capability enum in front of a dispatch map, with three formats bypassing the map entirely through an `if` chain | Same runtime property — an `if` chain over literals is a registry with the registration removed |
| An unknown strategy silently becomes a fixed default — **four sites**, not one: an exception handler that falls back to it, a dedicated default-lookup function, a `.get(key, default)` call, and a total parse failure that falls through to the same default | Rule 5, and resolution failing at load rather than at use |
| **A registered third-party strategy that can never run.** A plugin registered through a decorator *is* registered, *is* listed by an introspection function, *is* described to an LLM in a routing prompt — and hits three walls: the enum coercion above, a response validator hard-rejecting non-enum values, and a hard-coded 10-branch selector assigning literal enum members with no plugin branch | Fitness function 4 clause (b), which is the only one of the checks that catches wall three. This row is the sharpest statement of this document's thesis: **registration is not reachability** |
| Nothing **discoverable** from outside the package. One axis (enhancers) is otherwise fully open — a decorator-based registration works end to end already, complete with a lookup function and a factory — and lacks only the import trigger | Entry points, tested by the Phase 0 exit criterion. That enhancer axis is the proof that decorator + lazy bootstrap + loud lookup suffices *once discovery exists*, so discovery is the only genuinely new mechanism |
| Built-ins using internal paths the public API lacked — three indexing builders re-wrapped and re-assigned *after* registration to add span wrapping, so a plugin using the public decorator silently gets less observability | Fitness function 2, as a **runtime** check |

Every row is a real defect found in shipped code, paired with a mechanism rather than an intention.
That pairing is the difference between this document and an architecture document that only
describes the same goals without enforcing them.

> **Four rows were sharpened rather than replaced, and one row is new, on closer inspection.** The
> corrections: the default-coercion row is **four sites** (an earlier pass located only one); the
> capability-enum cluster is six structures across three files, not four maps; the closed-enum-as-key
> row needed re-attributing, since fitness function 4 as originally worded could not have caught it —
> there is no shadowing to grep for; and "nothing extensible from outside the package" is true of
> *discovery* but not of the enhancer axis, which matters because driving use case A runs through
> exactly that axis. The new row — a strategy that registers and can never execute — is the sharpest
> single finding to come out of that review.
