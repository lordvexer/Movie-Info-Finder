"""
MovieMatcher: computes a confidence score for how well a ProviderMovieCandidate
matches a locally-parsed filename, per spec section 12.

Pure scoring logic, no I/O -- fully unit-testable.
"""
from __future__ import annotations
import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

from mediavault.scanner.filename_parser import ParsedFilename
from mediavault.providers.tmdb import ProviderMovieCandidate

CONFIDENCE_AUTO_ACCEPT_THRESHOLD = 0.85
CONFIDENCE_REVIEW_THRESHOLD = 0.55


@dataclass
class MatchFactor:
    name: str
    score: float
    weight: float
    detail: str = ""


@dataclass
class MovieMatchResult:
    candidate: ProviderMovieCandidate
    confidence: float
    factors: list[MatchFactor] = field(default_factory=list)
    needs_manual_review: bool = False


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _title_similarity(a: str, b: str) -> float:
    a_norm, b_norm = _normalize_title(a), _normalize_title(b)
    if not a_norm or not b_norm:
        return 0.0
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()


def score_candidate(
    parsed: ParsedFilename,
    candidate: ProviderMovieCandidate,
    runtime_minutes_hint: Optional[int] = None,
    candidate_runtime_minutes: Optional[int] = None,
) -> MovieMatchResult:
    factors: list[MatchFactor] = []

    title_score = max(
        _title_similarity(parsed.clean_title, candidate.title),
        _title_similarity(parsed.clean_title, candidate.original_title or ""),
    )
    factors.append(MatchFactor(
        name="title_match", score=title_score, weight=0.55,
        detail=f"{parsed.clean_title!r} vs {candidate.title!r}",
    ))

    if parsed.year is not None and candidate.release_year is not None:
        year_diff = abs(parsed.year - candidate.release_year)
        year_score = 1.0 if year_diff == 0 else (0.5 if year_diff == 1 else 0.0)
        factors.append(MatchFactor(
            name="year_match", score=year_score, weight=0.30,
            detail=f"{parsed.year} vs {candidate.release_year}",
        ))
    else:
        factors.append(MatchFactor(name="year_match", score=0.5, weight=0.10, detail="year unavailable"))

    if runtime_minutes_hint and candidate_runtime_minutes:
        runtime_diff = abs(runtime_minutes_hint - candidate_runtime_minutes)
        runtime_score = max(0.0, 1.0 - (runtime_diff / 30.0))
        factors.append(MatchFactor(
            name="runtime_match", score=runtime_score, weight=0.15,
            detail=f"{runtime_minutes_hint}min vs {candidate_runtime_minutes}min",
        ))

    if candidate.popularity:
        popularity_score = min(1.0, candidate.popularity / 100.0)
        factors.append(MatchFactor(name="popularity_signal", score=popularity_score, weight=0.05,
                                    detail=f"popularity={candidate.popularity}"))

    total_weight = sum(f.weight for f in factors)
    weighted_score = sum(f.score * f.weight for f in factors) / total_weight if total_weight else 0.0

    return MovieMatchResult(
        candidate=candidate,
        confidence=round(weighted_score, 4),
        factors=factors,
        needs_manual_review=weighted_score < CONFIDENCE_REVIEW_THRESHOLD,
    )


def rank_candidates(
    parsed: ParsedFilename,
    candidates: list[ProviderMovieCandidate],
    runtime_minutes_hint: Optional[int] = None,
) -> list[MovieMatchResult]:
    results = [score_candidate(parsed, c, runtime_minutes_hint) for c in candidates]
    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


def best_match(
    parsed: ParsedFilename,
    candidates: list[ProviderMovieCandidate],
    runtime_minutes_hint: Optional[int] = None,
) -> Optional[MovieMatchResult]:
    ranked = rank_candidates(parsed, candidates, runtime_minutes_hint)
    return ranked[0] if ranked else None