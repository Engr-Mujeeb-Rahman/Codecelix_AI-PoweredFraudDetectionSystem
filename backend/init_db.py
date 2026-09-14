"""Create all database tables (empty, no demo data).

Usage:
    python init_db.py            # create tables in the DB from DATABASE_URL
    python init_db.py --drop     # drop all tables first, then recreate
"""
import sys

from app.db.session import Base, engine


def main(drop: bool = False):
    if drop:
        print("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        print("All tables dropped.")

    print("Creating tables...")
    import app.models  # noqa: F401 — register all models on Base metadata
    Base.metadata.create_all(bind=engine)

    from sqlalchemy import inspect
    tables = sorted(inspect(engine).get_table_names())
    print(f"Done. {len(tables)} tables ready:")
    for t in tables:
        print(f"  - {t}")


if __name__ == "__main__":
    main(drop="--drop" in sys.argv)
