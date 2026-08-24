"""
Diagnostic script: dumps every MediaFile + linked Movie row currently in the
database, correctly separating crew by role (director/writer/producer/composer)
by querying the movie_crew association table directly instead of the flat
Movie.crew relationship (which mixes all roles together).
"""
from sqlalchemy import select

from mediavault.database.connection import get_database
from mediavault.database.models import MediaFile, Drive, Movie, Person
from mediavault.database.models.movie import movie_crew

db = get_database()


def people_by_role(session, movie_id: str, role: str) -> list[str]:
    rows = session.execute(
        select(Person.name)
        .join(movie_crew, movie_crew.c.person_id == Person.id)
        .where(movie_crew.c.movie_id == movie_id, movie_crew.c.role == role)
    ).scalars().all()
    return list(rows)


with db.session() as session:
    print("=== DRIVES ===")
    for drive in session.query(Drive).all():
        print(f"id={drive.id[:8]} label={drive.label} mount={drive.current_mount_point!r} "
              f"serial={drive.volume_serial_number} status={drive.status.value}")

    print()
    print("=== MEDIA FILES ===")
    files = session.query(MediaFile).order_by(MediaFile.filename).all()
    for f in files:
        print(f"file_id={f.id[:8]} filename={f.filename!r}")
        print(f"  state={f.scan_state.value} error={f.last_error!r}")
        print(f"  movie_id={f.movie_id}")
        if f.movie:
            m = f.movie
            print(f"  MOVIE: title={m.title!r} original_title={m.original_title!r} year={m.release_year} "
                  f"confidence={m.identification_confidence} needs_review={m.needs_manual_review}")
            print(f"    overview={(m.overview[:80] if m.overview else None)!r}")
            print(f"    genres={[g.name for g in m.genres]}")
            print(f"    DIRECTORS={people_by_role(session, m.id, 'DIRECTOR')}")
            print(f"    WRITERS={people_by_role(session, m.id, 'WRITER')}")
            print(f"    PRODUCERS={people_by_role(session, m.id, 'PRODUCER')}")
            print(f"    COMPOSERS={people_by_role(session, m.id, 'COMPOSER')}")
            print(f"    CAST(top5)={[p.name for p in m.cast][:5]}")
            print(f"    external_ids={m.external_ids}")
            print(f"    rating={m.rating} popularity={m.popularity}")
        else:
            print("  MOVIE: None (not identified)")
        print()

    print(f"TOTAL DRIVES: {session.query(Drive).count()}")
    print(f"TOTAL FILES: {session.query(MediaFile).count()}")
    print(f"TOTAL MOVIES: {session.query(Movie).count()}")