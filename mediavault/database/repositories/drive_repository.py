"""
DriveRepository: encapsulates all Drive persistence logic, including the
critical "rediscover a known drive under a new letter" workflow.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediavault.database.models import Drive, DriveStatus


class DriveRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_by_fingerprint(
        self,
        volume_serial_number: Optional[str] = None,
        filesystem_uuid: Optional[str] = None,
        fallback_fingerprint: Optional[str] = None,
    ) -> Optional[Drive]:
        """
        Resolution order mirrors persistence confidence:
        1. volume_serial_number (most reliable on Windows/NTFS/exFAT)
        2. filesystem_uuid (when available)
        3. fallback_fingerprint (label+capacity heuristic; last resort)
        """
        if volume_serial_number:
            drive = self.session.execute(
                select(Drive).where(Drive.volume_serial_number == volume_serial_number)
            ).scalar_one_or_none()
            if drive:
                return drive
        if filesystem_uuid:
            drive = self.session.execute(
                select(Drive).where(Drive.filesystem_uuid == filesystem_uuid)
            ).scalar_one_or_none()
            if drive:
                return drive
        if fallback_fingerprint:
            drive = self.session.execute(
                select(Drive).where(Drive.fallback_fingerprint == fallback_fingerprint)
            ).scalar_one_or_none()
            if drive:
                return drive
        return None

    def get(self, drive_id: str) -> Optional[Drive]:
        return self.session.get(Drive, drive_id)

    def list_all(self) -> List[Drive]:
        return list(self.session.execute(select(Drive)).scalars().all())

    def register_or_update(
        self,
        volume_serial_number: Optional[str],
        filesystem_uuid: Optional[str],
        fallback_fingerprint: Optional[str],
        label: Optional[str],
        filesystem: Optional[str],
        mount_point: str,
        capacity_bytes: Optional[int],
        free_bytes: Optional[int],
    ) -> Drive:
        """
        Idempotent upsert used every time a drive is detected/connected.
        Reuses the existing Drive row (preserving its id and full history)
        if the fingerprint matches; otherwise creates a brand-new Drive.
        """
        now = datetime.now(timezone.utc)
        drive = self.find_by_fingerprint(volume_serial_number, filesystem_uuid, fallback_fingerprint)

        if drive is None:
            drive = Drive(
                id=uuid.uuid4().hex,
                volume_serial_number=volume_serial_number,
                filesystem_uuid=filesystem_uuid,
                fallback_fingerprint=fallback_fingerprint,
                label=label,
                filesystem=filesystem,
                current_mount_point=mount_point,
                capacity_bytes=capacity_bytes,
                free_bytes=free_bytes,
                status=DriveStatus.ONLINE,
                first_seen=now,
                last_seen=now,
            )
            self.session.add(drive)
        else:
            # Same physical disk, possibly under a NEW drive letter -- update, don't recreate.
            drive.current_mount_point = mount_point
            drive.label = label or drive.label
            drive.filesystem = filesystem or drive.filesystem
            drive.capacity_bytes = capacity_bytes if capacity_bytes is not None else drive.capacity_bytes
            drive.free_bytes = free_bytes if free_bytes is not None else drive.free_bytes
            drive.status = DriveStatus.ONLINE
            drive.last_seen = now

        self.session.flush()
        return drive

    def mark_offline(self, drive_id: str) -> None:
        drive = self.get(drive_id)
        if drive:
            drive.status = DriveStatus.OFFLINE
            self.session.flush()

    def mark_all_offline_except(self, connected_drive_ids: List[str]) -> None:
        """Called at app startup: any previously-online drive not currently detected goes OFFLINE."""
        for drive in self.list_all():
            if drive.id not in connected_drive_ids and drive.status == DriveStatus.ONLINE:
                drive.status = DriveStatus.OFFLINE
        self.session.flush()