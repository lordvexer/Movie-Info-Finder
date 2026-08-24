"""
TMDBProvider: concrete implementation of the MetadataProvider abstraction for
The Movie Database (TMDB), per spec section 13.

API key is NEVER hardcoded: it must be supplied by the caller (read from
AppConfig.from_env(), which reads the TMDB_API_KEY environment variable).
"""
from __future__ import annotations
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import requests


@dataclass
class ProviderMovieCandidate:
    external_id: str
    provider: str
    title: str
    original_title: Optional[str]
    release_year: Optional[int]
    release_date: Optional[str]
    overview: Optional[str]
    popularity: Optional[float]
    vote_average: Optional[float]
    vote_count: Optional[int]
    poster_path: Optional[str]
    original_language: Optional[str]


@dataclass
class ProviderMovieDetails(ProviderMovieCandidate):
    runtime_minutes: Optional[int] = None
    genres: list[str] = field(default_factory=list)
    tagline: Optional[str] = None
    spoken_languages: list[str] = field(default_factory=list)
    production_countries: list[str] = field(default_factory=list)
    production_companies: list[str] = field(default_factory=list)
    backdrop_path: Optional[str] = None
    imdb_id: Optional[str] = None
    directors: list[dict] = field(default_factory=list)
    writers: list[dict] = field(default_factory=list)
    producers: list[dict] = field(default_factory=list)
    composers: list[dict] = field(default_factory=list)
    cast: list[dict] = field(default_factory=list)
    collection_name: Optional[str] = None
    collection_external_id: Optional[str] = None


class MetadataProviderError(Exception):
    pass


class MetadataProvider(ABC):
    """Abstract base every provider (TMDB, IMDb, future) must implement."""

    @abstractmethod
    def search_movies(self, title: str, year: Optional[int] = None) -> list[ProviderMovieCandidate]:
        ...

    @abstractmethod
    def get_movie_details(self, external_id: str) -> ProviderMovieDetails:
        ...


class TMDBProvider(MetadataProvider):
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"
    PROVIDER_NAME = "tmdb"
    def __init__(self, api_key: str, timeout: int = 15, max_retries: int = 3, proxy: str | None = None):
        if not api_key:
            raise MetadataProviderError(
                "TMDB API key is missing. Set the TMDB_API_KEY environment variable."
            )
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}

    def ping(self) -> bool:
        """
        Lightweight warm-up call: establishes the underlying HTTPS connection
        (and, when routed through a local VPN/proxy tool, gives that tool time
        to finish tunnel negotiation) BEFORE the real scan work starts. This
        avoids the first real request eating a 30-40s timeout+retry cycle.
        Returns True if TMDB is reachable, False otherwise (never raises).
        """
        try:
            self._get("/configuration")
            return True
        except MetadataProviderError:
            return False
            
    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        params = dict(params or {})
        params["api_key"] = self.api_key

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._session.get(f"{self.BASE_URL}{path}", params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(min(2 ** attempt, 10))
                continue

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 2))
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                last_error = MetadataProviderError(f"TMDB server error {response.status_code}")
                time.sleep(min(2 ** attempt, 10))
                continue

            if response.status_code == 401:
                raise MetadataProviderError("TMDB rejected the API key (401 Unauthorized).")

            if response.status_code == 404:
                raise MetadataProviderError(f"TMDB resource not found: {path}")

            if not response.ok:
                raise MetadataProviderError(f"TMDB request failed ({response.status_code}): {response.text[:300]}")

            return response.json()

        raise MetadataProviderError(f"TMDB request failed after {self.max_retries} attempts: {last_error}")

    def search_movies(self, title: str, year: Optional[int] = None) -> list[ProviderMovieCandidate]:
        params = {"query": title, "include_adult": "false"}
        if year:
            params["year"] = year

        data = self._get("/search/movie", params=params)
        results = data.get("results", []) or []

        candidates = []
        for item in results:
            release_date = item.get("release_date") or None
            release_year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
            candidates.append(ProviderMovieCandidate(
                external_id=str(item.get("id")),
                provider=self.PROVIDER_NAME,
                title=item.get("title") or item.get("original_title") or "",
                original_title=item.get("original_title"),
                release_year=release_year,
                release_date=release_date,
                overview=item.get("overview"),
                popularity=item.get("popularity"),
                vote_average=item.get("vote_average"),
                vote_count=item.get("vote_count"),
                poster_path=item.get("poster_path"),
                original_language=item.get("original_language"),
            ))
        return candidates

    def get_movie_details(self, external_id: str) -> ProviderMovieDetails:
        data = self._get(f"/movie/{external_id}", params={"append_to_response": "credits,external_ids"})

        release_date = data.get("release_date") or None
        release_year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

        credits = data.get("credits", {}) or {}
        crew = credits.get("crew", []) or []
        cast_list = credits.get("cast", []) or []

        def _crew_by_job(job_name: str) -> list[dict]:
            return [
                {"id": str(p.get("id")), "name": p.get("name")}
                for p in crew if p.get("job") == job_name
            ]

        collection = data.get("belongs_to_collection")

        return ProviderMovieDetails(
            external_id=str(data.get("id")),
            provider=self.PROVIDER_NAME,
            title=data.get("title") or data.get("original_title") or "",
            original_title=data.get("original_title"),
            release_year=release_year,
            release_date=release_date,
            overview=data.get("overview"),
            popularity=data.get("popularity"),
            vote_average=data.get("vote_average"),
            vote_count=data.get("vote_count"),
            poster_path=data.get("poster_path"),
            original_language=data.get("original_language"),
            runtime_minutes=data.get("runtime"),
            genres=[g.get("name") for g in data.get("genres", []) or [] if g.get("name")],
            tagline=data.get("tagline") or None,
            spoken_languages=[l.get("english_name") or l.get("name") for l in data.get("spoken_languages", []) or []],
            production_countries=[c.get("name") for c in data.get("production_countries", []) or []],
            production_companies=[c.get("name") for c in data.get("production_companies", []) or []],
            backdrop_path=data.get("backdrop_path"),
            imdb_id=(data.get("external_ids") or {}).get("imdb_id") or data.get("imdb_id"),
            directors=_crew_by_job("Director"),
            writers=_crew_by_job("Writer") + _crew_by_job("Screenplay"),
            producers=_crew_by_job("Producer"),
            composers=_crew_by_job("Original Music Composer"),
            cast=[
                {"id": str(p.get("id")), "name": p.get("name"), "character": p.get("character"), "order": p.get("order")}
                for p in sorted(cast_list, key=lambda p: p.get("order", 999))[:25]
            ],
            collection_name=collection.get("name") if collection else None,
            collection_external_id=str(collection.get("id")) if collection else None,
        )

    def poster_url(self, poster_path: Optional[str]) -> Optional[str]:
        return f"{self.IMAGE_BASE_URL}{poster_path}" if poster_path else None

    def backdrop_url(self, backdrop_path: Optional[str]) -> Optional[str]:
        return f"{self.IMAGE_BASE_URL}{backdrop_path}" if backdrop_path else None