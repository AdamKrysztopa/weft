# weft-kernel

The kernel of Weft, a RAG engine built as a microkernel. This distribution is the registry a pack
registers into, the entry-point discovery that finds packs, the pipeline model a pipeline document
resolves against, the payload types every stage signature names, and the registration seam every
stage's execution passes through. It contains no RAG capability of any kind.

## The one thing that makes it unusual

**The kernel names no capability.** There is no `Extractor`, `Chunker`, `Store`, `Retriever` or
`LLM` in this package — those contracts are published by the first-party packs that own them, in
`weft-rag`, on exactly the same public entry point a third party's pack would use. What ships here
is the mechanism a contract is expressed and run through, never a contract itself.

This is not a design intention stated in a docstring; it is checked. `weft-kernel` is a separate
installable distribution for exactly one reason: `poe kernel-isolated` installs it alone into a
clean environment and imports it, so if anything reached outside what it ships, the import fails.
A static counterpart walks every import in the source tree against the same declared dependency
set. Both are fitness function 1, in `tests/architecture/test_ff1_boundary.py`.

## Dependencies

Exactly `pydantic` and `opentelemetry-api` — that is `packages/weft-kernel/pyproject.toml`'s whole
`dependencies` list, and a third dependency is a decision-log entry, not a line in a pyproject.
`opentelemetry-api` is the no-op-without-an-SDK API; anything that actually exports a span is a
pack's concern (`weft-otel`), not this one's.

## Async only

Every contract method this kernel's types describe is `async def`. There is no sync protocol and
no sync facade anywhere in this package — a stage runs on the event loop, and a categorical
detector installed at the registration seam (`weft_kernel.blocking`) fails the build on a blocking
call made on that thread rather than tolerating one behind a synchronous-looking signature.

## What is actually in here

Twenty modules under `weft_kernel`, none of them a plugin:

- `registry.py` — where a pack's `register()` adds what it provides, and where an unresolvable
  name fails loudly, naming what was wanted and what is registered.
- `discovery.py` — entry-point discovery and the trust model: which installed distributions get
  imported, what a pack may disclose about itself, and the `[packs] allow` pin that refuses an
  import before it happens rather than after.
- `pipeline.py` / `resolution.py` / `runner.py` — the pipeline as authored data, the pipeline
  resolved to a frozen explicit form, and the linear runner that executes a resolved chain.
- `seam.py` — `wrap`, the one seam every stage's call passes through: spans, error attribution,
  `__transient__` stripping and the blocking-call detector attach here, automatically, so no
  author has to remember any of the four.
- `context.py` — the passport every stage receives: tenant, run and trace ids, cancellation,
  locale, and `require()` for an ambient service.
- `payload/` — the domain model a stage signature names: `Node`, `NodeId`, `Lineage`, `MediaType`,
  `Vector`, `Outcome`, `ExtModel`/`ExtMap` (a pack's own namespaced, validated extension data), and
  the `Property` and `Applies` markers a plugin class declares itself against.
- `errors.py` / `fallback.py` / `blocking.py` — the `WeftError` root every pack raises against, the
  fallback-chain combinator that composes plugins over any contract without inspecting them, and
  the blocking-call detector above.

The kernel is also held to a size ceiling: `uv run pytest tests/architecture/test_ff3_kernel_budget.py -s`
measures 3,300 non-blank, non-comment, non-docstring lines against a 3,500-line fail and a
2,800-line review trigger — a stated budget rather than an unstated one, so growth is on the agenda
before it is a crisis.

## You probably do not want this package

If you want to index a directory and ask a question about it, install `weft-rag`, not this. It
depends on `weft-kernel` and brings the packs that do the actual work — extraction, chunking,
embedding, storage, retrieval, generation — plus the `weft` command:

```bash
uvx --from weft-rag weft --help
```

`weft-kernel` exists as its own installable distribution so that fitness function 1 can be a fact
about a clean install rather than a claim about the source tree. Install it directly only if you
are writing a pack against its registry and discovery mechanism and want nothing else on the
import path while you do it.
