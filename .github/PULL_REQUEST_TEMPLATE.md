## What and why

<!-- The diff says what changed. Say why it changed. -->

## Decisions

<!-- Delete what does not apply. -->

- [ ] This touches **no** architecture gate.
- [ ] This implements a **settled** gate: <!-- G? --> — and matches what the document says.
- [ ] This touches an **open** gate: <!-- G? --> — and there is an issue discussing it, because
      defaulting an open decision is what the gates exist to prevent.
- [ ] This **reopens** a settled decision. The decision-log row is set to Reopened with a date and a
      reason, and the downstream checklist items it invalidates are un-ticked.

## Checks

- [ ] `uv run poe ci-checks` is green.
- [ ] Any new architecture check is in the `ci-checks` composite (fitness function 0 will fail
      otherwise).
- [ ] No waiver constant was loosened. If one was, the reason is in the body above.
- [ ] Documents that own the changed content are updated in this PR.
- [ ] Claims about the reference carry `path:line` evidence.
- [ ] **Nothing was copied.** No source text from `a prior project` or any other codebase — no function
      body, docstring, comment, prompt string, word list, regex or test fixture. Anything the reference
      informed was read, understood, and written fresh for Weft.
