"""
Database connection pool for the NFL Data Engineering API.

Provides a PostgreSQL connection pool via psycopg2 when DATABASE_URL is set.
When DATABASE_URL is absent the API falls back to Parquet reads (dev mode).

Usage in services:
    from web.api.db import get_connection, is_db_enabled

    if is_db_enabled():
        with get_connection() as conn:
            ...
"""

import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)

DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

_pool = None


def _get_pool():
    """Lazily initialise the connection pool on first use."""
    global _pool
    if _pool is not None:
        return _pool

    if DATABASE_URL is None:
        raise RuntimeError("DATABASE_URL is not set -- cannot create pool")

    try:
        from psycopg2 import pool as pg_pool

        _pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL,
        )
        logger.info("PostgreSQL connection pool created")
        return _pool
    except Exception:
        logger.exception("Failed to create PostgreSQL connection pool")
        raise


def is_db_enabled() -> bool:
    """Return True when a DATABASE_URL is configured."""
    return DATABASE_URL is not None


@contextmanager
def get_connection() -> Generator:
    """Yield a connection from the pool; returns it on exit.

    Usage::

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def check_health() -> bool:
    """Return True if the database is reachable."""
    if not is_db_enabled():
        return False
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False
