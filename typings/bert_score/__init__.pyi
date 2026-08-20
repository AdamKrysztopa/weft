from collections.abc import Sequence

class _Tensor:
    def mean(self) -> float: ...

def score(
    cands: Sequence[str],
    refs: Sequence[str],
    *,
    lang: str = ...,
    verbose: bool = ...,
) -> tuple[_Tensor, _Tensor, _Tensor]: ...
