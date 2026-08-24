"""
MediaFile model: the physical-file layer. Distinct from Movie (logical/creative work)
and from Drive (physical storage). A MediaFile always belongs to exactly one Drive
and may (eventually) be linked to exactly one Movie.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, BigInteger, ForeignKey, Enum as SAEnum, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediavault.database.models.base import Base, TimestampMixin
from mediavault.database.models.enums import FileScanState, HashTier, PipelineStage


class MediaFile(Base, TimestampMixin):
    __tablename__ = "media_files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID4 hex

    drive_id: Mapped[str] = mapped_column(ForeignKey("drives.id"), nullable=False, index=True)
    drive: Mapped["Drive"] = relationship(back_populates="files")

    movie_id: Mapped[Optional[str]] = mapped_column(ForeignKey("movies.id"), nullable=True, index=True)
    movie: Mapped[Optional["Movie"]] = relationship(back_populates="files")

    # --- Location (never rely on full path alone) ---
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)   # relative to drive root
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    current_filename: Mapped[str] = mapped_column(String(500), nullable=False)

    # --- Filesystem fingerprint (cheap, checked every scan) ---
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    modified_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # --- Hashing (tiered, expensive, checked only when configured) ---
    fast_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    file_hash_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    hash_tier_computed: Mapped[HashTier] = mapped_column(
        SAEnum(HashTier, native_enum=False), default=HashTier.NONE, nullable=False
    )

    metadata_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # hash of extracted tech metadata

    # --- Scan bookkeeping (crash-safe: updated per file, not just in RAM) ---
    scan_state: Mapped[FileScanState] = mapped_column(
        SAEnum(FileScanState, native_enum=False), default=FileScanState.NEW, nullable=False
    )
    pipeline_stage: Mapped[PipelineStage] = mapped_column(
        SAEnum(PipelineStage, native_enum=False), default=PipelineStage.DISCOVERED, nullable=False
    )
    last_scan_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_metadata_scan_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(default=0, nullable=False)

    is_missing: Mapped[bool] = mapped_column(default=False, nullable=False)
    missing_since: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # --- Raw technical metadata preserved for future re-parsing ---
    raw_media_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    video_streams: Mapped[List["VideoStream"]] = relationship(back_populates="file", cascade="all, delete-orphan")
    audio_streams: Mapped[List["AudioStream"]] = relationship(back_populates="file", cascade="all, delete-orphan")
    subtitle_streams: Mapped[List["SubtitleStream"]] = relationship(back_populates="file", cascade="all, delete-orphan")

    def full_path(self) -> str:
        mount = self.drive.current_mount_point if self.drive and self.drive.current_mount_point else "<OFFLINE>"
        sep = "" if mount.endswith(("\\\\", "/")) else "\\\\"
        return f"{mount}{sep}{self.relative_path}"

    def __repr__(self) -> str:
        return f"<MediaFile id={self.id} drive={self.drive_id} rel={self.relative_path} state={self.scan_state}>"