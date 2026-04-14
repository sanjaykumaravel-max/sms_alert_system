"""Lightweight DB layer using SQLAlchemy for local persistence."""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Table, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from pathlib import Path
import logging
from datetime import datetime, timezone
import json
from sqlalchemy.sql import func
try:
    import pytz  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    pytz = None

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path

logger = logging.getLogger(__name__)

BASE_DIR = data_path().parent
DB_PATH = os.getenv('SMS_APP_DB', str(data_path('app.db')))
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def _ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime without hard dependency on pytz."""
    if dt.tzinfo is not None:
        return dt
    if pytz is not None:
        return pytz.UTC.localize(dt)
    return dt.replace(tzinfo=timezone.utc)


class Machine(Base):
    __tablename__ = 'machines'
    id = Column(Integer, primary_key=True)
    external_id = Column(String(128), index=True)
    name = Column(String(255))
    data = Column(JSON)


class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    subject = Column(String(255))
    machine_id = Column(String(128), index=True)
    # Use timezone-aware datetimes
    due_at = Column(DateTime(timezone=True))
    status = Column(String(50), default='pending')
    metadata_json = Column(JSON)


class Operator(Base):
    __tablename__ = 'operators'
    id = Column(Integer, primary_key=True)
    external_id = Column(String(128), index=True)
    name = Column(String(255))
    phone = Column(String(64))
    data = Column(JSON)


class SMSAudit(Base):
    __tablename__ = 'sms_audit'
    id = Column(Integer, primary_key=True)
    to_number = Column(String(64), index=True)
    provider = Column(String(64))
    message = Column(Text)
    success = Column(Integer)  # 1 or 0
    status_code = Column(Integer, nullable=True)
    response = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Role-based access models
user_roles = Table(
    'user_roles', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE')),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'))
)


class Role(Base):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, index=True)
    description = Column(String(255), nullable=True)


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(128), unique=True, index=True)
    display_name = Column(String(255))
    email = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True)


# Offline queue for operations when app is offline
class OfflineAction(Base):
    __tablename__ = 'offline_actions'
    id = Column(Integer, primary_key=True)
    action_type = Column(String(128), index=True)
    payload = Column(JSON)
    attempts = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


def init_db():
    """Create tables if they don't exist."""
    try:
        Path(DB_PATH).resolve().parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)
        logger.info('Initialized DB at %s', DB_PATH)
    except Exception:
        logger.exception('Failed to initialize DB')


def get_session():
    return SessionLocal()


def migrate_json_to_db(json_path: str, model: str = 'machines'):
    import json as _json
    from dateutil.parser import parse as _parse_dt
    try:
        p = Path(json_path)
        if not p.exists():
            return 0
        with open(p, 'r', encoding='utf-8') as f:
            data = _json.load(f) or []
        sess = get_session()
        count = 0
        if model == 'machines':
            for item in data:
                m = Machine(external_id=str(item.get('id') or item.get('name')), name=item.get('name') or '', data=item)
                sess.add(m)
                count += 1
        if model == 'tasks' or model == 'maintenance_tasks':
            for item in data:
                try:
                    due = item.get('due_at') or item.get('due_date') or item.get('next_maintenance')
                    due_dt = None
                    if due:
                        try:
                            due_dt = _parse_dt(due)
                            if due_dt.tzinfo is None:
                                due_dt = _ensure_utc(due_dt)
                        except Exception:
                            due_dt = None
                    t = Task(
                        subject=item.get('subject') or item.get('title') or item.get('name') or '',
                        machine_id=str(item.get('machine_id') or item.get('machine') or item.get('machine_external_id') or ''),
                        due_at=due_dt,
                        status=item.get('status') or 'pending',
                        metadata_json=item
                    )
                    sess.add(t)
                    count += 1
                except Exception:
                    continue
        if model == 'operators':
            for item in data:
                try:
                    op = Operator(external_id=str(item.get('id') or item.get('phone') or item.get('name') or ''),
                                  name=item.get('name') or '', phone=item.get('phone') or item.get('phone_number') or '', data=item)
                    sess.add(op)
                    count += 1
                except Exception:
                    continue
        if model == 'sms_audit':
            for item in data:
                try:
                    sa = SMSAudit(
                        to_number=item.get('to_number'),
                        provider=item.get('provider'),
                        message=item.get('message'),
                        success=1 if item.get('success') else 0,
                        status_code=item.get('status_code'),
                        response=item.get('response'),
                        error=item.get('error')
                    )
                    sess.add(sa)
                    count += 1
                except Exception:
                    continue
        sess.commit()
        sess.close()
        return count
    except Exception:
        logger.exception('Migration failed')
        return 0
