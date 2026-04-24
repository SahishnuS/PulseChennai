"""
Database Connection Pool
========================
asyncpg-based connection pool with FastAPI lifespan integration.
Gracefully degrades if PostgreSQL is unreachable.
"""

import logging
import asyncpg
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def connect(database_url: str) -> Optional[asyncpg.Pool]:
    """Create the asyncpg connection pool. Call during FastAPI startup."""
    global _pool
    # asyncpg uses raw postgresql:// URIs, not SQLAlchemy-style
    raw_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        _pool = await asyncpg.create_pool(
            raw_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
            statement_cache_size=100,
        )
        # Verify connection
        async with _pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            logger.info(f"Database connected: {version[:60]}...")
        return _pool
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        _pool = None
        return None


async def disconnect():
    """Close the connection pool. Call during FastAPI shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed.")


def get_pool() -> Optional[asyncpg.Pool]:
    """Get the current connection pool (may be None if DB is down)."""
    return _pool


@asynccontextmanager
async def acquire():
    """Acquire a connection from the pool with proper error handling."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call connect() first.")
    async with _pool.acquire() as conn:
        yield conn


async def execute_migration(migration_path: str):
    """Run a SQL migration file against the database."""
    if _pool is None:
        logger.warning("Cannot run migration: no database connection.")
        return
    try:
        with open(migration_path, "r") as f:
            sql = f.read()
        async with _pool.acquire() as conn:
            await conn.execute(sql)
        logger.info(f"Migration executed: {migration_path}")
    except Exception as e:
        logger.error(f"Migration failed: {e}")


async def health_check() -> dict:
    """Check database connectivity and return status."""
    if _pool is None:
        return {"status": "disconnected", "pool_size": 0}
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {
            "status": "connected",
            "pool_size": _pool.get_size(),
            "pool_free": _pool.get_idle_size(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
