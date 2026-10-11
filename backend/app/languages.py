from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEXICON_PATH = ROOT / "data" / "lexicon_hi_kn.json"

_ROMA_HI_KEYWORDS = {
    "kitna", "kitni", "kitne", "bikri", "aamdani", "kamai", "rajasva",
    "khetr", "kshetra", "girawat", "ghata", "badhotari", "badha",
    "timahi", "mahina", "uttar", "dakshin", "poorv", "pashchim",
    "kyun", "dikhao", "batao", "kripya", "hai"
}

_ROMA_KN_KEYWORDS = {
    "eshtu", "marata", "adayam", "pradesha", "ilike", "erike",
    "hecchu", "kadime", "traimasika", "tingalu", "uttara", "dakshina",
    "poorva", "pashchima", "yake", "torisi", "heli", "yenu", "ivathu"
}

_LEXICON_CACHE: dict[str, dict[str, str]] | None = None


def load_lexicon() -> dict[str, dict[str, str]]:
    global _LEXICON_CACHE
    if _LEXICON_CACHE is not None:
        return _LEXICON_CACHE
    if LEXICON_PATH.exists():
        with open(LEXICON_PATH, "r", encoding="utf-8") as f:
            _LEXICON_CACHE = json.load(f)
    else:
        _LEXICON_CACHE = {"hi": {}, "kn": {}}
    return _LEXICON_CACHE


def detect_language(text: str) -> str:
    """Detect whether text is primarily Hindi (Devanagari/romanized), Kannada (script/romanized), or English."""
    if not text:
        return "en"

    # Count script characters
    hi_count = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    kn_count = sum(1 for c in text if "\u0C80" <= c <= "\u0CFF")

    if hi_count > 0 or kn_count > 0:
        if hi_count >= kn_count:
            return "hi"
        return "kn"

    # Check for romanized words
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z]+", text)]
    hi_matches = sum(1 for t in tokens if t in _ROMA_HI_KEYWORDS)
    kn_matches = sum(1 for t in tokens if t in _ROMA_KN_KEYWORDS)

    if kn_matches > hi_matches and kn_matches > 0:
        return "kn"
    if hi_matches > 0:
        return "hi"

    return "en"


def normalize_with_lexicon(text: str) -> str:
    """Normalize Hindi or Kannada terms in query to English canonical terms using lexicon."""
    if not text:
        return ""

    lexicon = load_lexicon()
    all_mappings: dict[str, str] = {}
    # Combine both hi and kn mappings
    for lang_dict in lexicon.values():
        all_mappings.update(lang_dict)

    # Sort keys by length descending to match longest phrases first
    sorted_phrases = sorted(all_mappings.keys(), key=lambda k: len(k), reverse=True)

    normalized = text
    for phrase in sorted_phrases:
        eng_replacement = all_mappings[phrase]
        # For non-ASCII phrases (Devanagari / Kannada), do substring or word replacement
        if any(ord(c) > 127 for c in phrase):
            if phrase in normalized:
                normalized = normalized.replace(phrase, f" {eng_replacement} ")
        else:
            # Word boundary regex for ASCII / romanized words
            pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
            normalized = pattern.sub(eng_replacement, normalized)

    # Clean up extra whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized
