"""Title cleaning and year/episode extraction for TMDB search."""

from __future__ import annotations

import re
from datetime import datetime

_CURRENT_YEAR = datetime.now().year

# Common release tags — stripped before searching
_STRIP_PATTERNS = [
    r"\b2160p\b", r"\b1080[pi]\b", r"\b720p\b", r"\b480p\b",
    r"\b4K\b", r"\bUHD\b",
    r"\bBlu-?Ray\b", r"\bBDRip\b", r"\bBRRip\b",
    r"\bDVDRip\b", r"\bDVDScr\b", r"\bDVD\b",
    r"\bWEB-?DL\b", r"\bWEB-?Rip\b", r"\bWEBDL\b",
    r"\bHDTV\b", r"\bPDTV\b", r"\bDSRip\b",
    r"\bx26[45]\b", r"\bH\.?26[45]\b", r"\bHEVC\b", r"\bAVC\b",
    r"\bAAC\b", r"\bAC3\b", r"\bDTS\b", r"\bDD5\b", r"\bMP3\b",
    r"\bNL\b", r"\bDUTCH\b", r"\bNLSUBS?\b", r"\bMULTI\b",
    r"\bREPACK\b", r"\bPROPER\b", r"\bEXTENDED\b", r"\bDIRECTORS\.?CUT\b",
    r"\bSUBBED\b", r"\bDUBBED\b", r"\bHDR\b", r"\bSDR\b",
    r"\bRemux\b", r"\bAMZN\b", r"\bNF\b", r"\bDSNP\b",
    r"\bS\d{1,4}E\d+(?:-E\d+)?\b",  # S01E03, S2026E15, S38E9745
    r"\bSeizoen\s*\d+\b", r"\bSeason\s*\d+\b",
    r"\bAflevering\s*\d+\b", r"\bEpisode\s*\d+\b",
]

_STRIP_RE = re.compile("|".join(_STRIP_PATTERNS), re.IGNORECASE)

# Year — must be 4 digits, plausible range
_YEAR_RE = re.compile(r"(?:^|[\s.(])(\d{4})(?:[\s.)]|$)")


def _extract_season_episode(raw: str) -> tuple[int | None, int | None]:
    m = re.search(r"\bS(\d{1,4})E(\d+)\b", raw, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _extract_year(raw: str) -> int | None:
    for m in _YEAR_RE.finditer(raw):
        y = int(m.group(1))
        if 1900 < y <= _CURRENT_YEAR + 1:
            return y
    return None


def clean_title(raw: str) -> tuple[str, int | None, int | None, int | None]:
    """Return (cleaned_title, year, season, episode) extracted from a raw release title."""
    season, episode = _extract_season_episode(raw)
    year = _extract_year(raw)

    # Normalise dots/underscores used as word separators
    cleaned = raw.replace(".", " ").replace("_", " ")

    # Strip leading channel/network tags like (BBC), (NPO), (VTM)
    cleaned = re.sub(r"^\([A-Z0-9 ]+\)\s*", "", cleaned)

    # Strip from the first tag onwards — everything after is noise
    tag_match = _STRIP_RE.search(cleaned)
    if tag_match:
        cleaned = cleaned[: tag_match.start()]

    # Remove years — already captured separately, confuse TMDB query if left in
    cleaned = re.sub(r"\(\s*\d{4}\s*\)", "", cleaned)
    cleaned = re.sub(r"\b(19|20)\d{2}\b", "", cleaned)

    cleaned = cleaned.strip(" -_.,")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    return cleaned, year, season, episode
