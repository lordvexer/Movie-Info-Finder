"""
MovieDetailDialog: shows full details for a single Movie -- poster, overview,
genres, director/writer/cast, and every physical MediaFile version linked to
it (with drive/quality/online-offline status), per spec section 54.

Poster is ALWAYS read from the local artwork cache first (see
mediavault.artwork.manager) -- it is never re-downloaded from the internet
just to display a dialog that was already downloaded once during scanning.
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget,
    QGroupBox, QListWidget, QListWidgetItem,
)

from sqlalchemy import select

from mediavault.database.connection import get_database
from mediavault.database.models import Movie, MediaFile, VideoStream, Drive, Person
from mediavault.database.models.movie import movie_crew
from mediavault.artwork.manager import get_local_poster_path


def _people_by_role(session, movie_id: str, role: str) -> list[str]:
    rows = session.execute(
        select(Person.name)
        .join(movie_crew, movie_crew.c.person_id == Person.id)
        .where(movie_crew.c.movie_id == movie_id, movie_crew.c.role == role)
    ).scalars().all()
    return list(rows)


class MovieDetailDialog(QDialog):
    def __init__(self, movie_id: str, parent=None):
        super().__init__(parent)
        self.movie_id = movie_id
        self.setWindowTitle("Movie Details")
        self.setMinimumSize(750, 600)

        outer_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        self.content_layout = QVBoxLayout(content)
        self._load_movie()

    def _load_movie(self):
        db = get_database()
        with db.session() as session:
            movie = session.get(Movie, self.movie_id)
            if movie is None:
                self.content_layout.addWidget(QLabel("Movie not found."))
                return

            top_row = QHBoxLayout()

            poster_label = QLabel()
            poster_label.setFixedSize(200, 300)
            poster_label.setAlignment(Qt.AlignCenter)
            poster_label.setStyleSheet("border: 1px solid #888;")

            local_poster = get_local_poster_path(movie.id)
            if local_poster is not None:
                pixmap = QPixmap(str(local_poster))
                scaled = pixmap.scaled(200, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                poster_label.setPixmap(scaled)
            else:
                poster_label.setText("No poster cached")
            top_row.addWidget(poster_label)

            info_col = QVBoxLayout()
            title_text = f"{movie.title} ({movie.release_year or '?'})"
            if movie.original_title and movie.original_title != movie.title:
                title_text += f"\n{movie.original_title}"
            title_label = QLabel(title_text)
            title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
            title_label.setWordWrap(True)
            info_col.addWidget(title_label)

            if movie.tagline:
                tagline_label = QLabel(movie.tagline)
                tagline_label.setStyleSheet("font-style: italic; color: #666;")
                tagline_label.setWordWrap(True)
                info_col.addWidget(tagline_label)

            meta_parts = []
            if movie.rating:
                meta_parts.append(f"Rating: {movie.rating:.1f}/10 ({movie.vote_count or 0} votes)")
            if movie.runtime_minutes:
                meta_parts.append(f"Runtime: {movie.runtime_minutes} min")
            if movie.genres:
                meta_parts.append("Genres: " + ", ".join(g.name for g in movie.genres))
            for part in meta_parts:
                info_col.addWidget(QLabel(part))

            review_note = QLabel(
                f"Identification confidence: {(movie.identification_confidence or 0) * 100:.1f}%"
                + ("  [NEEDS MANUAL REVIEW]" if movie.needs_manual_review else "")
            )
            if movie.needs_manual_review:
                review_note.setStyleSheet("color: #b00; font-weight: bold;")
            info_col.addWidget(review_note)

            if movie.external_ids:
                ids_text = " | ".join(f"{k.upper()}: {v}" for k, v in movie.external_ids.items())
                info_col.addWidget(QLabel(ids_text))

            info_col.addStretch(1)
            top_row.addLayout(info_col, stretch=1)
            self.content_layout.addLayout(top_row)

            if movie.overview:
                overview_box = QGroupBox("Overview")
                overview_layout = QVBoxLayout(overview_box)
                overview_label = QLabel(movie.overview)
                overview_label.setWordWrap(True)
                overview_layout.addWidget(overview_label)
                self.content_layout.addWidget(overview_box)

            people_box = QGroupBox("Cast & Crew")
            people_layout = QVBoxLayout(people_box)
            directors = _people_by_role(session, movie.id, "DIRECTOR")
            writers = _people_by_role(session, movie.id, "WRITER")
            producers = _people_by_role(session, movie.id, "PRODUCER")
            composers = _people_by_role(session, movie.id, "COMPOSER")
            cast_names = [p.name for p in movie.cast][:10]

            for label_text, names in [
                ("Director(s)", directors), ("Writer(s)", writers),
                ("Producer(s)", producers), ("Composer(s)", composers),
                ("Cast", cast_names),
            ]:
                if names:
                    row_label = QLabel(f"<b>{label_text}:</b> {', '.join(names)}")
                    row_label.setWordWrap(True)
                    people_layout.addWidget(row_label)
            self.content_layout.addWidget(people_box)

            files_box = QGroupBox("Physical Files (versions)")
            files_layout = QVBoxLayout(files_box)
            files_list = QListWidget()
            media_files = session.query(MediaFile).filter_by(movie_id=movie.id).all()
            for media_file in media_files:
                video = session.query(VideoStream).filter_by(file_id=media_file.id).first()
                resolution = video.resolution_label if video and video.resolution_label else "-"
                codec = video.codec.upper() if video and video.codec else "-"
                hdr = video.hdr_format if video and video.hdr_format else "SDR"
                drive = session.get(Drive, media_file.drive_id)
                drive_status = drive.status.value if drive else "UNKNOWN"
                size_gb = media_file.file_size / (1024 ** 3)

                item_text = (
                    f"{resolution} {codec} {hdr} | {size_gb:.2f} GB | "
                    f"Drive: {drive.label or drive.id[:8] if drive else '?'} [{drive_status}] | "
                    f"{media_file.relative_path}"
                )
                files_list.addItem(QListWidgetItem(item_text))
            files_layout.addWidget(files_list)
            self.content_layout.addWidget(files_box)