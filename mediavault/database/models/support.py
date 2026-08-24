"""
Supporting entities: duplicates, operation history, provider cache, settings,
and metadata-source snapshots (for auditability / conflict resolution).
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, ForeignKey, Enum as SAEnum, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediavault.database.models.base import Base, TimestampMixin
from mediavault.database.models.enums import (
    DuplicateRelationType, FileOperationType, FileOperationResult, MetadataFieldSource,
)


class DuplicateGroup(Base, TimestampMixin):
    __tablename__ = "duplicate_groups"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    movie_id: Mapped[Optional[str]] = mapped_column(ForeignKey("movies.id"), nullable=True, index=True)

    relation_type: Mapped[DuplicateRelationType] = mapped_column(
        SAEnum(DuplicateRelationType, native_enum=False), nullable=False
    )
    file_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)  # list[str] of media_files.id
    preferred_file_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    resolution_action: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # KEEP_A/KEEP_B/KEEP_BOTH/...
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FileOperation(Base, TimestampMixin):
    """Immutable audit log entry. Every rename/move/metadata-write/delete goes through here."""
    __tablename__ = "file_operations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("media_files.id"), nullable=True, index=True)
    drive_id: Mapped[Optional[str]] = mapped_column(ForeignKey("drives.id"), nullable=True, index=True)

    operation_type: Mapped[FileOperationType] = mapped_column(
        SAEnum(FileOperationType, native_enum=False), nullable=False
    )
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    performed_by: Mapped[str] = mapped_column(String(64), default="user", nullable=False)
    result: Mapped[FileOperationResult] = mapped_column(
        SAEnum(FileOperationResult, native_enum=False), nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    can_undo: Mapped[bool] = mapped_column(default=False, nullable=False)
    undone: Mapped[bool] = mapped_column(default=False, nullable=False)


class ProviderCache(Base, TimestampMixin):
    """Caches external provider responses to respect rate limits and avoid redundant calls."""
    __tablename__ = "provider_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # "tmdb"
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # e.g. "movie:603"
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class MetadataSnapshot(Base, TimestampMixin):
    """
    Per-field provenance tracking for auditability & conflict resolution.
    e.g. (movie_id="abc", field_name="title", value="The Matrix", source=EXTERNAL_PROVIDER, confidence=0.99)
    """
    __tablename__ = "metadata_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    movie_id: Mapped[Optional[str]] = mapped_column(ForeignKey("movies.id"), nullable=True, index=True)
    file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("media_files.id"), nullable=True, index=True)

    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[MetadataFieldSource] = mapped_column(
        SAEnum(MetadataFieldSource, native_enum=False), nullable=False
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)  # superseded snapshots kept, flagged inactive


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)