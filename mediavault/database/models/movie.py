"""
Movie: the logical/creative-work entity. Distinct from MediaFile (physical file)
and Drive (physical storage). One Movie can have many MediaFiles (versions).
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Float, Integer, Text, ForeignKey, Table, Column, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediavault.database.models.base import Base, TimestampMixin

# --- Many-to-many association tables ---

movie_genres = Table(
    "movie_genres", Base.metadata,
    Column("movie_id", ForeignKey("movies.id"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id"), primary_key=True),
)

movie_cast = Table(
    "movie_cast", Base.metadata,
    Column("movie_id", ForeignKey("movies.id"), primary_key=True),
    Column("person_id", ForeignKey("people.id"), primary_key=True),
    Column("character_name", String(255)),
    Column("cast_order", Integer),
)

movie_crew = Table(
    "movie_crew", Base.metadata,
    Column("movie_id", ForeignKey("movies.id"), primary_key=True),
    Column("person_id", ForeignKey("people.id"), primary_key=True),
    Column("role", String(64), primary_key=True),  # DIRECTOR/WRITER/PRODUCER/COMPOSER/CINEMATOGRAPHER/EDITOR
)


class Genre(Base):
    __tablename__ = "genres"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    movies: Mapped[List["Movie"]] = relationship(secondary=movie_genres, back_populates="genres")


class Person(Base, TimestampMixin):
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    biography: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    external_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"tmdb": 123, "imdb": "nm123"}

    cast_movies: Mapped[List["Movie"]] = relationship(secondary=movie_cast, back_populates="cast")
    crew_movies: Mapped[List["Movie"]] = relationship(secondary=movie_crew, back_populates="crew")


class Collection(Base, TimestampMixin):
    __tablename__ = "collections"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="MANUAL")  # MANUAL/FRANCHISE/SMART/etc.
    smart_filter_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # for smart collections
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    movies: Mapped[List["Movie"]] = relationship(back_populates="collection")


class Movie(Base, TimestampMixin):
    __tablename__ = "movies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    original_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    alternate_titles: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    release_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    release_year: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    runtime_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tagline: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    original_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    spoken_languages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    production_countries: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    production_companies: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vote_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    popularity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    collection_id: Mapped[Optional[str]] = mapped_column(ForeignKey("collections.id"), nullable=True)
    collection: Mapped[Optional["Collection"]] = relationship(back_populates="movies")

    external_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"tmdb": 603, "imdb": "tt0133093"}
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    backdrop_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    metadata_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    metadata_last_updated: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    metadata_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    identification_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    needs_manual_review: Mapped[bool] = mapped_column(default=False, nullable=False)

    metadata_completeness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    technical_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    artwork_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    genres: Mapped[List["Genre"]] = relationship(secondary=movie_genres, back_populates="movies")
    cast: Mapped[List["Person"]] = relationship(secondary=movie_cast, back_populates="cast_movies")
    crew: Mapped[List["Person"]] = relationship(secondary=movie_crew, back_populates="crew_movies")

    files: Mapped[List["MediaFile"]] = relationship(back_populates="movie")

    def __repr__(self) -> str:
        return f"<Movie id={self.id} title={self.title!r} year={self.release_year}>"


class VideoStream(Base):
    __tablename__ = "video_streams"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("media_files.id"), nullable=False, index=True)
    file: Mapped["MediaFile"] = relationship(back_populates="video_streams")

    stream_index: Mapped[int] = mapped_column(Integer, nullable=False)
    codec: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    codec_profile: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    codec_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolution_label: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # "2160p","1080p",...
    aspect_ratio: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pixel_format: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    bit_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frame_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_frame_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bitrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    color_range: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    color_space: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    color_transfer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    color_primaries: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_hdr: Mapped[bool] = mapped_column(default=False, nullable=False)
    hdr_format: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # HDR10/HDR10+/DolbyVision
    dolby_vision_profile: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    mastering_display_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_light_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scan_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # progressive/interlaced


class AudioStream(Base):
    __tablename__ = "audio_streams"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("media_files.id"), nullable=False, index=True)
    file: Mapped["MediaFile"] = relationship(back_populates="audio_streams")

    stream_index: Mapped[int] = mapped_column(Integer, nullable=False)
    codec: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    channels: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    channel_layout: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    bitrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sample_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bit_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    profile: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_forced: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_commentary: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_lossless: Mapped[Optional[bool]] = mapped_column(nullable=True)


class SubtitleStream(Base):
    __tablename__ = "subtitle_streams"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("media_files.id"), nullable=False, index=True)
    file: Mapped["MediaFile"] = relationship(back_populates="subtitle_streams")

    stream_index: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    codec: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # SRT/ASS/SSA/PGS/VobSub/WebVTT
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_forced: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_hearing_impaired: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_text_based: Mapped[Optional[bool]] = mapped_column(nullable=True)