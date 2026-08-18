"""The Weft kernel.

What belongs here is settled in G1 and specified in `docs/01-high-level-plan.md`
under *The kernel boundary*: the kernel is what is required to express, load and
run contracts it knows nothing about, plus the domain types those signatures
unavoidably name — and nothing in the kernel performs RAG work.

Deliberately empty until Phase 0. Its two dependencies, `pydantic` and
`opentelemetry-api`, are declared and enforced by fitness function 1.
"""
