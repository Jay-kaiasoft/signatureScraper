# db.py
"""
Creates the SQLAlchemy engine and a scoped session factory.
Reads settings from .env (DATABASE_URL).
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env")

# echo=True for SQL debug
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

@contextmanager
def session_scope():
    """
    Provide a transactional scope for a series of operations.
    Commits on success; rolls back on exception.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
        print("DB session committed")
    except Exception:
        session.rollback()
        print("DB session rolled back")
        raise
    finally:
        session.close()
