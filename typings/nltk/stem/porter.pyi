"""Minimal type stub for `nltk.stem.porter`, the same problem `typings/rouge_score` and
`typings/bert_score` already solve: `nltk` ships no `py.typed` marker, which strict pyright
refuses at the `import` line under `reportMissingTypeStubs`. Covers only the surface
`weft_eval.lexical` calls.
"""

class PorterStemmer:
    def stem(self, word: str, to_lowercase: bool = ...) -> str: ...
