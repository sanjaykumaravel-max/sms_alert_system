"""
Repository Pattern for Data Access

This module provides repository classes for database operations,
implementing the repository pattern for clean data access.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from datetime import datetime, timedelta

from models import (
    Machine, Operator, SMSLog, SystemLog, CacheEntry,
    SessionLocal, get_db, get_async_db
)

class BaseRepository:
    """Base repository with common database operations."""

    def __init__(self, model_class):
        self.model_class = model_class

    def get_by_id(self, db: Session, id: Any) -> Optional[Any]:
        """Get entity by ID."""
        return db.query(self.model_class).filter(self.model_class.id == id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[Any]:
        """Get all entities with pagination."""
        return db.query(self.model_class).offset(skip).limit(limit).all()

    def create(self, db: Session, **kwargs) -> Any:
        """Create new entity."""
        entity = self.model_class(**kwargs)
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity

    def update(self, db: Session, id: Any, **kwargs) -> Optional[Any]:
        """Update entity by ID."""
        entity = self.get_by_id(db, id)
        if entity:
            for key, value in kwargs.items():
                setattr(entity, key, value)
            db.commit()
            db.refresh(entity)
        return entity

    def delete(self, db: Session, id: Any) -> bool:
        """Delete entity by ID."""
        entity = self.get_by_id(db, id)
        if entity:
            db.delete(entity)
            db.commit()
            return True
        return False

class MachineRepository(BaseRepository):
    """Repository for Machine operations."""

    def __init__(self):
        super().__init__(Machine)

    def get_by_status(self, db: Session, status: str) -> List[Machine]:
        """Get machines by status."""
        return db.query(Machine).filter(Machine.status == status).all()

    def get_by_operator_phone(self, db: Session, phone: str) -> List[Machine]:
        """Get machines by operator phone."""
        return db.query(Machine).filter(Machine.operator_phone == phone).all()

    def get_overdue_maintenance(self, db: Session) -> List[Machine]:
        """Get machines overdue for maintenance."""
        now = datetime.utcnow()
        return db.query(Machine).filter(
            and_(
                Machine.next_maintenance.isnot(None),
                Machine.next_maintenance < now
            )
        ).all()

    def update_status(self, db: Session, machine_id: str, status: str) -> Optional[Machine]:
        """Update machine status."""
        return self.update(db, machine_id, status=status, updated_at=datetime.utcnow())

class OperatorRepository(BaseRepository):
    """Repository for Operator operations."""

    def __init__(self):
        super().__init__(Operator)

    def get_by_phone(self, db: Session, phone: str) -> Optional[Operator]:
        """Get operator by phone number."""
        return db.query(Operator).filter(Operator.phone == phone).first()

    def get_active(self, db: Session) -> List[Operator]:
        """Get all active operators."""
        return db.query(Operator).filter(Operator.is_active == True).all()

    def search_by_name(self, db: Session, name_pattern: str) -> List[Operator]:
        """Search operators by name pattern."""
        return db.query(Operator).filter(
            Operator.name.ilike(f"%{name_pattern}%")
        ).all()

class SMSLogRepository(BaseRepository):
    """Repository for SMS log operations."""

    def __init__(self):
        super().__init__(SMSLog)

    def get_by_machine(self, db: Session, machine_id: str) -> List[SMSLog]:
        """Get SMS logs for a specific machine."""
        return db.query(SMSLog).filter(SMSLog.machine_id == machine_id).all()

    def get_by_operator(self, db: Session, operator_id: int) -> List[SMSLog]:
        """Get SMS logs for a specific operator."""
        return db.query(SMSLog).filter(SMSLog.operator_id == operator_id).all()

    def get_recent_logs(self, db: Session, hours: int = 24) -> List[SMSLog]:
        """Get SMS logs from the last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        return db.query(SMSLog).filter(SMSLog.sent_at >= since).order_by(
            desc(SMSLog.sent_at)
        ).all()

    def get_success_rate(self, db: Session, hours: int = 24) -> Dict[str, Any]:
        """Get SMS success rate statistics."""
        since = datetime.utcnow() - timedelta(hours=hours)
        logs = db.query(SMSLog).filter(SMSLog.sent_at >= since).all()

        total = len(logs)
        successful = len([log for log in logs if log.status == "delivered"])

        return {
            "total_sent": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": (successful / total * 100) if total > 0 else 0
        }

class SystemLogRepository(BaseRepository):
    """Repository for system log operations."""

    def __init__(self):
        super().__init__(SystemLog)

    def get_by_level(self, db: Session, level: str) -> List[SystemLog]:
        """Get logs by level."""
        return db.query(SystemLog).filter(SystemLog.level == level).all()

    def get_recent_logs(self, db: Session, hours: int = 24) -> List[SystemLog]:
        """Get recent system logs."""
        since = datetime.utcnow() - timedelta(hours=hours)
        return db.query(SystemLog).filter(SystemLog.timestamp >= since).order_by(
            desc(SystemLog.timestamp)
        ).all()

    def log_event(self, db: Session, level: str, message: str,
                  module: str = None, function: str = None,
                  user_id: str = None, ip_address: str = None) -> SystemLog:
        """Log a system event."""
        return self.create(
            db,
            level=level,
            message=message,
            module=module,
            function=function,
            user_id=user_id,
            ip_address=ip_address
        )

class CacheRepository(BaseRepository):
    """Repository for cache operations."""

    def __init__(self):
        super().__init__(CacheEntry)

    def get_valid_cache(self, db: Session, key: str) -> Optional[CacheEntry]:
        """Get valid (non-expired) cache entry."""
        now = datetime.utcnow()
        return db.query(CacheEntry).filter(
            and_(
                CacheEntry.key == key,
                CacheEntry.expires_at > now
            )
        ).first()

    def set_cache(self, db: Session, key: str, value: str, ttl_seconds: int) -> CacheEntry:
        """Set cache entry with TTL."""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        # Upsert operation
        existing = db.query(CacheEntry).filter(CacheEntry.key == key).first()
        if existing:
            existing.value = value
            existing.expires_at = expires_at
            existing.created_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            return self.create(
                db,
                key=key,
                value=value,
                expires_at=expires_at
            )

    def cleanup_expired(self, db: Session) -> int:
        """Clean up expired cache entries."""
        now = datetime.utcnow()
        deleted = db.query(CacheEntry).filter(CacheEntry.expires_at <= now).delete()
        db.commit()
        return deleted

# Global repository instances
machine_repo = MachineRepository()
operator_repo = OperatorRepository()
sms_log_repo = SMSLogRepository()
system_log_repo = SystemLogRepository()
cache_repo = CacheRepository()

# Dependency functions for FastAPI
def get_machine_repository() -> MachineRepository:
    """Get machine repository instance."""
    return machine_repo

def get_operator_repository() -> OperatorRepository:
    """Get operator repository instance."""
    return operator_repo

def get_sms_log_repository() -> SMSLogRepository:
    """Get SMS log repository instance."""
    return sms_log_repo

def get_system_log_repository() -> SystemLogRepository:
    """Get system log repository instance."""
    return system_log_repo

def get_cache_repository() -> CacheRepository:
    """Get cache repository instance."""
    return cache_repo