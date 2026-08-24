"""
FilenameParser: extracts a clean movie title, release year, and quality
hints from messy scene-release filenames, per spec section 21.

Pure string logic, no I/O, fully unit-testable.

Example:
  "Gladiator.II.2024.2160p.HDR10Plus.DV.WEB-DL.6CH.x265-PSA.SoftSub.DigiMoviez.mkv"
  -> ParsedFilename(title="Gladiator II", year=2024, ...)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedFilename:
    clean_title: str
    year: Optional[int]
    raw_tokens_removed: list[str] = field(default_factory=list)
    original_filename: str = ""


_TECH_MARKERS = [
    r"\d{3,4}p", r"2160p", r"1080p", r"720p", r"480p",
    r"WEB[-.]?DL", r"WEBRip", r"BluRay", r"BDRip", r"BRRip", r"HDRip", r"DVDRip", r"HDTV",
    r"REMUX", r"REPACK", r"PROPER", r"UNRATED", r"EXTENDED", r"DIRECTORS?\.?CUT",
    r"x264", r"x265", r"h264", r"h265", r"HEVC", r"AVC", r"AV1", r"VP9",
    r"HDR10\+?", r"HDR", r"DV", r"DoVi", r"Dolby\.?Vision",
    r"\d{1,2}CH", r"\dCH", r"AAC\d?", r"AC3", r"E-?AC3", r"DTS(-HD)?(\.MA)?",
    r"TrueHD", r"FLAC", r"Atmos", r"DDP?\d?\.?\d?",
    r"\d{1,2}bit", r"10bit", r"8bit",
    r"SoftSub", r"HardSub", r"MultiSub", r"Dubbed",
    r"YIFY", r"RARBG", r"PSA", r"FGT", r"NTb", r"EVO",
]
_TECH_MARKER_PATTERN = re.compile(
    r"(?:" + "|".join(_TECH_MARKERS) + r")", re.IGNORECASE
)

_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")

_RELEASE_GROUP_SUFFIX = re.compile(r"-[A-Za-z0-9]+$")

_KNOWN_DISTRIBUTOR_TAGS = {"digimoviez", "yify", "rarbg", "psa", "fgt", "ntb", "evo"}


def _split_on_separators(text: str) -> list[str]:
    normalized = re.sub(r"[._]+", " ", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.split(" ")


def parse_filename(filename: str) -> ParsedFilename:
    stem = filename
    for ext in (".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".m2ts", ".vob", ".webm"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break

    group_match = _RELEASE_GROUP_SUFFIX.search(stem)
    removed_tokens: list[str] = []
    if group_match and group_match.group(0)[1:].lower() not in {"ii", "iii", "iv", "vi", "vii"}:
        removed_tokens.append(group_match.group(0))
        stem = stem[: group_match.start()]

    words = _split_on_separators(stem)

    year: Optional[int] = None
    title_words: list[str] = []
    hit_tech_marker = False

    for word in words:
        if hit_tech_marker:
            removed_tokens.append(word)
            continue

        year_match = _YEAR_PATTERN.fullmatch(word)
        if year_match and year is None:
            year = int(word)
            hit_tech_marker = True
            continue

        if _TECH_MARKER_PATTERN.fullmatch(word) or word.lower() in _KNOWN_DISTRIBUTOR_TAGS:
            hit_tech_marker = True
            removed_tokens.append(word)
            continue

        title_words.append(word)

    clean_title = " ".join(title_words).strip()
    clean_title = re.sub(r"\s+", " ", clean_title)

    return ParsedFilename(
        clean_title=clean_title,
        year=year,
        raw_tokens_removed=removed_tokens,
        original_filename=filename,
    )