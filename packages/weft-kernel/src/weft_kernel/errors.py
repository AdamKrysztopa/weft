"""`WeftError` — the root of Weft's error hierarchy.

Specified in `docs/02-extension-model.md` section 1 ("What a plugin
receives"): packs raise subclasses of `WeftError`, which carries a
`transient` marker so a pack can say what is worth retrying — the kernel
runs no retry engine of its own, so a caller deciding whether to retry needs
the pack's opinion, not a guess read off the exception's class name. Every
kernel-raised error is loud and specific: it says what was wanted, why it is
unavailable, and what the valid options are, never the reference's bare
`unknown plugin 'x'`.

**Attribution is data this type carries, not logic it performs.**
`docs/06-phase-0-build.md` step 3 builds the registration seam that catches
whatever escapes a plugin's `run()` and wraps it, naming the pack, contract,
plugin and stage, with `__cause__` preserved so no traceback is hidden. This
step only gives that seam somewhere to put the four names — a plain
`WeftError` raised directly by a pack has no reason to know its own
attribution, and none of the four fields defaulting to `None` is exactly
that: a stage does not know which pack it runs under or which pipeline slot
it fills, and the one place that does is the seam wrapping the call, not the
stage itself.
"""


class WeftError(Exception):
    """Root of Weft's error hierarchy. Every kernel- and pack-raised error is one of these.

    Catching `WeftError` catches everything Weft itself raises, kernel or
    pack, without also swallowing an unrelated `KeyError` or `TypeError` a
    caller would want to see — the catch-specific-exceptions rule applies to
    callers of this library exactly as it applies inside it.
    """

    def __init__(
        self,
        message: str,
        *,
        transient: bool = False,
        pack: str | None = None,
        contract: str | None = None,
        plugin: str | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.transient = transient
        self.pack = pack
        self.contract = contract
        self.plugin = plugin
        self.stage = stage
