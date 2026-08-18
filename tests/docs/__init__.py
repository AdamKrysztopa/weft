"""The shipped documentation set's checks — `docs/08-manuals.md` §3.

Ordinary tests, not fitness functions: `08` §3's own *decision D1* argues why
— `tests/docs/` inherits reachability from `poe test`, already the last step
of `poe ci-checks`, with no second membership proof to write the way
`tests/architecture/` needed one. Each module still carries the same ratchet
shape `01`'s fitness function 0 uses: a named waiver constant, pinned empty
(or holding only a documented, visible exception), and a floor that must be
non-trivially true before the comparison it protects can even run.
"""
