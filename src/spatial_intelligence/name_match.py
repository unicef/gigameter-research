"""
Module: src/spatial_intelligence/name_match.py
Purpose: Registry-name match between an entity's official name and the SSIDs
         seen at a location. Used to break strategy disagreements and as
         Track 3 evidence.
Rules: Names and SSIDs are lowercased, stripped of diacritics, and split on
       non-alphanumeric characters. Generic tokens are removed, together with
       a number written directly before a generic token (a grade label such
       as `9-vjeçare`, or the `2` of `2.4g`). The match holds when every
       remaining registry token appears in the SSID.
"""

import re
import unicodedata
from typing import Iterable, List, Optional, Set

from .config import DEFAULT_CONFIG, SpatialConfig

_SPLIT = re.compile(r"[^0-9a-z]+")


def _tokens(text: str) -> List[str]:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return [t for t in _SPLIT.split(ascii_text.lower()) if t]


def distinctive_tokens(
    text: Optional[str], generic_tokens: Iterable[str] = DEFAULT_CONFIG.name_match_generic_tokens
) -> Set[str]:
    """
    Tokens of `text` that can identify an entity.

    Args:
        text: Registry name or SSID. `None` yields an empty set.
        generic_tokens: Tokens to drop, already lowercase and ASCII.

    Returns:
        The remaining tokens.
    """
    if not text or not isinstance(text, str):
        return set()
    generic = set(generic_tokens)
    tokens = _tokens(text)
    kept = set()
    for index, token in enumerate(tokens):
        if token in generic:
            continue
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if token.isdigit() and next_token in generic:
            continue
        kept.add(token)
    return kept


def ssid_matches_name(
    ssids: Iterable[Optional[str]],
    registry_name: Optional[str],
    config: SpatialConfig = DEFAULT_CONFIG,
) -> bool:
    """
    True when any SSID contains every distinctive token of `registry_name`.

    A registry name with no distinctive token never matches.
    """
    wanted = distinctive_tokens(registry_name, config.name_match_generic_tokens)
    if not wanted:
        return False
    for ssid in ssids:
        if wanted <= distinctive_tokens(ssid, config.name_match_generic_tokens):
            return True
    return False
