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


# ── provável seed, mesmo sem ser perfeita ────────────────────────────────────
# Live 2026-11-03: a member pasted 12 bare words with typos, "these are the
# words I got", three times. Exact BIP-39 matching saw nothing and the list
# stayed in the group. Deleting a chat line is cheap; a public seed is not.
LIST_MIN_WORDS, LIST_MAX_WORDS = 11, 25
TYPO_RATIO = 0.75
# Words real seeds practically never carry: two of them mean a sentence.
_FUNCTION_WORDS = frozenset(
    "the and to of is it my your you we this that for with are was have not but i "
    "o os as um uma de do da dos das e que para pra por com em no na nos nas nao eu "
    "voce vc meu minha seu sua ele ela se mas como ja vou foi tem esta aqui agora "
    "el la los las y en para con mi tu es por pero yo".split()
)


def word_list_lines(text: str) -> list[list[str]]:
    """Lines shaped like a recovery phrase: 11-25 bare words, not a sentence."""
    found = []
    for line in (text or "").splitlines():
        if len(re.findall(r"[.,;:!?]", re.sub(r"\b\d+[.)]", " ", line))) > 1:
            continue
        words = re.findall(r"[a-z]+", _fold(line))
        if not LIST_MIN_WORDS <= len(words) <= LIST_MAX_WORDS:
            continue
        if sum(word in _FUNCTION_WORDS for word in words) >= 2:
            continue
        found.append(words)
    return found


def looks_like_mistyped_mnemonic(text: str) -> bool:
    """A list that is mostly one BIP-39 wordlist: a real seed with a few typos."""
    for words in word_list_lines(text):
        for wordlist in wordlists():
            if sum(word in wordlist for word in words) >= TYPO_RATIO * len(words):
                return True
    return False


_LABEL = re.compile(r"\b(?:seed|seeds|semente|semilla|frases?|phrase|palavras?|palabras?|words?|mnemonic\w*|recupera\w*|recovery)\b")
_LABEL_THEN_LIST = re.compile(
    r"\b(?:seed|semente|semilla|frase(?:\s+secreta)?|phrase|palavras|palabras|words)\b"
    r"(?:\s+(?:e|is|es|sao|son|are))?\s*:?\s+(.+)$", re.M)


def word_list_with_label(text: str) -> bool:
    """A bare word list plus words naming it: "<12 words>\\n\\nthese are the words I got".

    A list alone is not enough (it can be a list of coins); the label must be
    OUTSIDE the list line, or lead into it ("minha seed é gap dras ...").
    """
    folded = _fold(text or "")
    lines = folded.splitlines()
    for index, line in enumerate(lines):
        if word_list_lines(line) and any(_LABEL.search(o) for i, o in enumerate(lines) if i != index):
            return True
    return any(word_list_lines(m.group(1)) for m in _LABEL_THEN_LIST.finditer(folded))
