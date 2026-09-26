# Dispatching a red writer

Read this when a task's failing tests are written by a dispatched agent rather than by you. The
dispatch prompt points the agent here and adds the ledger line, the owner's settled direction and
the patch name (`red-<id>.patch` in the scratchpad). Everything below is the agent's standing brief.

A red writer writes the **failing tests and nothing else**. A `weft-implementer` makes them pass
from a brief, and may not edit a test, so every test is a specification it must satisfy.

## Read first

- `CLAUDE.md`, the settled rules.
- `phase-step` → *Red — you write the test*, whole. Derive expected values from the settled
  documents, never from an example. Vary the dimension under test in the fixture. Give a rendered
  collection at least two entries. Assert the leaf exception class and a fragment of the message's
  claim. Assert an operator-facing fact where the operator reads it: the rendered line and the exit
  code. Copy a seam's double from an existing double of that seam. Give a double of a store method
  the method's whole documented effect.

## Rules

1. **Tests only**, under `tests/` (and `examples/*/tests/` for a stranger pack). Production code
   is touched only by the temporary stubs of rule 3. Never `docs/`, `manual/` or the ledger.
2. **The pin sweep, before writing** (`L28.45`). Grep `tests/` and `examples/` for every pinned set
   the change grows: var lists, exception families (FF12's `NAME_RESOLUTION_FAMILY`,
   `_LOCAL_IMPORT_MEMBERS`), kit check counts, enum value sets, contract-version literals and
   command tables. Update each pin in the patch and list every one checked. Read the *calls* of
   every existing test of the entry point the change touches, and update a superseded test in the
   same patch (`L28.35`).
3. **Stub and run** (`L28.36`). Where a test imports a name that does not exist yet, stub it in the
   production module, run each new test once, and quote the line each one fails on. That line must
   be the test's own assertion, never a collection or fixture error. Then remove every stub.
4. Run named tests only (`uv run pytest <node ids> -q`), never a whole suite or a `poe` gate. Run
   nothing that reaches Postgres or Qdrant unless the dispatch says the container is yours. Never
   print `.env`: export `WEFT_DATABASE_URL` from the dispatch instead.
5. Report `ruff check` and `pyright` over the red files, with errors grouped by the missing symbol
   they name.
6. **Leave the checkout clean.** Write the patch (`git diff -- <tracked files>` plus
   `git diff --no-index /dev/null <new file>` for each new file). Reverse your own edits, confirm
   with `git status --short`, and run `git apply --check` on the patch. Touch no path you did not
   edit.
7. Never `git stash`, `reset`, `checkout --` or `clean`, and never commit.

## Report, in this order

- `Patch:` the path and the files in it.
- `Tests:` every node id, each with its quoted failure line (or "passes: a guard").
- `Already decided:` every production name the tests assert on, derived from the code and cited as
  `path:line "fragment"`. Say plainly what the code does not settle, give the options, and mark one
  as the recommendation.
- `Pins updated:` each pin edited and each pin checked.
- `Callers:` every caller of what the fix changes, and what each will get.
- `Red state:` ruff and pyright over the red files.
- `Owner modules:` the production modules the implementer will edit.
- `## Noticed`: anything wrong and out of scope, one line each, or `nothing`.
