"""
Manual smoke test / entry point for Phase 1.
Run this directly (python -m mediavault.main) to verify:
  - database creation
  - drive registration
  - scan job creation
  - incremental + resumable scanning
Requires: pip install sqlalchemy
"""
from __future__ import annotations
import os
import sys

from mediavault.database.connection import get_database
from mediavault.database.repositories.drive_repository import DriveRepository
from mediavault.scanner.drive_detector import get_drive_fingerprint
from mediavault.scanner.scan_manager import ScanManager, ScanManagerConfig
from mediavault.database.models import ScanJobType
from mediavault.archive.hashing import HashPolicy


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m mediavault.main <path-to-scan>")
        print("Example: python -m mediavault.main H:\\")
        sys.exit(1)

    root_path = sys.argv[1]
    if not os.path.isdir(root_path):
        print(f"Path does not exist: {root_path}")
        sys.exit(1)

    db = get_database()

    with db.session() as session:
        drive_repo = DriveRepository(session)
        fingerprint = get_drive_fingerprint(root_path)

        drive = drive_repo.register_or_update(
            volume_serial_number=fingerprint.volume_serial_number,
            filesystem_uuid=fingerprint.filesystem_uuid,
            fallback_fingerprint=fingerprint.fallback_fingerprint,
            label=fingerprint.label,
            filesystem=fingerprint.filesystem,
            mount_point=root_path,
            capacity_bytes=fingerprint.capacity_bytes,
            free_bytes=fingerprint.free_bytes,
        )
        print(f"Drive registered/updated: {drive}")

        scan_manager = ScanManager(
            session=session,
            config=ScanManagerConfig(hash_policy=HashPolicy.NEW_FILES_ONLY),
        )
        job = scan_manager.start_or_resume(drive_id=drive.id, root_path=root_path, job_type=ScanJobType.QUICK)
        print(f"Scan finished: {job}")
        print(f"  discovered={job.files_discovered} processed={job.files_processed} "
              f"added={job.files_added} modified={job.files_modified} missing={job.files_missing} "
              f"failed={job.files_failed}")


if __name__ == "__main__":
    main()