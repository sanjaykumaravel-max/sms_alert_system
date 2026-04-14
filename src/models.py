"""
Database Models and Connection Pooling for SMS Alert App.

This module provides:
- SQLAlchemy models for data persistence
- Connection pooling configuration
- Database migration support with Alembic
- Async database operations
"""

import os
from typing import List, Dict, Any, Optional, Generator, AsyncGenerator
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.pool import QueuePool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import redis.asyncio as redis

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sms_alert.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# SQLAlchemy setup
Base = declarative_base()

# Connection pooling settings
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))

# Create sync engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_pre_ping=True,  # Test connections before use
    echo=False  # Set to True for SQL debugging
)

# Create async engine
async_engine = create_async_engine(
    DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://") if DATABASE_URL.startswith("sqlite") else DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_pre_ping=True
)

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession)

# Database Models
class Machine(Base):
    """Machine model for equipment tracking."""
    __tablename__ = "machines"

    id = Column(String(50), primary_key=True, index=True)
    type = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="normal")
    operator_phone = Column(String(20))
    last_maintenance = Column(DateTime)
    next_maintenance = Column(DateTime)
    location = Column(String(200))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sms_logs = relationship("SMSLog", back_populates="machine")

class Operator(Base):
    """Operator model for personnel management."""
    __tablename__ = "operators"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False, unique=True)
    email = Column(String(100))
    role = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sms_logs = relationship("SMSLog", back_populates="operator")

class SMSLog(Base):
    """SMS log model for message tracking."""
    __tablename__ = "sms_logs"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String(50), ForeignKey("machines.id"))
    operator_id = Column(Integer, ForeignKey("operators.id"))
    message = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    message_id = Column(String(100))
    provider = Column(String(50))
    cost = Column(Float)
    sent_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime)
    error_message = Column(Text)

    # Relationships
    machine = relationship("Machine", back_populates="sms_logs")
    operator = relationship("Operator", back_populates="sms_logs")

class SystemLog(Base):
    """System log model for application events."""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    module = Column(String(100))
    function = Column(String(100))
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String(100))
    ip_address = Column(String(45))

class CacheEntry(Base):
    """Cache entry model for database-backed caching."""
    __tablename__ = "cache_entries"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(500), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PlantComponent(Base):
    """Represents a plant component (crusher, conveyor, screen, etc)."""
    __tablename__ = "plant_components"

    id = Column(Integer, primary_key=True, index=True)
    area = Column(String(100), nullable=False)  # e.g., primary_crusher, conveyor
    name = Column(String(200), nullable=False)
    details = Column(Text)
    last_inspected_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HourEntry(Base):
    """Recorded hour meter entry for a machine."""
    __tablename__ = "hour_entries"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String(50), ForeignKey("machines.id"))
    opening = Column(String(20))
    closing = Column(String(20))
    hour_reading = Column(Float)
    recorded_by = Column(Integer, ForeignKey("operators.id"))
    recorded_at = Column(DateTime, default=datetime.utcnow)


class MaintenanceTask(Base):
    """Scheduled or completed maintenance task for machine or plant component."""
    __tablename__ = "maintenance_tasks"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(300), nullable=False)
    machine_id = Column(String(50), ForeignKey("machines.id"), nullable=True)
    component_id = Column(Integer, ForeignKey("plant_components.id"), nullable=True)
    due_at_hours = Column(Float, nullable=True)  # if hour-based
    scheduled_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="pending")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Part(Base):
    """Spare part or wear item tracking."""
    __tablename__ = "parts"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(100), nullable=True)
    name = Column(String(200), nullable=False)
    last_replaced_at = Column(DateTime, nullable=True)
    expected_life_hours = Column(Float, nullable=True)
    quantity_on_hand = Column(Integer, default=0)
    notes = Column(Text)


class OperatorDocument(Base):
    """Operator documents like license and fitness certificates."""
    __tablename__ = "operator_documents"

    id = Column(Integer, primary_key=True, index=True)
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=False)
    doc_type = Column(String(100))
    expiry_date = Column(DateTime)
    notes = Column(Text)

# Database dependency functions
def get_db() -> Generator[Session, None, None]:
    """Get database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session with automatic cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Redis cache functions
class RedisCache:
    """Redis-based caching with database fallback."""

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Redis connection."""
        if not self._initialized:
            try:
                self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
                self._initialized = True
            except Exception:
                self._redis = None

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._redis:
            return await self._get_db_fallback(key)

        try:
            value = await self._redis.get(key)
            if value:
                import json
                return json.loads(value)
        except Exception:
            return await self._get_db_fallback(key)

        return None

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache."""
        if not self._redis:
            await self._set_db_fallback(key, value, ttl)
            return

        try:
            import json
            await self._redis.setex(key, ttl, json.dumps(value))
        except Exception:
            await self._set_db_fallback(key, value, ttl)

    async def delete(self, key: str):
        """Delete value from cache."""
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception:
                pass

        # Also delete from database fallback
        await self._delete_db_fallback(key)

    async def _get_db_fallback(self, key: str) -> Optional[Any]:
        """Get value from database fallback cache."""
        from sqlalchemy import text
        async for session in get_async_db():
            from datetime import datetime
            result = await session.execute(
                text("SELECT value FROM cache_entries WHERE key = :key AND expires_at > :now"),
                {"key": key, "now": datetime.utcnow()}
            )
            row = result.fetchone()
            if row:
                import json
                return json.loads(row[0])
        return None

    async def _set_db_fallback(self, key: str, value: Any, ttl: int):
        """Set value in database fallback cache."""
        import json
        from datetime import datetime, timedelta
        from sqlalchemy import text
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)

        async for session in get_async_db():
            # Upsert operation
            await session.execute(
                text("""
                INSERT INTO cache_entries (key, value, expires_at, created_at)
                VALUES (:key, :value, :expires_at, :created_at)
                ON CONFLICT (key) DO UPDATE SET
                    value = :value,
                    expires_at = :expires_at
                """),
                {
                    "key": key,
                    "value": json.dumps(value),
                    "expires_at": expires_at,
                    "created_at": datetime.utcnow()
                }
            )
            await session.commit()

    async def _delete_db_fallback(self, key: str):
        """Delete value from database fallback cache."""
        from sqlalchemy import text
        async for session in get_async_db():
            await session.execute(text("DELETE FROM cache_entries WHERE key = :key"), {"key": key})
            await session.commit()

# Global cache instance
cache = RedisCache()

# Database initialization
async def init_db():
    """Initialize database and create tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

def init_db_sync():
    """Synchronous database initialization."""
    Base.metadata.create_all(bind=engine)

# Cleanup function
async def cleanup_db():
    """Cleanup database connections."""
    await async_engine.dispose()
    await cache.close()

# Utility functions
async def get_machine_status_counts() -> Dict[str, int]:
    """Get machine status counts with caching."""
    cache_key = "machine_status_counts"

    # Try cache first
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Query database
    async for session in get_async_db():
        from sqlalchemy import func
        result = await session.execute(
            "SELECT status, COUNT(*) as count FROM machines GROUP BY status"
        )
        rows = result.fetchall()

    counts = {row[0]: row[1] for row in rows}

    # Cache for 5 minutes
    await cache.set(cache_key, counts, 300)

    return counts

async def log_sms_send(
    machine_id: str,
    operator_id: Optional[int],
    message: str,
    status: str,
    message_id: Optional[str] = None,
    provider: str = "unknown",
    cost: Optional[float] = None
):
    """Log SMS send operation."""
    async for session in get_async_db():
        sms_log = SMSLog(
            machine_id=machine_id,
            operator_id=operator_id,
            message=message,
            status=status,
            message_id=message_id,
            provider=provider,
            cost=cost
        )
        session.add(sms_log)
        await session.commit()

async def get_recent_sms_logs(limit: int = 100) -> List[SMSLog]:
    """Get recent SMS logs."""
    async for session in get_async_db():
        result = await session.execute(
            "SELECT * FROM sms_logs ORDER BY sent_at DESC LIMIT :limit",
            {"limit": limit}
        )
        return result.fetchall()

# Migration helpers for Alembic
def get_current_revision():
    """Get current database revision."""
    from alembic.config import Config
    from alembic import command
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext

    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()

def upgrade_database():
    """Upgrade database to latest revision."""
    from alembic.config import Config
    from alembic import command

    config = Config("alembic.ini")
    command.upgrade(config, "head")

# Initialize cache instance
cache = RedisCache()

if __name__ == "__main__":
    # Initialize database when run directly
    import asyncio
    asyncio.run(init_db())
