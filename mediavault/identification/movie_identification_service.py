"""
MovieIdentificationService: bridges FilenameParser + TMDBProvider + MovieMatcher
into persisted Movie rows, per spec sections 9, 12, 14.

Design principles enforced here (spec section 51/52):
  - A provider failure NEVER aborts the scan; the file stays indexed with
    movie_id=None and is retried on a future scan.
  - Low-confidence matches are NEVER silently assigned: flagged
    `needs_manual_review=True` instead.
  - Results are cached via ProviderCache to avoid redundant API calls.
  - Poster/backdrop artwork is downloaded ONCE here (during identification)
    and cached to local disk via ArtworkManager -- the GUI never re-downloads
    it just to display a dialog.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from mediavault.core.time_utils import utcnow_naive, to_naive_utc
from mediavault.artwork.manager import download_and_cache
from mediavault.database.models import (
    MediaFile, Movie, Person, Genre, Collection, ProviderCache, MetadataSnapshot,
    MetadataFieldSource,
)
from mediavault.scanner.filename_parser import parse_filename
from mediavault.providers.tmdb import (
    TMDBProvider, MetadataProviderError, ProviderMovieDetails,
)
from mediavault.identification.movie_matcher import best_match, CONFIDENCE_AUTO_ACCEPT_THRESHOLD

logger = logging.getLogger("mediavault.movie_identification_service")

_CACHE_TTL_SECONDS = 30 * 24 * 3600


class MovieIdentificationService:
    def __init__(self, session: Session, provider: TMDBProvider, proxy: Optional[str] = None):
        self.session = session
        self.provider = provider
        self.proxy = proxy

    def process_file(self, media_file_id: str) -> None:
        media_file = self.session.get(MediaFile, media_file_id)
        if media_file is None:
            logger.warning("MediaFile %s not found; skipping identification", media_file_id)
            return

        parsed = parse_filename(media_file.filename)
        if not parsed.clean_title:
            media_file.last_error = "Filename parser could not extract a title"
            self.session.flush()
            return

        try:
            candidates = self._search_with_cache(parsed.clean_title, parsed.year)
        except MetadataProviderError as exc:
            media_file.last_error = f"TMDB search failed: {exc}"
            media_file.error_count += 1
            self.session.flush()
            logger.error("TMDB search failed for %s: %s", media_file.filename, exc)
            return

        if not candidates:
            media_file.last_error = "No TMDB candidates found"
            self.session.flush()
            return

        match = best_match(parsed, candidates, runtime_minutes_hint=None)
        if match is None:
            return

        try:
            details = self._get_details_with_cache(match.candidate.external_id)
        except MetadataProviderError as exc:
            media_file.last_error = f"TMDB details fetch failed: {exc}"
            media_file.error_count += 1
            self.session.flush()
            logger.error("TMDB details fetch failed for %s: %s", media_file.filename, exc)
            return

        movie = self._upsert_movie(details, confidence=match.confidence)
        media_file.movie_id = movie.id
        media_file.last_error = None
        self.session.flush()

        self._write_metadata_snapshots(movie, details, match.confidence)
        logger.info(
            "Identified %s -> %s (%s) [confidence=%.2f%s]",
            media_file.filename, movie.title, movie.release_year, match.confidence * 100,
            " NEEDS REVIEW" if movie.needs_manual_review else "",
        )

    def _search_with_cache(self, title: str, year: Optional[int]):
        cache_key = f"search:{title.lower()}:{year or ''}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            from mediavault.providers.tmdb import ProviderMovieCandidate
            return [ProviderMovieCandidate(**item) for item in cached]

        candidates = self.provider.search_movies(title, year)
        self._write_cache(cache_key, [candidate.__dict__ for candidate in candidates])
        return candidates

    def _get_details_with_cache(self, external_id: str) -> ProviderMovieDetails:
        cache_key = f"details:{external_id}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return ProviderMovieDetails(**cached)

        details = self.provider.get_movie_details(external_id)
        self._write_cache(cache_key, details.__dict__)
        return details

    def _read_cache(self, cache_key: str) -> Optional[dict]:
        row = self.session.execute(
            select(ProviderCache).where(
                ProviderCache.provider == self.provider.PROVIDER_NAME,
                ProviderCache.cache_key == cache_key,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.expires_at and to_naive_utc(row.expires_at) < utcnow_naive():
            return None
        return row.response_json

    def _write_cache(self, cache_key: str, payload) -> None:
        from datetime import timedelta
        existing = self.session.execute(
            select(ProviderCache).where(
                ProviderCache.provider == self.provider.PROVIDER_NAME,
                ProviderCache.cache_key == cache_key,
            )
        ).scalar_one_or_none()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=_CACHE_TTL_SECONDS)
        if existing:
            existing.response_json = payload
            existing.expires_at = expires_at
        else:
            self.session.add(ProviderCache(
                id=uuid.uuid4().hex, provider=self.provider.PROVIDER_NAME,
                cache_key=cache_key, response_json=payload, expires_at=expires_at,
            ))
        self.session.flush()

    def _upsert_movie(self, details: ProviderMovieDetails, confidence: float) -> Movie:
        existing = self.session.execute(
            select(Movie).where(Movie.external_ids.isnot(None))
        ).scalars().all()
        movie = next(
            (m for m in existing if m.external_ids and m.external_ids.get("tmdb") == details.external_id),
            None,
        )

        release_date = None
        if details.release_date:
            try:
                release_date = datetime.strptime(details.release_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        if movie is None:
            movie = Movie(id=uuid.uuid4().hex)
            self.session.add(movie)

        movie.title = details.title
        movie.original_title = details.original_title
        movie.release_date = release_date
        movie.release_year = details.release_year
        movie.runtime_minutes = details.runtime_minutes
        movie.overview = details.overview
        movie.tagline = details.tagline
        movie.original_language = details.original_language
        movie.spoken_languages = details.spoken_languages
        movie.production_countries = details.production_countries
        movie.production_companies = details.production_companies
        movie.rating = details.vote_average
        movie.vote_count = details.vote_count
        movie.popularity = details.popularity
        movie.external_ids = {"tmdb": details.external_id, **({"imdb": details.imdb_id} if details.imdb_id else {})}
        movie.poster_url = self.provider.poster_url(details.poster_path)
        movie.backdrop_url = self.provider.backdrop_url(details.backdrop_path)
        movie.metadata_provider = self.provider.PROVIDER_NAME
        movie.metadata_last_updated = datetime.now(timezone.utc)
        movie.identification_confidence = confidence
        movie.needs_manual_review = confidence < CONFIDENCE_AUTO_ACCEPT_THRESHOLD

        self._sync_genres(movie, details.genres)
        self._sync_people(movie, details)
        if details.collection_name:
            self._sync_collection(movie, details.collection_name, details.collection_external_id)

        self.session.flush()

        # Download artwork ONCE here, right after identification. The GUI
        # (MovieDetailDialog) only ever reads from this local cache afterwards
        # -- it never hits the network again for the same movie.
        if movie.poster_url:
            download_and_cache(movie.id, movie.poster_url, "poster", proxy=self.proxy)
        if movie.backdrop_url:
            download_and_cache(movie.id, movie.backdrop_url, "backdrop", proxy=self.proxy)

        return movie

    def _sync_genres(self, movie: Movie, genre_names: list[str]) -> None:
        movie.genres.clear()
        for name in genre_names:
            genre = self.session.execute(select(Genre).where(Genre.name == name)).scalar_one_or_none()
            if genre is None:
                genre = Genre(name=name)
                self.session.add(genre)
                self.session.flush()
            movie.genres.append(genre)

    def _sync_people(self, movie: Movie, details: ProviderMovieDetails) -> None:
        movie.cast.clear()
        movie.crew.clear()
        self.session.flush()

        def _get_or_create_person(person_id: str, name: str) -> Person:
            person = self.session.execute(
                select(Person).where(Person.external_ids.isnot(None))
            ).scalars().all()
            match_person = next(
                (p for p in person if p.external_ids and p.external_ids.get("tmdb") == person_id), None
            )
            if match_person is None:
                match_person = Person(id=uuid.uuid4().hex, name=name, external_ids={"tmdb": person_id})
                self.session.add(match_person)
                self.session.flush()
            return match_person

        for entry in details.cast[:25]:
            if not entry.get("id"):
                continue
            person = _get_or_create_person(entry["id"], entry.get("name") or "Unknown")
            movie.cast.append(person)

        from mediavault.database.models.movie import movie_crew
        for role, people_list in [
            ("DIRECTOR", details.directors), ("WRITER", details.writers),
            ("PRODUCER", details.producers), ("COMPOSER", details.composers),
        ]:
            for entry in people_list:
                if not entry.get("id"):
                    continue
                person = _get_or_create_person(entry["id"], entry.get("name") or "Unknown")
                exists = self.session.execute(
                    select(movie_crew).where(
                        movie_crew.c.movie_id == movie.id,
                        movie_crew.c.person_id == person.id,
                        movie_crew.c.role == role,
                    )
                ).first()
                if not exists:
                    self.session.execute(
                        movie_crew.insert().values(movie_id=movie.id, person_id=person.id, role=role)
                    )
        self.session.flush()

    def _sync_collection(self, movie: Movie, name: str, external_id: Optional[str]) -> None:
        collection = self.session.execute(select(Collection).where(Collection.name == name)).scalar_one_or_none()
        if collection is None:
            collection = Collection(id=uuid.uuid4().hex, name=name, kind="FRANCHISE", external_id=external_id)
            self.session.add(collection)
            self.session.flush()
        movie.collection_id = collection.id

    def _write_metadata_snapshots(self, movie: Movie, details: ProviderMovieDetails, confidence: float) -> None:
        fields = {
            "title": details.title, "original_title": details.original_title,
            "release_year": str(details.release_year) if details.release_year else None,
            "runtime_minutes": str(details.runtime_minutes) if details.runtime_minutes else None,
        }
        for field_name, value in fields.items():
            if value is None:
                continue
            self.session.add(MetadataSnapshot(
                id=uuid.uuid4().hex, movie_id=movie.id, field_name=field_name, field_value=value,
                source=MetadataFieldSource.EXTERNAL_PROVIDER, confidence=confidence, is_active=True,
            ))
        self.session.flush()