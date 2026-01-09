"""
Project Aegis - Database Provider Abstraction Layer

Provides a unified interface for database operations, supporting:
- SQLite (development/testing)
- PostgreSQL (production, with connection pooling)

Usage:
    from db_provider import get_db_provider
    db = get_db_provider()
    db.execute("INSERT INTO ...", params)
"""

import os
import abc
import logging
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseProviderError(Exception):
    """Raised when a database operation fails."""
    pass


class DatabaseProvider(abc.ABC):
    """Abstract base class for database providers."""

    @abc.abstractmethod
    def execute(self, query: str, params: Tuple = ()) -> None:
        """Execute a query without returning results."""
        pass

    @abc.abstractmethod
    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        """Execute a query with multiple parameter sets."""
        pass

    @abc.abstractmethod
    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute a query and return one row as a dict."""
        pass

    @abc.abstractmethod
    def fetch_all(self, query: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return all rows as dicts."""
        pass

    @abc.abstractmethod
    def execute_script(self, script: str) -> None:
        """Execute a SQL script (multiple statements)."""
        pass

    @abc.abstractmethod
    @contextmanager
    def transaction(self):
        """Context manager for transactions."""
        pass


class SQLiteProvider(DatabaseProvider):
    """
    SQLite database provider for development and testing.

    Note: SQLite has write concurrency limitations.
    Use PostgreSQLProvider for production deployments.
    """

    def __init__(self, db_file: str = "aegis_zkp.db"):
        import sqlite3
        self._db_file = db_file
        self._sqlite3 = sqlite3
        logger.info(f"SQLiteProvider initialized: {db_file}")

    def _get_connection(self):
        conn = self._sqlite3.connect(self._db_file)
        conn.row_factory = self._sqlite3.Row
        return conn

    def execute(self, query: str, params: Tuple = ()) -> None:
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        with self._get_connection() as conn:
            conn.executemany(query, params_list)
            conn.commit()

    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def execute_script(self, script: str) -> None:
        with self._get_connection() as conn:
            conn.executescript(script)
            conn.commit()

    @contextmanager
    def transaction(self):
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class PostgreSQLProvider(DatabaseProvider):
    """
    PostgreSQL database provider for production.

    Requires:
        - AEGIS_PG_HOST, AEGIS_PG_PORT, AEGIS_PG_DATABASE
        - AEGIS_PG_USER, AEGIS_PG_PASSWORD

    Features connection pooling for high concurrency.
    """

    def __init__(self):
        self._host = os.environ.get("AEGIS_PG_HOST", "localhost")
        self._port = int(os.environ.get("AEGIS_PG_PORT", "5432"))
        self._database = os.environ.get("AEGIS_PG_DATABASE", "aegis")
        self._user = os.environ.get("AEGIS_PG_USER", "aegis")
        self._password = os.environ.get("AEGIS_PG_PASSWORD", "")
        self._pool = None

        logger.info(f"PostgreSQLProvider initialized: {self._host}:{self._port}/{self._database}")

    def _get_pool(self):
        if self._pool is None:
            try:
                from psycopg2 import pool
                self._pool = pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=20,
                    host=self._host,
                    port=self._port,
                    database=self._database,
                    user=self._user,
                    password=self._password
                )
            except ImportError:
                raise DatabaseProviderError(
                    "psycopg2 not installed. Run: pip install psycopg2-binary"
                )
        return self._pool

    def _get_connection(self):
        return self._get_pool().getconn()

    def _put_connection(self, conn):
        self._get_pool().putconn(conn)

    def execute(self, query: str, params: Tuple = ()) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
        finally:
            self._put_connection(conn)

    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(query, params_list)
            conn.commit()
        finally:
            self._put_connection(conn)

    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                if row is None:
                    return None
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
        finally:
            self._put_connection(conn)

    def fetch_all(self, query: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in rows]
        finally:
            self._put_connection(conn)

    def execute_script(self, script: str) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(script)
            conn.commit()
        finally:
            self._put_connection(conn)

    @contextmanager
    def transaction(self):
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_connection(conn)


_db_provider_instance = None

def get_db_provider() -> DatabaseProvider:
    """
    Factory function returning the appropriate database provider.

    Set AEGIS_DB_BACKEND environment variable:
        - "sqlite" (default): SQLiteProvider
        - "postgresql": PostgreSQLProvider

    Returns:
        Configured DatabaseProvider instance (singleton)
    """
    global _db_provider_instance

    if _db_provider_instance is not None:
        return _db_provider_instance

    backend = os.environ.get("AEGIS_DB_BACKEND", "sqlite").lower()

    logger.info(f"Initializing database provider: {backend}")

    if backend == "postgresql" or backend == "postgres":
        _db_provider_instance = PostgreSQLProvider()
    else:
        db_file = os.environ.get("AEGIS_DB_FILE", "aegis_zkp.db")
        _db_provider_instance = SQLiteProvider(db_file)

    return _db_provider_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Test with SQLite
    db = get_db_provider()
    print(f"Provider: {type(db).__name__}")

    # Create test table
    db.execute_script("""
        CREATE TABLE IF NOT EXISTS test_table (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)

    db.execute("INSERT INTO test_table (name) VALUES (?)", ("test_entry",))
    result = db.fetch_one("SELECT * FROM test_table WHERE name = ?", ("test_entry",))
    print(f"Fetched: {result}")
