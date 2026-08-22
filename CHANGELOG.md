# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) **per distribution** — `weft`
ships as several packages (`docs/README.md` → *Where things are*), not one, and each carries its own
version, tracked in its own `pyproject.toml`. This file does not repeat those numbers — a second,
hand-copied list of them is exactly the two-lists bug `docs/README.md` opens with, aimed at version
digits instead of prose — it records what changed, and why, for someone using the software.

**Architecture decisions are not changelog entries.** They live in the decision log in
[`docs/README.md`](docs/README.md), which records what was decided, when, and where the reasoning is
written down.

**Nothing has been released to an index.** `docs/09-release.md` §2.2: "No distribution in this
repository has made a 1.0 promise before Phase 6." Every entry below is therefore `[Unreleased]` —
not because nothing has shipped, but because nothing has been published for anyone outside this
repository to pin against yet. This file's own staleness while five phases shipped around it —
nineteen lines, touched in one commit, unmoved since the repository's initialising commit — is
`docs/lessons.md` L5.8, and is why it is checked from Phase 5 on
(`tests/docs/test_changelog_deprecation_coverage.py`) rather than only trusted.

## [Unreleased]

### Added

- **Phase 0 — the walking skeleton.** The kernel (registry, discovery, the pipeline model, the
  payload types), `weft-cli` (the one driving adapter and the one `asyncio.run` in the tree), and
  the first capability packs — `weft-extract`, `weft-chunk`, `weft-store`, `weft-embed` — plus the
  discovery, extension and trust-model fitness functions (0, 1, 3, 8, 9) that keep them honest.
- **Phase 1 — pipelines as data.** The four-operator derivation set, closed by a named constant
  (fitness function 11a — a fifth operator fails the build until someone changes the constant and
  records why), and every shipped pipeline proven to resolve against the installed registry in
  `ci-checks` (fitness function 11b).
- **Phase 2 — retrieval and generation.** `weft-pdf`, `weft-openai`, `weft-retrieve`,
  `weft-generate`, `weft-qdrant`, `weft-llm`, `weft-index` — the retrieval and generation contract
  families, a router that picks a strategy from the registry with no enum and no closed key space
  (fitness function 4), and the filter AST the store contract family speaks.
- **Phase 3 — the command surface.** `weft-command` and the `Command` contract — CLI verbs are
  plugins too, each declaring its own permission `ClassVar` rather than living in a hard-coded list.
- **Phase 4 — evaluation and observability.** `weft-eval` — retrieval and generation metrics,
  persisted `RunRecord`s, `weft eval run`/`compare`/`metrics`, `weft trace`, and a tool that
  generates its own comparison across two derived pipelines run over one corpus.
- **Phase 5 — the extension model (in progress; G7 and G9 settled).** `weft-otel`, setting the
  process `TracerProvider` from a pack with no core edit (5.1d); the store-family
  `SourceDeletable`/`Reconcilable` protocols behind `weft delete` and `weft reconcile`, and the
  `repair`/`full` reconciliation modes a person opts into rather than one that surprises them
  (5.1a–5.1c); fitness function 13, closing a `FilterOp` dispatch gap so an added enum member is
  refused everywhere rather than silently answered as the wrong query (5.2b); mandatory
  `ExtModel.__schema_version__`, so a pack reads back what an older version of itself wrote, or
  refuses by name instead of silently misreading it (5.2c); the structured `--json` error envelope
  carrying a `WeftError` subclass name and `valid_options` as data rather than prose to parse
  (5.2d); `weft plugins doctor` reporting version skew and a deprecated-surface flag, and the
  registration-time deprecation mechanism (`PackRegistrar.deprecate`) behind it (5.2e); this file,
  brought current and checked against that mechanism (5.2f).

### Changed

- `COMMAND_CONTRACT_VERSION` corrected from a mis-recorded `1.1.0` to `2.0.0` — task 3.2 added a
  name to `required_declarations`, which breaks every `Command` implementer that does not declare
  one, and is therefore major for an implementer even though it is additive for a caller
  (`docs/09-release.md` §2.3's two-audience rule).
- Every first-party distribution's declared dependency on another now carries a real range
  (`>=X,<MAJOR+1`), never a bare name or an exact pin (task 5.2a).

### Deprecated

Nothing yet. The mechanism exists (5.2e) and this file's coverage of it is enforced (5.2f); no
first-party surface has used it.
