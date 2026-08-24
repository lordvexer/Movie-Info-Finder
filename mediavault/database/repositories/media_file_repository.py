"""
MediaFileRepository + ScanJobRepository: persistence for the incremental
scan engine. Designed so the ScanManager can crash at any point and resume
without reprocessing completed work.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediavault.database.models import (
    MediaFile, ScanJob, ScanItem, FileScanState, ScanJobStatus, ScanItemStatus, PipelineStage,
)


class MediaFileRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_by_drive_and_path(self, drive_id: str, relative_path: str) -> Optional[MediaFile]:
        return self.session.execute(
            select(MediaFile).where(
                MediaFile.drive_id == drive_id, MediaFile.relative_path == relative_path
            )
        ).scalar_one_or_none()

    def find_by_drive_size_and_hash(
        self, drive_id: str, file_size: int, fast_hash: Optional[str]
    ) -> List[MediaFile]:
        """Used for MOVED/RENAMED detection: same drive, same size, same fast hash, different path."""
        stmt = select(MediaFile).where(MediaFile.drive_id == drive_id, MediaFile.file_size == file_size)
        if fast_hash:
            stmt = stmt.where(MediaFile.fast_hash == fast_hash)
        return list(self.session.execute(stmt).scalars().all())

    def list_active_by_drive(self, drive_id: str) -> List[MediaFile]:
        return list(
            self.session.execute(
                select(MediaFile).where(MediaFile.drive_id == drive_id, MediaFile.is_missing == False)  # noqa: E712
            ).scalars().all()
        )

    def create(self, **kwargs) -> MediaFile:
        kwargs.setdefault("id", uuid.uuid4().hex)
        media_file = MediaFile(**kwargs)
        self.session.add(media_file)
        self.session.flush()
        return media_file

    def mark_missing(self, media_file: MediaFile) -> None:
        media_file.is_missing = True
        media_file.scan_state = FileScanState.MISSING
        media_file.missing_since = datetime.now(timezone.utc)
        self.session.flush()

    def mark_found_again(self, media_file: MediaFile) -> None:
        media_file.is_missing = False
        media_file.missing_since = None
        self.session.flush()


class ScanJobRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, drive_id: str, job_type, root_path: str) -> ScanJob:
        job = ScanJob(
            id=uuid.uuid4().hex,
            drive_id=drive_id,
            job_type=job_type,
            root_path=root_path,
            status=ScanJobStatus.QUEUED,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, job_id: str) -> Optional[ScanJob]:
        return self.session.get(ScanJob, job_id)

    def find_resumable_job(self, drive_id: str) -> Optional[ScanJob]:
        """
        A job is resumable if it exists for this drive and is not in a terminal
        state (COMPLETED/CANCELLED). INTERRUPTED/FAILED/PAUSED/SCANNING(crashed)
        are all resumable -- we never assume a non-completed job means "start over".
        """
        return self.session.execute(
            select(ScanJob)
            .where(
                ScanJob.drive_id == drive_id,
                ScanJob.status.in_([
                    ScanJobStatus.SCANNING, ScanJobStatus.PAUSED,
                    ScanJobStatus.INTERRUPTED, ScanJobStatus.QUEUED,
                ]),
            )
            .order_by(ScanJob.created_at.desc())
        ).scalars().first()

    def mark_started(self, job: ScanJob) -> None:
        job.status = ScanJobStatus.SCANNING
        if job.started_at is None:
            job.started_at = datetime.now(timezone.utc)
        self.session.flush()

    def mark_interrupted(self, job: ScanJob, reason: str) -> None:
        job.status = ScanJobStatus.INTERRUPTED
        job.last_error = reason
        self.session.flush()

    def mark_completed(self, job: ScanJob) -> None:
        job.status = ScanJobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        job.progress_percent = 100.0
        self.session.flush()

    def mark_failed(self, job: ScanJob, reason: str) -> None:
        job.status = ScanJobStatus.FAILED
        job.last_error = reason
        job.finished_at = datetime.now(timezone.utc)
        self.session.flush()

    def update_progress(self, job: ScanJob) -> None:
        if job.files_discovered:
            job.progress_percent = round(100.0 * job.files_processed / job.files_discovered, 2)
        self.session.flush()

    # --- ScanItem: the per-file resumability ledger ---

    def add_items_bulk(self, job_id: str, paths: List[tuple[str, str]]) -> None:
        """paths: list of (full_path, relative_path). Bulk-inserted once at discovery time."""
        items = [
            ScanItem(id=uuid.uuid4().hex, job_id=job_id, full_path=full, relative_path=rel)
            for full, rel in paths
        ]
        self.session.add_all(items)
        self.session.flush()

    def get_pending_items(self, job_id: str) -> List[ScanItem]:
        """
        Returns items not yet DONE. Includes IN_PROGRESS items left over from a
        crash (they get reprocessed from their last known pipeline_stage, not
        from PipelineStage.DISCOVERED, avoiding wasted work).
        """
        return list(
            self.session.execute(
                select(ScanItem).where(
                    ScanItem.job_id == job_id,
                    ScanItem.status.in_([ScanItemStatus.PENDING, ScanItemStatus.IN_PROGRESS]),
                )
            ).scalars().all()
        )

    def count_done(self, job_id: str) -> int:
        return len(
            list(
                self.session.execute(
                    select(ScanItem).where(ScanItem.job_id == job_id, ScanItem.status == ScanItemStatus.DONE)
                ).scalars().all()
            )
        )

    def mark_item_in_progress(self, item: ScanItem, stage: PipelineStage) -> None:
        item.status = ScanItemStatus.IN_PROGRESS
        item.pipeline_stage = stage
        item.attempt_count += 1
        if item.started_at is None:
            item.started_at = datetime.now(timezone.utc)
        self.session.flush()  # persisted immediately -- not batched in RAM

    def mark_item_stage(self, item: ScanItem, stage: PipelineStage) -> None:
        item.pipeline_stage = stage
        self.session.flush()

    def mark_item_done(self, item: ScanItem, file_id: Optional[str] = None) -> None:
        item.status = ScanItemStatus.DONE
        item.pipeline_stage = PipelineStage.COMPLETED
        item.finished_at = datetime.now(timezone.utc)
        if file_id:
            item.file_id = file_id
        self.session.flush()

    def mark_item_failed(self, item: ScanItem, error: str) -> None:
        item.status = ScanItemStatus.FAILED
        item.error_message = error
        item.finished_at = datetime.now(timezone.utc)
        self.session.flush()