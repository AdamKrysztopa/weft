# Security Policy

## Reporting a vulnerability

Report privately through GitHub's **Report a vulnerability** button on the Security tab, or by email
to the maintainer listed in `CODEOWNERS`. Please do not open a public issue.

Include what you did, what happened, and what you expected. A proof of concept helps enormously. You
will get an acknowledgement, and if the report is valid you will be credited in the release notes
unless you ask not to be.

Weft is pre-alpha and unreleased, so there is no supported-version table yet. When there is a
release, this section will name the versions that receive fixes.

## What Weft's plugin model does and does not protect you from

This section exists because the honest answer is unusual, and an unclear one would be worse than
useless.

**Weft loads plugins through Python entry points. A pack runs in your interpreter, with your
privileges, your configuration and your credentials. Installing a pack is trusting it — completely
and irrevocably.** Weft cannot sandbox it. CPython offers no in-process boundary that constrains
file access, sockets or subprocesses, and `sys.audit` hooks are advisory and removable by the code
they audit. Enforcement would require running packs in separate processes, which is not this
architecture.

We say this plainly rather than shipping controls that look like enforcement but are not, because
people build policy on what a tool appears to promise.

**What Weft does do:**

- **Refusal precedes execution.** An allow-list in `weft.toml` is exhaustive when present, and a pack
  it excludes is *never imported* — not imported-then-ignored. A fitness function asserts this with a
  canary distribution that writes a marker at import time.
- **Nothing runs that does not need to.** Discovery happens when a command needs the registry, never
  at process start.
- **Every run records what was in the process.** The set of distributions that executed is recorded,
  so "what code ran during this run?" is always answerable after the fact.
- **`weft plugins doctor` tells you what is loaded, from where, and what is not** — including packs
  that are running but are not direct dependencies of your project, which is the case worth noticing.
- **Packs may disclose what they touch** — hosts, paths, executables. This is documentation, not a
  control: Weft never refuses a pack based on it and never verifies it.

**The threat this model is actually built against** is not the malicious package — if you deliberately
install hostile code, entry points changed nothing. It is *ambient arrival*: a pack you never chose,
pulled in as a transitive dependency of something you did, executing automatically because it
declared an entry point. That is the gap entry points create, and the measures above are aimed at it.

**Explicitly out of scope**, and not quietly hoped for: signature verification, sandboxing, per-pack
privilege separation, and any defence against a pack that is hostile once running. If Weft ever wants
these, it wants an out-of-process pack host, which is a different architecture and would be decided
deliberately.

The full reasoning is in [`docs/02-extension-model.md`](docs/02-extension-model.md) → *The trust
model*.

## Adjacent things worth knowing

- **Command permission classes are guardrails against accidents, not against packs.** A plugin
  command declares `read`, `write`, `overwrite`, `destroy` or `network`, and destructive classes
  prompt. A dishonest pack can declare `read` and delete your collection. See
  [`docs/03-cli.md`](docs/03-cli.md).
- **Secrets are `SecretStr` and come from `${env:VAR}` interpolation performed by the config loader.**
  No component reads the environment itself, and a pack receives only its own settings — never the
  whole configuration.
