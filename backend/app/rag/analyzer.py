"""Shared, versioned query/source normalization; original source text is never changed."""

import unicodedata

ANALYZER_VERSION = "en-ar-lexical-v1"
_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ـ": ""})


def tokenize(text: str) -> list[str]:
    value = unicodedata.normalize("NFKC", text).casefold().translate(_ARABIC_FOLD)
    tokens, current = [], []
    for char in value:
        # Arabic vocalization/Quranic annotation marks; Latin accents remain significant.
        if unicodedata.category(char).startswith("M") and ("ARABIC" in unicodedata.name(char, "")):
            continue
        if char.isdecimal():
            current.append(str(unicodedata.decimal(char)))
        elif unicodedata.category(char).startswith("L"):
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def index_text(text: str) -> str:
    return " ".join(tokenize(text))
