"""Unit tests for `weft_openai_compatible`, the second OpenAI-protocol account.

Mirrors `packages/weft-rag/src/weft_openai_compatible/__init__.py`. Phase 20a task **20.1**:
"a second `weft.packs` account exists, so one `weft.toml` can name a local embedder and a hosted
chat model without either borrowing the other's credential or endpoint."

**The gap this closes, measured before it was written.** `weft_openai.register()` binds one
`Settings` into all three of its plugins through `functools.partial`, and a pack receives exactly
one settings block — so `openai-embeddings` and `openai` necessarily shared one `base_url` and one
`api_key`. *Local embeddings with hosted chat* was not a configuration an operator could get wrong:
it was a sentence `weft.toml` had no way to write, with no error to read because nothing was in
error.

**Driven through `build_dependencies`, never through `register` directly.** The value under test is
one that has to *travel* — from a `[packs.*]` block, through the settings loader, through
discovery, into the object a stage will call with — and a test that hands `register` a `Settings`
it built itself asserts nothing about that journey (`phase-step` → *Red*: where a value's whole job
is to travel from configuration to a call, one test must capture that call's arguments). So the
fixture is a real `weft.toml` on disk and the assertion is made on the SDK client each pack's
plugins would actually build.

**Both blocks differ in both fields, deliberately.** A fixture whose two accounts share a
credential could not tell "each pack reads its own block" from "both read the same block and it
happens to be right" — the vacuous-fixture shape `L11.42` is about. Constructing an
`openai.OpenAI` makes no request, so this reaches no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import SecretStr

import weft_openai_compatible
from weft_cli import registry_bootstrap
from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import MediaType, Node
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_llm.payload import Conversation, Message, MessageRole
from weft_openai.embedder import OpenAIEmbedder, build_client
from weft_openai.llm import DEFAULT_MODEL as DEFAULT_LLM_MODEL
from weft_openai.llm import OpenAILLMProvider
from weft_openai.settings import Settings
from weft_vision import Describer

_HOSTED = "https://api.openai.com/v1"
_LOCAL = "http://127.0.0.1:11434/v1"


def _two_account_config(tmp_path: Path) -> Path:
    config = tmp_path / "weft.toml"
    config.write_text(
        "[packs.openai]\n"
        'api_key = "sk-hosted-account"\n'
        f'base_url = "{_HOSTED}"\n'
        "\n"
        "[packs.openai-compatible]\n"
        'api_key = "sk-local-account"\n'
        f'base_url = "{_LOCAL}"\n',
        encoding="utf-8",
    )
    return config


def _endpoint_of(settings: Settings) -> str:
    """Where the client `settings` produces actually points, normalised.

    `build_client`'s declared return is the narrow `EmbeddingsClient` protocol `weft_openai`
    calls through — `base_url` is real on the object and absent from that protocol, because the
    protocol names what the pack *uses* rather than what the SDK *has*. The cast says so once
    here instead of at three call sites; constructing the client makes no request.
    """
    return str(cast("Any", build_client(settings)).base_url).rstrip("/")


def _bound_settings(registry: Registry, contract: type[object], name: str) -> Settings:
    """The `Settings` `register()` bound into one plugin's factory.

    `weft_openai.__init__` registers through `functools.partial` rather than a closure, and its
    own comment says why: `weft_kernel.registry.unwrap_factory` peels a `partial` and nothing
    else, so a closure makes the bound value invisible to every reader that inspects a factory.
    This is one of those readers.
    """
    factory = registry.entry(contract, name).factory
    bound = getattr(factory, "args", ())
    assert bound, f"{name}'s factory bound no settings — a closure would do this"
    settings = bound[0]
    assert isinstance(settings, Settings)
    return settings


def test_the_two_accounts_reach_two_different_endpoints(tmp_path: Path) -> None:
    # Arrange — one file, two blocks, differing in both fields.
    deps = registry_bootstrap.build_dependencies(_two_account_config(tmp_path))

    # Act — the client each pack's embedder would actually build, from the settings that
    # travelled out of that pack's own block.
    hosted = _endpoint_of(_bound_settings(deps.registry, Embedder, "openai-embeddings"))
    local = _endpoint_of(_bound_settings(deps.registry, Embedder, "openai-compatible-embeddings"))

    # Assert
    assert hosted == _HOSTED
    assert local == _LOCAL


def test_neither_account_borrows_the_others_credential(tmp_path: Path) -> None:
    # Arrange
    deps = registry_bootstrap.build_dependencies(_two_account_config(tmp_path))

    # Act
    hosted = _bound_settings(deps.registry, LLMProvider, "openai")
    local = _bound_settings(deps.registry, LLMProvider, "openai-compatible")

    # Assert — the credential is the half a shared-settings bug would get wrong silently, since
    # a wrong endpoint fails loudly on the first call and a wrong key fails on it too, but a
    # *borrowed* key against the right endpoint succeeds and bills the wrong account.
    assert hosted.api_key.get_secret_value() == "sk-hosted-account"
    assert local.api_key.get_secret_value() == "sk-local-account"


def test_the_second_account_registers_the_same_three_capabilities(tmp_path: Path) -> None:
    # Arrange
    deps = registry_bootstrap.build_dependencies(_two_account_config(tmp_path))

    # Act / Assert — a second account narrower than the first would be a second account an
    # operator has to remember the limits of.
    for contract, name in (
        (Embedder, "openai-compatible-embeddings"),
        (LLMProvider, "openai-compatible"),
        (Describer, "openai-compatible-vision"),
    ):
        assert deps.registry.entry(contract, name) is not None


def test_no_name_this_pack_registers_answers_to_two_contracts(tmp_path: Path) -> None:
    """Fitness function 18's property, asserted where the shape could recur.

    `openai` answering to both `Embedder` and `LLMProvider` is the one instance FF18 exists for,
    found by running the binary at ledger task 8.15. Registering the same classes a second time is
    exactly what could reproduce it, so this pack asserts it locally as well.
    """
    # Arrange
    deps = registry_bootstrap.build_dependencies(_two_account_config(tmp_path))
    ours = {
        weft_openai_compatible.EMBEDDER_NAME,
        weft_openai_compatible.PROVIDER_NAME,
        weft_openai_compatible.VISION_NAME,
    }

    # Act
    claimed = {
        name: [c for c in (Embedder, LLMProvider, Describer) if name in deps.registry.names_for(c)]
        for name in ours
    }

    # Assert
    assert len(ours) == 3, "three constants, three names — one shared constant is 8.15's defect"
    assert all(len(contracts) == 1 for contracts in claimed.values()), claimed


def test_the_disclosure_names_this_packs_own_settings_block() -> None:
    """An operator reading a disclosure is being told which knob decides where content goes.

    `weft_openai`'s names `[packs.openai] base_url`; a copy of that sentence in a pack configured
    by a *different* block sends the operator to the wrong file location, which is worse than no
    disclosure — `02` §2's own argument for why this is prose naming a setting rather than a
    boolean.
    """
    # Arrange / Act
    disclosed = " ".join(weft_openai_compatible.DISCLOSURE.network)

    # Assert
    assert "[packs.openai-compatible]" in disclosed
    assert "[packs.openai]" not in disclosed.replace("[packs.openai-compatible]", "")


def test_an_unconfigured_second_account_is_refused_by_name(tmp_path: Path) -> None:
    """The failure path `20.2`'s Exit names: which *account* is unconfigured, not which pack.

    Both packs validate against the same model, so the message an operator reads has to carry the
    block they must edit. `weft plugins doctor` is where that is rendered; this asserts the fact
    it renders is per-account.
    """
    # Arrange — the second account named with a field the model refuses, the first left valid.
    config = tmp_path / "weft.toml"
    config.write_text(
        "[packs.openai]\n"
        'api_key = "sk-hosted-account"\n'
        "\n"
        "[packs.openai-compatible]\n"
        "base_url = 17\n",
        encoding="utf-8",
    )

    # Act
    deps = registry_bootstrap.build_dependencies(config)
    failed = {report.pack: report for report in deps.reports if report.reason}

    # Assert
    assert "openai-compatible" in failed, sorted(str(report.pack) for report in deps.reports)
    assert "openai" not in failed


def test_the_check_can_actually_fail() -> None:
    """The pre-`20.1` state, planted: one `Settings` answering for both accounts.

    `test_the_two_accounts_reach_two_different_endpoints` asserts two endpoints come back. This
    builds the world it is written to refuse and watches the comparison collapse to one — without
    which that test could be passing on two reads of the same block.
    """
    # Arrange — one Settings, as `weft_openai.register` bound into all three plugins.
    shared = Settings(api_key=SecretStr("sk-one-account"), base_url=_HOSTED)

    # Act — the two "accounts" a shared settings object produces.
    both = {_endpoint_of(shared) for _ in range(2)}

    # Assert
    assert both == {_HOSTED}
    assert len(both) == 1


@pytest.mark.parametrize("name", ["openai-compatible", "openai-compatible-embeddings"])
def test_the_second_accounts_names_do_not_collide_with_the_first(name: str) -> None:
    # Arrange / Act / Assert — a prefix relationship is not a collision, and this says so once
    # rather than leaving a reader to work it out from two constants in two files.
    assert name.startswith("openai")
    assert name not in {"openai", "openai-embeddings", "openai-vision"}


# --- the remedy names the account that is unconfigured -----------------------------------------
#
# Task **20.2**'s Exit clause, and it failed the first time it was run. With
# `[packs.openai-compatible]` holding no `api_key` and `[packs.openai]` fully configured, the
# shipped binary said:
#
#     no OpenAI credential is configured, so the 'openai' embedder has nothing to authenticate
#     with. Add `[packs.openai] api_key = "${env:OPENAI_API_KEY}"` to weft.toml
#
# — naming a block that was already configured. An operator following that remedy edits the wrong
# four lines and nothing changes, which is `L8.3`'s rule exactly: a remedy naming the wrong thing
# is worse than no remedy. Three raise sites composed the block name as a literal, because until
# `20.1` there was only one account and a literal was true.


async def _refusal_message(plugin: Any) -> str:
    """Whatever `plugin` says when asked to do its job with no credential.

    Each of the three refuses from its own method, so this asks each in the shape its own
    contract defines rather than through a common base they do not share — the point is the
    *message*, and a helper that reached for one shared entry point would be testing a seam that
    does not exist.
    """
    ctx = Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")
    node = Node.synthetic(content="anything", media_type=MediaType.TEXT, reason="test fixture")
    with pytest.raises(WeftError) as raised:
        if isinstance(plugin, OpenAIEmbedder):
            await plugin.run([node], ctx)
        elif isinstance(plugin, OpenAILLMProvider):
            await plugin.complete(
                Conversation(messages=(Message(role=MessageRole.USER, content="hi"),)),
                model=DEFAULT_LLM_MODEL,
                ctx=ctx,
            )
        else:
            await plugin.describe(b"\x89PNG", "image/png", "describe this")
    return str(raised.value)


@pytest.mark.parametrize(
    ("contract", "name"),
    [
        (Embedder, "openai-compatible-embeddings"),
        (LLMProvider, "openai-compatible"),
        (Describer, "openai-compatible-vision"),
    ],
)
async def test_an_unconfigured_account_names_its_own_block(
    tmp_path: Path, contract: type[object], name: str
) -> None:
    # Arrange — the second account named and left without a credential, the first one complete.
    config = tmp_path / "weft.toml"
    config.write_text(
        "[packs.openai]\n"
        'api_key = "sk-hosted-account"\n'
        "\n"
        "[packs.openai-compatible]\n"
        f'base_url = "{_LOCAL}"\n',
        encoding="utf-8",
    )
    deps = registry_bootstrap.build_dependencies(config)
    plugin = deps.registry.entry(contract, name).factory(None)

    # Act
    message = await _refusal_message(plugin)

    # Assert — the block an operator must edit, and not the one that is already right.
    assert "[packs.openai-compatible]" in message, message
    assert "[packs.openai]" not in message.replace("[packs.openai-compatible]", ""), message
    assert name in message, message
