from collections.abc import Iterable

class Score:
    precision: float
    recall: float
    fmeasure: float

class RougeScorer:
    def __init__(self, rouge_types: Iterable[str], use_stemmer: bool = ...) -> None: ...
    def score(self, target: str, prediction: str) -> dict[str, Score]: ...
