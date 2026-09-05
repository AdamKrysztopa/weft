# weft-rag

Weft — a RAG engine built as a microkernel. This is the default install: the packs that index a
directory and answer a question about it, and the `weft` command.

**The distribution is `weft-rag`; the command is `weft`** — the name `weft` belongs to an unrelated
project on PyPI, so what you install and what you run are spelled differently:

```bash
uvx --from weft-rag weft --help
```

## What is in it, and what is not

Twelve packs ship here and each keeps its own identity: `weft plugins list` prints one row per pack,
and `weft.toml` configures one at a time — `[packs.store]`, not `[packs.weft-rag]`.

Five distributions publish **beside** this one, and each is separate because it carries a dependency
you may want to decline:

| | |
|---|---|
| `weft-kernel` | the registry, discovery, the pipeline model and the payload types. Depends on `pydantic` and `opentelemetry-api` and nothing else, and installs and imports alone — which is what proves the kernel names no capability |
| `weft-openai` | an `Embedder` and an `LLMProvider` against the OpenAI API. Needs `openai` and a credential |
| `weft-pdf` | two PDF extraction backends. Needs `pypdf` and `pdfplumber` |
| `weft-qdrant` | a Qdrant store backend, beside the pgvector one shipped here. Needs `qdrant-client` |
| `weft-otel` | sets the OpenTelemetry TracerProvider the registration seam already emits spans into. Needs `opentelemetry-sdk` |

None of the four add-ons is needed to index a directory and query it. A pack neither we nor you
wrote installs beside this one on exactly the same terms and is discovered the same way, with no
edit to anything here — that is the extension model, not a courtesy.

See `docs/09-release.md` §1 for why this is one wheel rather than fourteen.

## What installing this trusts

**A pack runs with your full privileges, and installing one is trusting it.** Weft discovers packs
through Python entry points and calls their `register()` in this process, so a pack can do anything
the interpreter can do. That is stated rather than mitigated, because the mitigations are not
available: **signature verification, sandboxing, per-pack privilege separation, and any defence
against a pack that is hostile once running are all out of reach without a process boundary**,
which Weft does not have.

What Weft does give you is visibility and refusal, not containment:

- `weft plugins doctor` names every distribution that is installed, at what version, and what each
  one *discloses* about the network, filesystem and subprocess access it uses. A disclosure is what
  the pack says about itself; nothing checks it.
- `[packs] allow` in `weft.toml` is an exhaustive pin. Anything not listed is **never imported** —
  refusal before any of its code runs, which is the one control that does work without a process
  boundary.

A control that looked like enforcement but was not would be worse than an acknowledged gap, because
people build policy on it. `docs/02-extension-model.md` §2 is the argument in full.
