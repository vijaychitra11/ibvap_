from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite file lives in backend/, anchored to this file rather than the shell's
# working directory, so the same DB is used no matter where uvicorn is launched.
# Swap this URL for a Postgres/MySQL URL later without touching any other file.
BACKEND_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = f"sqlite:///{BACKEND_DIR / 'ibvap.db'}"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
