"""
MainWindow: Phase 3 GUI shell + Phase 1(end) technical metadata wiring.

Provides:
  - A list of currently-connected drive letters (auto-detected).
  - A manual Browse button (QFileDialog) to pick ANY path.
  - A background QThread worker so scanning never freezes the UI.
  - FFprobe technical metadata extraction wired into the scan pipeline.
  - A results table listing every MediaFile in the database with its
    quality/resolution/codec, refreshed after each scan.
"""
from __future__ import annotations
import sys
from PySide6.QtCore import QThread, Signal, Qt
from mediavault.app.movie_detail_dialog import MovieDetailDialog
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog,
    QProgressBar, QTextEdit, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView,
)

from mediavault.database.connection import get_database
from mediavault.database.repositories.drive_repository import DriveRepository
from mediavault.scanner.drive_detector import get_drive_fingerprint, list_connected_drives
from mediavault.scanner.scan_manager import ScanManager, ScanManagerConfig
from mediavault.database.models import ScanJobType, MediaFile, VideoStream
from mediavault.archive.hashing import HashPolicy
from mediavault.metadata.technical_metadata_service import TechnicalMetadataService
from mediavault.core.configuration.settings import AppConfig
from mediavault.providers.tmdb import TMDBProvider, MetadataProviderError
from mediavault.identification.movie_identification_service import MovieIdentificationService
class ScanWorker(QThread):
    progress_text = Signal(str)
    finished_ok = Signal(dict)
    finished_error = Signal(str)


    def __init__(self, root_path: str, ffprobe_path: str, tmdb_api_key: str | None = None, tmdb_proxy: str | None = None):
        super().__init__()
        self.root_path = root_path
        self.ffprobe_path = ffprobe_path
        self.tmdb_api_key = tmdb_api_key
        self.tmdb_proxy = tmdb_proxy


    def run(self):
        try:
            db = get_database()
            with db.session() as session:
                drive_repo = DriveRepository(session)
                fingerprint = get_drive_fingerprint(self.root_path)

                self.progress_text.emit(f"Registering drive for {self.root_path} ...")
                drive = drive_repo.register_or_update(
                    volume_serial_number=fingerprint.volume_serial_number,
                    filesystem_uuid=fingerprint.filesystem_uuid,
                    fallback_fingerprint=fingerprint.fallback_fingerprint,
                    label=fingerprint.label,
                    filesystem=fingerprint.filesystem,
                    mount_point=fingerprint.mount_point,
                    capacity_bytes=fingerprint.capacity_bytes,
                    free_bytes=fingerprint.free_bytes,
                )

                self.progress_text.emit(f"Drive: {drive.label or drive.id} ({drive.status.value}). Scanning...")

                tech_service = TechnicalMetadataService(session, ffprobe_path=self.ffprobe_path)

                identification_service = None
                if self.tmdb_api_key:
                    try:
                        provider = TMDBProvider(
                            api_key=self.tmdb_api_key, proxy=self.tmdb_proxy,
                            timeout=30, max_retries=3,
                        )
                        self.progress_text.emit("Warming up TMDB connection...")
                        if provider.ping():
                            self.progress_text.emit("TMDB is reachable.")
                            identification_service = MovieIdentificationService(session, provider)
                        else:
                            self.progress_text.emit("WARNING: TMDB unreachable even after warm-up. Skipping identification.")
                    except MetadataProviderError as exc:
                        self.progress_text.emit(f"WARNING: TMDB unavailable ({exc}). Skipping identification.")
                else:
                    self.progress_text.emit("WARNING: TMDB_API_KEY not set. Skipping movie identification.")

                def on_file_ready(file_id: str):
                    self.progress_text.emit(f"Extracting technical metadata for file id={file_id[:8]}...")
                    tech_service.process_file(file_id)
                    if identification_service is not None:
                        self.progress_text.emit(f"Identifying movie for file id={file_id[:8]}...")
                        identification_service.process_file(file_id)

                scan_manager = ScanManager(
                    session=session,
                    config=ScanManagerConfig(hash_policy=HashPolicy.NEW_FILES_ONLY),
                    on_file_ready_for_metadata=on_file_ready,
                )
                job = scan_manager.start_or_resume(
                    drive_id=drive.id, root_path=self.root_path, job_type=ScanJobType.QUICK
                )

                result = {
                    "drive_label": drive.label or drive.id,
                    "discovered": job.files_discovered,
                    "processed": job.files_processed,
                    "added": job.files_added,
                    "modified": job.files_modified,
                    "missing": job.files_missing,
                    "failed": job.files_failed,
                    "status": job.status.value,
                }
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.finished_error.emit(str(exc))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MediaVault")
        self.setMinimumSize(900, 650)
        self.config = AppConfig.from_env()

        self.worker: ScanWorker | None = None
        self.selected_path: str | None = None

        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)

        tabs = QTabWidget()
        outer_layout.addWidget(tabs)

        tabs.addTab(self._build_scan_tab(), "Scan")
        tabs.addTab(self._build_files_tab(), "Files")


    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(5000)
        event.accept()


    # --- Scan tab ---

    def _build_scan_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("Detected drives (double-click to select):"))
        self.drive_list = QListWidget()
        self.drive_list.itemDoubleClicked.connect(self._on_drive_double_clicked)
        layout.addWidget(self.drive_list)

        refresh_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Drive List")
        self.refresh_btn.clicked.connect(self._refresh_drives)
        refresh_row.addWidget(self.refresh_btn)
        layout.addLayout(refresh_row)

        layout.addWidget(QLabel("Or choose any folder / drive manually:"))
        path_row = QHBoxLayout()
        self.path_label = QLabel("No path selected")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        path_row.addWidget(self.path_label, stretch=1)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

        self.scan_btn = QPushButton("Scan Selected Path")
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        self.scan_btn.setEnabled(False)
        layout.addWidget(self.scan_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Log:"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, stretch=1)

        self._refresh_drives()
        return tab

    def _refresh_drives(self):
        self.drive_list.clear()
        drives = list_connected_drives()
        if not drives:
            self.drive_list.addItem("No drives detected.")
            return
        for mount_point in drives:
            self.drive_list.addItem(QListWidgetItem(mount_point))

    def _on_drive_double_clicked(self, item: QListWidgetItem):
        text = item.text()
        if not text.endswith(":\\") and not text.endswith(":/"):
            return
        self._set_selected_path(text)

    def _on_browse_clicked(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select folder or drive root to scan", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if path:
            self._set_selected_path(path)

    def _set_selected_path(self, path: str):
        self.selected_path = path
        self.path_label.setText(path)
        self.scan_btn.setEnabled(True)

    def _on_scan_clicked(self):
        if not self.selected_path:
            return
        self.scan_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log_view.append(f"--- Starting scan of {self.selected_path} ---")

        self.worker = ScanWorker(
            self.selected_path,
            ffprobe_path=self.config.ffprobe_path,
            tmdb_api_key=self.config.tmdb_api_key,
        )        
        self.worker.progress_text.connect(self._on_progress_text)
        self.worker.finished_ok.connect(self._on_scan_finished)
        self.worker.finished_error.connect(self._on_scan_error)
        self.worker.start()

    def _on_progress_text(self, text: str):
        self.log_view.append(text)

    def _on_scan_finished(self, result: dict):
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.log_view.append(
            f"--- Scan finished [{result['status']}] ---\n"
            f"Drive: {result['drive_label']}\n"
            f"Discovered: {result['discovered']}  Processed: {result['processed']}\n"
            f"Added: {result['added']}  Modified: {result['modified']}  "
            f"Missing: {result['missing']}  Failed: {result['failed']}"
        )
        self._reload_files_table()

    def _on_scan_error(self, error_message: str):
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.log_view.append(f"--- ERROR: {error_message} ---")
        QMessageBox.critical(self, "Scan Error", error_message)

    # --- Files tab ---
    def _build_files_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        self.files_refresh_btn = QPushButton("Refresh File List")
        self.files_refresh_btn.clicked.connect(self._reload_files_table)
        top_row.addWidget(self.files_refresh_btn)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        self.files_table = QTableWidget()
        headers = ["Filename", "Movie", "Year", "Drive", "Path", "Size (MB)",
                   "Resolution", "Codec", "HDR", "State", "Error"]
        self.files_table.setColumnCount(len(headers))
        self.files_table.setHorizontalHeaderLabels(headers)
        self.files_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.files_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.files_table)
        self.files_table.itemDoubleClicked.connect(self._on_file_row_double_clicked)

        self._reload_files_table()
        return tab

    def _reload_files_table(self):
        db = get_database()
        with db.session() as session:
            files = session.query(MediaFile).all()
            self.files_table.setRowCount(len(files))
            for row, media_file in enumerate(files):
                video = session.query(VideoStream).filter_by(file_id=media_file.id).first()
                resolution = video.resolution_label if video and video.resolution_label else (
                    f"{video.width}x{video.height}" if video and video.width else "-"
                )
                codec = video.codec.upper() if video and video.codec else "-"
                hdr = (video.hdr_format or "SDR") if video else "-"

                movie_title = media_file.movie.title if media_file.movie else "(unidentified)"
                movie_year = str(media_file.movie.release_year) if media_file.movie and media_file.movie.release_year else "-"
                if media_file.movie and media_file.movie.needs_manual_review:
                    movie_title += " [REVIEW]"

                values = [
                    media_file.current_filename,
                    movie_title,
                    movie_year,
                    media_file.drive.label or media_file.drive_id[:8] if media_file.drive else "-",
                    media_file.relative_path,
                    f"{media_file.file_size / (1024 * 1024):.1f}",
                    resolution,
                    codec,
                    hdr,
                    media_file.scan_state.value,
                    media_file.last_error or "",
                ]
                for col, value in enumerate(values):
                    self.files_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _reload_files_table(self):
        db = get_database()
        with db.session() as session:
            files = session.query(MediaFile).all()
            self.files_table.setRowCount(len(files))
            for row, media_file in enumerate(files):
                video = session.query(VideoStream).filter_by(file_id=media_file.id).first()
                resolution = video.resolution_label if video and video.resolution_label else (
                    f"{video.width}x{video.height}" if video and video.width else "-"
                )
                codec = video.codec.upper() if video and video.codec else "-"
                hdr = (video.hdr_format or "SDR") if video else "-"

                movie_title = media_file.movie.title if media_file.movie else "(unidentified)"
                movie_year = str(media_file.movie.release_year) if media_file.movie and media_file.movie.release_year else "-"
                if media_file.movie and media_file.movie.needs_manual_review:
                    movie_title += " [REVIEW]"

                values = [
                    media_file.current_filename,
                    movie_title,
                    movie_year,
                    media_file.drive.label or media_file.drive_id[:8] if media_file.drive else "-",
                    media_file.relative_path,
                    f"{media_file.file_size / (1024 * 1024):.1f}",
                    resolution,
                    codec,
                    hdr,
                    media_file.scan_state.value,
                    media_file.last_error or "",
                ]
                for col, value in enumerate(values):
                    table_item = QTableWidgetItem(str(value))
                    if media_file.movie_id:
                        table_item.setData(Qt.UserRole, media_file.movie_id)
                    self.files_table.setItem(row, col, table_item)

    def _on_file_row_double_clicked(self, item: QTableWidgetItem):
        movie_id = item.data(Qt.UserRole)
        if not movie_id:
            return
        dialog = MovieDetailDialog(movie_id, parent=self)
        dialog.exec()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()