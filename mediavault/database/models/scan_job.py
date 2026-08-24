"""
ScanJob / ScanItem: the persistent job-queue backbone that makes resumable,
crash-safe, incremental scanning possible. Every discovered file gets a
ScanItem row BEFORE processing begins, and its status is updated as it moves
through the pipeline. This is what allows "resume from file 6342/10000".
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Text, ForeignKey, Enum as SAEnum, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediavault.database.models.base import Base, TimestampMixin
from mediavault.database.models.enums import ScanJobStatus, ScanJobType, ScanItemStatus, PipelineStage


class ScanJob(Base, TimestampMixin):
    __tablename__ = "scan_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    drive_id: Mapped[str] = mapped_column(ForeignKey("drives.id"), nullable=False, index=True)
    drive: Mapped["Drive"] = relationship(back_populates="scan_jobs")

    job_type: Mapped[ScanJobType] = mapped_column(SAEnum(ScanJobType, native_enum=False), nullable=False)
    root_path: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[ScanJobStatus] = mapped_column(
        SAEnum(ScanJobStatus, native_enum=False), default=ScanJobStatus.QUEUED, nullable=False
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    files_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_modified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_missing: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    current_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[List["ScanItem"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ScanJob id={self.id} drive={self.drive_id} status={self.status} {self.files_processed}/{self.files_discovered}>"


class ScanItem(Base, TimestampMixin):
    """
    One row per discovered filesystem path within a ScanJob. This table is the
    resumability mechanism: on restart, the scanner queries for items whose
    status is PENDING or IN_PROGRESS (crashed mid-file) and continues from there,
    skipping every item already marked DONE.
    """
    __tablename__ = "scan_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("scan_jobs.id"), nullable=False, index=True)
    job: Mapped["ScanJob"] = relationship(back_populates="items")

    file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("media_files.id"), nullable=True, index=True)

    full_path: Mapped[str] = mapped_column(Text, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ScanItemStatus] = mapped_column(
        SAEnum(ScanItemStatus, native_enum=False), default=ScanItemStatus.PENDING, nullable=False, index=True
    )
    pipeline_stage: Mapped[PipelineStage] = mapped_column(
        SAEnum(PipelineStage, native_enum=False), default=PipelineStage.DISCOVERED, nullable=False
    )

    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"<ScanItem id={self.id} path={self.relative_path} status={self.status} stage={self.pipeline_stage}>"