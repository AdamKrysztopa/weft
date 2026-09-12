"""Weft assembled, without a driving adapter — what `weft_cli` calls and an application may.

`docs/03-cli.md`:9 says *"The CLI is a driving adapter and holds no logic. Every operation it
performs is a library call that a FastAPI route could make identically."* That was a claim about
where the logic conceptually belongs, and until ledger task **24.1** it was not a fact about where
the logic lived: discovery, `weft.toml` parsing, pack settings, service selection, the role table,
the permission policy and the reconcile policy were all modules of `weft_cli`, so the only way to
assemble Weft was to import the package named for the terminal. `12-roadmap.md` §5b names that
exactly — *"it is assembled **inside** `weft_cli`, which is the accident this phase corrects"* — and
this module is the correction: eight modules moved here unchanged, and `weft_cli` became one of
their callers rather than their home.

**What is here and what is not.** Here: everything needed to turn a `weft.toml` and a set of
installed packs into a `Dependencies` — the registry, the `PackReport`s, the `ServiceSelection`,
the `RoleTable`, the `LLMSection`, the `PermissionPolicy`, the `ReconcilePolicy` and the token
sink. Not here: anything that decides what a *person at a terminal* sees or how a process exits.
`weft_cli.render`, `weft_cli.exit_codes`, `weft_cli.confirm`, `weft_cli.repl` and the `Command`
implementations stay where they are, and the dividing question is the one `03`:9 asks — *could a
FastAPI route make this call identically?*

Two edges were inverted rather than carried, because each was that question answered wrongly:

- **`build_dependencies` no longer registers renderers.** It called
  `weft_cli.render.register_renderers_from_reports` through a local import; a renderer is
  presentation a library caller never asks for, so the CLI now makes that call itself once
  `build_dependencies` has returned. A `Dependencies` is the same object either way.
- **`ExitCode` is imported from `weft_command.render`, its actual home since G13 (task 6.20).**
  `weft_cli.exit_codes` only ever re-exported it, for the reason that module's own docstring
  gives: a pack implementing `Command` must not depend on `weft-cli` to name an exit code. The
  same argument applies here and had the same one-line answer.

**Not a pack.** No `weft.packs` entry point, no `register()`, no plugin of its own — it registers
nothing and contributes to no pipeline, so `plugins doctor` has no row for it and
`docs/02-extension-model.md` §2's status vocabulary gains no member. It ships inside the
`weft-rag` wheel like every other first-party module (G19); a second distribution for it would be
the third published name that decision closed.
"""
