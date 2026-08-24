"""
Drive model: persistent identity for physical storage, independent of the
current OS-assigned drive letter / mount point.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, BigInteger, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediavault.database.models.base import Base, TimestampMixin
from mediavault.database.models.enums import DriveStatus


class Drive(Base, TimestampMixin):
    """
    A physical (or virtual) storage device that has been scanned at least once.

    Persistent identity strategy (Windows):
      1. volume_serial_number  -- from GetVolumeInformation (survives reformat only, not repartition)
      2. filesystem UUID (if available, e.g. on exFAT/NTFS via alternate APIs)
      3. fallback composite fingerprint (label + total_capacity + first_seen files signature)

    The `id` (drive_id) is the app-level primary key. `volume_serial_number` is the
    OS-level fingerprint used to REDISCOVER this Drive row when the same disk is
    reconnected under a different letter.
    """
    __tablename__ = "drives"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # app-generated UUID4 hex
    volume_serial_number: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    filesystem_uuid: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    fallback_fingerprint: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)

    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    filesystem: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # NTFS/exFAT/etc

    current_mount_point: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # e.g. "H:\\"
    capacity_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    free_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    status: Mapped[DriveStatus] = mapped_column(
        SAEnum(DriveStatus, native_enum=False), default=DriveStatus.UNKNOWN, nullable=False
    )

    first_seen: Mapped[datetime] = mapped_column(nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_scan_started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_scan_completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    is_ignored: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    files: Mapped[List["MediaFile"]] = relationship(back_populates="drive", cascade="all, delete-orphan")
    scan_jobs: Mapped[List["ScanJob"]] = relationship(back_populates="drive", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Drive id={self.id} label={self.label} mount={self.current_mount_point} status={self.status}>"