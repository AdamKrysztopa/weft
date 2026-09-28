"""The one locale fallback every locale-keyed table in this pack resolves against.

Exact locale, then its primary subtag, then English, then nothing — the same three-step
fallback `weft_prompts.typed_prompt.TypedPrompt` and `weft_retrieve.sufficiency`'s own
`_markers_for` already applied inline; this is that rule named once so a locale-keyed table
gains it by calling `resolve_locale` rather than by copying the three steps again.
"""

from __future__ import annotations

from collections.abc import Iterable


def resolve_locale(locale: str | None, available: Iterable[str]) -> str | None:
    """The key of `available` to read for `locale`: exact, then primary subtag, then `en`.

    `locale=None` is not "no preference among `available`" — it goes straight to `"en"`,
    the same as an asked locale that matches nothing else. Returns `None` when even `"en"`
    is not offered.
    """
    keys = set(available)
    if locale is not None:
        if locale in keys:
            return locale
        primary = locale.split("-", 1)[0]
        if primary in keys:
            return primary
    if "en" in keys:
        return "en"
    return None
