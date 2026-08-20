"""A stranger's evaluation pack — the independence proof, as an artifact.

`docs/build-ledger.md` task 4.1, on `examples/weft-example-chunker`'s own footing: a pack that
lives *outside* the `weft` repository's workspace, in its own directory with its own
`pyproject.toml`, installed the same way any third-party pack would be, registering one plugin
through the same `weft.packs` entry point every first-party pack uses — no shortcut, no private
import path.

`weft`'s `tests/architecture/test_ff9c_every_contract_has_a_stranger.py` installs this
distribution into a throwaway environment built from wheels, with the `weft` repository itself
nowhere on `sys.path`, and confirms it registers a name under
`weft_eval.contract.GenerationMetric` — proving fitness function 9(c) for the contract task 4.1
publishes.
"""

from pydantic import BaseModel, ConfigDict

from weft_eval.contract import GenerationMetric
from weft_example_metric.exact_match import ExactMatch, ExactMatchConfig
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `ExactMatch` as `"example-exact-match"` for `GenerationMetric` — the only plugin
    here."""
    del settings
    registrar.add(GenerationMetric, "example-exact-match", ExactMatch)


__all__ = ["ExactMatch", "ExactMatchConfig", "Settings", "register"]
