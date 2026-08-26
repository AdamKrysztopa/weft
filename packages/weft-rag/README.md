# weft-rag

The Weft release set: one exactly-tested combination of the distributions that make up Weft.

This distribution ships no code. Installing it installs the product — including `weft-cli`, which
provides the `weft` command. **The distribution is `weft-rag`; the command is `weft`** — the name
`weft` belongs to an unrelated project on PyPI, and the console script is `weft-cli`'s:

```bash
uvx --from weft-rag weft --help
```

A pack that is not in this set installs beside it and is discovered the same way, with no edit to
anything here. See `docs/09-release.md` §1 for why the unit of release is a named set rather than a
single wheel.

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
