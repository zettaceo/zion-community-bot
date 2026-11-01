"""Detect a pasted wallet recovery phrase without any surrounding label.

A member who does not know what a seed phrase is will paste "the 12 words I
got when I created the wallet" with no "seed phrase:" label. Twelve or more
consecutive words from one official BIP-39 list are treated as a wallet
secret. Ordinary sentences rarely qualify: articles, prepositions and most
verbs ("the", "de", "que", "a") are not in any list.

Wordlists: github.com/bitcoin/bips/tree/master/bip-0039, pinned by SHA-256.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import re
import unicodedata

_DIR = Path(__file__).resolve().parent / "bip39"
_PINNED = {
    "english": "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda",
    "portuguese": "2685e9c194c82ae67e10ba59d9ea5345a23dc093e92276fc5361f6667d79cd3f",
    "spanish": "46846a5a0139d1e3cb77293e521c2865f7bcdb82c44e8d0a06a2cd0ecba48c0b",
}
MIN_WORDS = 12


def _fold(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value)
                   if not unicodedata.combining(c)).casefold()


@lru_cache(maxsize=1)
def wordlists() -> tuple[frozenset[str], ...]:
    lists = []
    for name, digest in _PINNED.items():
        raw = (_DIR / f"{name}.txt").read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError(f"bip39 wordlist integrity failure: {name}")
        words = frozenset(_fold(w) for w in raw.decode("utf-8").split())
        if len(words) != 2048:
            raise RuntimeError(f"bip39 wordlist size failure: {name}")
        lists.append(words)
    return tuple(lists)


def looks_like_bare_mnemonic(text: str) -> bool:
    """True for >= 12 consecutive words of one BIP-39 list.

    Numbering and punctuation between words ("1. abandon 2. ability") are
    ignored, so a list copied from a wallet backup screen still matches.
    """
    words = re.findall(r"[a-z]+", _fold(text or ""))
    if len(words) < MIN_WORDS:
        return False
    for wordlist in wordlists():
        run = 0
        for word in words:
            run = run + 1 if word in wordlist else 0
            if run >= MIN_WORDS:
                return True
    return False
