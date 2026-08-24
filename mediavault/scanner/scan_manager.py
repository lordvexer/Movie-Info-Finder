"""
ScanManager: orchestrates a full drive scan using the persistent ScanJob /
ScanItem ledger so the process is resumable and crash-safe.

CRITICAL INVARIANT: relative_path for every MediaFile is ALWAYS computed
relative to the DRIVE ROOT (drive.current_mount_point), never relative to
whatever sub-folder the user happened to pick for this particular scan.
This guarantees the same physical file always gets the same relative_path
no matter which folder was scanned, which is what makes
find_by_drive_and_path() correctly recognize a file as "already known"
instead of creating a duplicate row.
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from mediavault.database.models import (
    ScanJobType, ScanItemStatus, PipelineStage, FileScanState, HashTier, Drive,
)
from mediavault.database.repositories.media_file_repository import (
    MediaFileRepository, ScanJobRepository,
)
from mediavault.scanner.filesystem_scanner import walk_video_files, DiscoveredFile
from mediavault.scanner.file_state import compare_file_state, ExistingFileSnapshot
from mediavault.archive.hashing import compute_fast_hash, HashPolicy, should_hash

logger = logging.getLogger("mediavault.scan_manager")


@dataclass
class ScanManagerConfig:
    hash_policy: HashPolicy = HashPolicy.NEW_FILES_ONLY
    batch_commit_every_n_files: int = 1


class ScanManager:
    def __init__(
        self,
        session: Session,
        config: Optional[ScanManagerConfig] = None,
        on_file_ready_for_metadata: Optional[Callable[[str], None]] = None,
    ):
        self.session = session
        self.config = config or ScanManagerConfig()
        self.file_repo = MediaFileRepository(session)
        self.job_repo = ScanJobRepository(session)
        self.on_file_ready_for_metadata = on_file_ready_for_metadata

    def start_or_resume(self, drive_id: str, root_path: str, job_type: ScanJobType = ScanJobType.QUICK):
        root_path = os.path.normpath(root_path)

        drive = self.session.get(Drive, drive_id)
        if drive is None:
            raise ValueError(f"Drive {drive_id} not found")
        drive_root = os.path.normpath(drive.current_mount_point)

        logger.info("start_or_resume: root_path=%s drive_root=%s", root_path, drive_root)

        existing_job = self.job_repo.find_resumable_job(drive_id)
        if existing_job is not None:
            logger.info("Resuming existing scan job %s (%d/%d done)",
                        existing_job.id, existing_job.files_processed, existing_job.files_discovered)
            job = existing_job
        else:
            job = self.job_repo.create(drive_id=drive_id, job_type=job_type, root_path=root_path)
            logger.info("Created new scan job %s for drive %s", job.id, drive_id)

        self.job_repo.mark_started(job)
        self.session.commit()

        try:
            self._ensure_discovery(job, root_path, drive_root)
            self._process_pending_items(job, drive_id, drive_root)
            self._detect_missing_files(job, drive_id)
            self.job_repo.mark_completed(job)
            self.session.commit()
        except KeyboardInterrupt:
            self.job_repo.mark_interrupted(job, "Interrupted by user/OS")
            self.session.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scan job %s failed", job.id)
            self.job_repo.mark_interrupted(job, str(exc))
            self.session.commit()
            raise

        return job

    def _ensure_discovery(self, job, root_path: str, drive_root: str) -> None:
        from sqlalchemy import select
        from mediavault.database.models import ScanItem

        existing_paths = set(
            self.session.execute(
                select(ScanItem.full_path).where(ScanItem.job_id == job.id)
            ).scalars().all()
        )

        new_items = []
        discovered_count = 0
        for discovered in walk_video_files(root_path):
            discovered_count += 1
            if discovered.full_path in existing_paths:
                continue
            # ALWAYS relative to drive_root, never to root_path (the scan target).
            relative_to_drive = os.path.relpath(discovered.full_path, drive_root)
            new_items.append((discovered.full_path, relative_to_drive))

        if new_items:
            self.job_repo.add_items_bulk(job.id, new_items)

        if discovered_count > job.files_discovered:
            job.files_discovered = discovered_count
            self.session.flush()
        self.session.commit()

    def _process_pending_items(self, job, drive_id: str, drive_root: str) -> None:
        pending_items = self.job_repo.get_pending_items(job.id)
        logger.info("Job %s: %d pending items to process", job.id, len(pending_items))

        for idx, item in enumerate(pending_items):
            try:
                self._process_single_item(job, drive_id, item, drive_root)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Item %s failed", item.id)
                self.job_repo.mark_item_failed(item, str(exc))
                job.files_failed += 1
            finally:
                job.files_processed += 1
                self.job_repo.update_progress(job)
                if (idx + 1) % self.config.batch_commit_every_n_files == 0:
                    self.session.commit()

        self.session.commit()

    def _process_single_item(self, job, drive_id: str, item, drive_root: str) -> None:
        self.job_repo.mark_item_in_progress(item, PipelineStage.IDENTIFIED)

        if not os.path.exists(item.full_path):
            self.job_repo.mark_item_done(item)
            return

        stat = os.stat(item.full_path)
        filename = os.path.basename(item.full_path)
        extension = os.path.splitext(filename)[1].lower()

        existing = self.file_repo.find_by_drive_and_path(drive_id, item.relative_path)
        existing_snapshot = None
        if existing is not None:
            existing_snapshot = ExistingFileSnapshot(
                id=existing.id,
                relative_path=existing.relative_path,
                file_size=existing.file_size,
                modified_time=existing.modified_time.timestamp() if existing.modified_time else None,
                fast_hash=existing.fast_hash,
            )

        discovered = DiscoveredFile(
            full_path=item.full_path, relative_path=item.relative_path, filename=filename,
            extension=extension, size=stat.st_size, modified_time=stat.st_mtime, created_time=stat.st_ctime,
        )
        self.job_repo.mark_item_stage(item, PipelineStage.STATE_COMPARED)
        state = compare_file_state(discovered, existing_snapshot)

        moved_from: Optional[str] = None
        if existing is None:
            candidates = self.file_repo.find_by_drive_size_and_hash(drive_id, discovered.size, None)
            candidates = [c for c in candidates if c.relative_path != item.relative_path and c.is_missing]
            if candidates:
                existing = candidates[0]
                moved_from = existing.relative_path
                state = FileScanState.MOVED

        is_new = existing is None
        fast_hash_value = None
        if should_hash(self.config.hash_policy, is_new_file=is_new, is_duplicate_pass=False):
            fast_hash_value = compute_fast_hash(item.full_path, discovered.size)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        if existing is None:
            media_file = self.file_repo.create(
                drive_id=drive_id,
                relative_path=item.relative_path,
                filename=filename,
                extension=extension,
                original_filename=filename,
                current_filename=filename,
                file_size=discovered.size,
                modified_time=datetime.fromtimestamp(discovered.modified_time, tz=timezone.utc),
                created_time=datetime.fromtimestamp(discovered.created_time, tz=timezone.utc),
                fast_hash=fast_hash_value,
                hash_tier_computed=HashTier.FAST if fast_hash_value else HashTier.NONE,
                scan_state=FileScanState.NEW,
                pipeline_stage=PipelineStage.STATE_COMPARED,
                last_scan_time=now,
            )
            job.files_added += 1
        else:
            media_file = existing
            if moved_from:
                media_file.relative_path = item.relative_path
                media_file.filename = filename
                media_file.current_filename = filename
            media_file.scan_state = state
            media_file.file_size = discovered.size
            media_file.modified_time = datetime.fromtimestamp(discovered.modified_time, tz=timezone.utc)
            media_file.last_scan_time = now
            if fast_hash_value:
                media_file.fast_hash = fast_hash_value
                media_file.hash_tier_computed = HashTier.FAST
            self.file_repo.mark_found_again(media_file)
            if state == FileScanState.MODIFIED:
                job.files_modified += 1

        self.session.flush()

        if self.on_file_ready_for_metadata and state in (FileScanState.NEW, FileScanState.MODIFIED):
            self.job_repo.mark_item_stage(item, PipelineStage.TECH_EXTRACTED)
            self.on_file_ready_for_metadata(media_file.id)

        self.job_repo.mark_item_done(item, file_id=media_file.id)

    def _detect_missing_files(self, job, drive_id: str) -> None:
        from sqlalchemy import select
        from mediavault.database.models import ScanItem

        touched_file_ids = set(
            self.session.execute(
                select(ScanItem.file_id).where(ScanItem.job_id == job.id, ScanItem.file_id.isnot(None))
            ).scalars().all()
        )

        active_files = self.file_repo.list_active_by_drive(drive_id)
        missing_count = 0
        for media_file in active_files:
            if media_file.id not in touched_file_ids:
                self.file_repo.mark_missing(media_file)
                missing_count += 1

        job.files_missing = missing_count
        self.session.flush()