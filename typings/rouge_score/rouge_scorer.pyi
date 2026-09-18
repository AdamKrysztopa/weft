from collections.abc import Iterable
from typing import Protocol

class Score:
    precision: float
    recall: float
    fmeasure: float

class _Tokenizer(Protocol):
    def tokenize(self, text: str) -> list[str]: ...

class RougeScorer:
    def __init__(
        self,
        rouge_types: Iterable[str],
        use_stemmer: bool = ...,
        tokenizer: _Tokenizer | None = ...,
    ) -> None: ...
    def score(self, target: str, prediction: str) -> dict[str, Score]: ...
