# Weft

A RAG engine built as a microkernel. The kernel knows nothing about PDFs, chunking, embeddings or
graphs: every capability is a plugin discovered through Python entry points, pipelines are data
derivable from other pipelines, and built-in packs are held to the same public contract as anything
a third party writes.

The warp is the fixed frame on a loom; the weft is every thread through it.

> **Status: Phase 0, not yet built.** Six of ten architecture decisions are settled and the plan is
> complete. What exists here is the repository skeleton and the fitness functions, wired before there
> was anything to check — deliberately, because the project this one replaces shipped an
> architecture checker that was never in its CI task.

## Start here

**[`docs/README.md`](docs/README.md)** is the single source of truth: current phase, settled
decisions, what to do next, and which document owns what. Everything else is reached from there.

| | |
|---|---|
| [`docs/01-high-level-plan.md`](docs/01-high-level-plan.md) | The kernel boundary, async colour, the phase script, the fitness functions |
| [`docs/02-extension-model.md`](docs/02-extension-model.md) | Contracts, the payload model, the store family, discovery and the trust model |
| [`docs/03-cli.md`](docs/03-cli.md) | The command line as the single driving adapter |
| [`docs/04-reference-inventory.md`](docs/04-reference-inventory.md) | What to lift from the reference, what to rewrite, what to leave |
| [`docs/05-grilling-sessions.md`](docs/05-grilling-sessions.md) | The ten decision gates, six closed |
| [`docs/reference/`](docs/reference/) | The frozen audit of the reference codebase, and the review that started this |

## Layout

One repository, several distributions. That is what lets the kernel be verified by installing it
alone and importing it, rather than by a script that walks the source.

```text
packages/weft-kernel     registry, discovery, pipeline model, payload types
packages/weft-cli        the only driving adapter, and the only asyncio.run in the tree
packages/weft-extract    first-party pack: publishes the Extractor contract
packages/weft-chunk      first-party pack: publishes the Chunker contract
packages/weft-store      first-party pack: publishes the Store contract family
testing/weft-canary      test-only distribution, proves refused packs are never imported
tests/architecture       the fitness functions
```

## Development

```bash
uv sync
uv run poe ci-no-tests      # format, lint, types, architecture
uv run poe ci-checks        # the canonical full gate
uv run poe kernel-isolated  # install weft-kernel alone in a clean env and import it
```

Every architecture check must be reachable from `ci-checks`; a test asserts it.

## The reference

`a prior project` is a **parts reference, not a baseline** — a production RAG system whose extension points
were audited in detail before any of this was designed. That audit is frozen in `docs/reference/`, and
the source itself is reached through an untracked `reference` symlink to a sibling checkout. **No build,
test or packaging step reads through it.**

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) — including which architecture decisions are settled and
therefore not up for negotiation in a pull request, and which are open and must not be defaulted.
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) applies everywhere this project goes.

Security reports go through [`SECURITY.md`](SECURITY.md), which also states plainly what the plugin
model does and does not protect you from. The short version: **a pack runs with your full privileges,
and installing one is trusting it.**

## Licence

MIT — see [`LICENSE`](LICENSE).

The reference is Apache-2.0 and copyright STX Next sp. z o.o. That licence travels with any source text
lifted from it, so a file containing copied or adapted reference code is Apache-2.0 material and is
listed in [`NOTICE`](NOTICE). Ideas, designs and measurements taken from the reference study are not
covered by that — copyright does not protect them.
