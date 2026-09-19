# Oracle anchors — the labelling rubric (ledger 40.5)

Written before any label exists and before any promotion result, as `protocol.toml` requires. A
labeller sees **only the question text** — never its relevant documents, the pool, or what the
rule extractor found.

## What an anchor is

A span of the question, copied exactly as the question spells it, that a document answering it
would have to contain literally and that tells it apart from documents about the same subject:

- a model, part, product or build number (`AX6000`, `WRH123`, `8.5.5.14`);
- an error, message, fix or advisory code (`SQL30081N`, `CWWKS1100A`, `PI12345`, `CVE-2019-4102`);
- a file, command, flag, property or API name (`db2diag.log`, `-Xmx`, `com.ibm.mq.cfg`);
- a quoted span;
- a named product, brand or edition, when naming it narrows the answer
  (`WebSphere Application Server Liberty`, `Galaxy S21 Ultra`).

## What is not

A word the question uses only to say what it is about (`error`, `install`, `battery`, `cable`),
a measurement that describes rather than identifies (`32MB`, `6 feet`) unless it is part of a
name, and a phrase that paraphrases rather than names. When unsure, leave it out: a false anchor
promotes a sibling, a missing one only leaves dense's order alone.

## Recording

The complete set of anchors for the question, each an exact substring of it, in the order they
appear; an **empty set, stated explicitly**, when the question names nothing. Never an anchor the
question does not literally contain.

## The identifier-exact slice (second pass, after the pools are frozen)

Shown the question, its **whole** relevant set shuffled and the pool's documents from the same
family — same product and problem, another version, CVE or error code — a labeller records
whether an identifier in the question is what decides relevant from sibling (`yes` / `no`).
