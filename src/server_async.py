"""
Async SMS Alert API Server with Redis Caching and Celery Background Tasks.

This module provides a high-performance, asynchronous API server for the SMS Alert App
with the following optimizations:

- Async/await patterns throughout the application
- Redis caching layer for frequently accessed data
- Background job processing with Celery
- Database connection pooling and query optimization
- CDN integration for static assets
"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import redis.asyncio as redis
import aiohttp
import json
from pathlib import Path
from io import StringIO
import csv
from datetime import timezone

from .app_paths import data_path, resource_path

# Import database components
from .models import SessionLocal, get_db
from sqlalchemy.orm import Session

# Import existing services
try:
    from sms_service import default_sms_service, SMSService
    from config import SMS_ENABLED, SMS_API_KEY, SMS_SENDER_ID
    from auth import authenticate
    from excel_manager import list_machines
    from logger import configure_logging
    from repositories import (
        machine_repo, operator_repo, sms_log_repo, system_log_repo,
        get_machine_repository, get_operator_repository, get_sms_log_repository
    )
    from exceptions import (
        SMSAlertException, ValidationError, NotFoundError, AuthenticationError,
        AuthorizationError, SMSServiceError, DatabaseError, ExternalServiceError,
        handle_sms_alert_exception, validate_phone_number, validate_machine_id, validate_required_field
    )
except ImportError:
    # Fallback for development
    default_sms_service = None
    SMS_ENABLED = True
    SMS_API_KEY = None
    SMS_SENDER_ID = None
    configure_logging = lambda: None
    # Define dummy exception for fallback
    class SMSAlertException(Exception):
        def __init__(self, message, status_code=500, details=None):
            self.message = message
            self.status_code = status_code
            self.details = details or {}
            super().__init__(message)

# Configure logging
configure_logging()
logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour default

# CDN configuration
CDN_ENABLED = os.getenv("CDN_ENABLED", "false").lower() == "true"
CDN_BASE_URL = os.getenv("CDN_BASE_URL", "")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

# Database configuration (for future use)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sms_alert.db")

# Global Redis client
redis_client: Optional[redis.Redis] = None

# Pydantic models
class SMSRequest(BaseModel):
    to: str = Field(..., description="Recipient phone number")
    message: str = Field(..., description="SMS message content")
    priority: Optional[str] = Field("normal", description="Message priority: low, normal, high")

class SMSResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    status: str
    error: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str = "2.0.0"
    services: Dict[str, bool]

class AuthRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    success: bool
    user: Optional[Dict[str, Any]] = None
    token: Optional[str] = None
    error: Optional[str] = None

# Async context manager for Redis
@asynccontextmanager
async def get_redis():
    """Get Redis connection with automatic cleanup."""
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis connection not available")
    try:
        yield redis_client
    except Exception as e:
        logger.error(f"Redis error: {e}")
        raise HTTPException(status_code=500, detail="Cache service error")

# Cache decorators
def cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate cache key from function arguments."""
    key_parts = [prefix]
    key_parts.extend(str(arg) for arg in args)
    key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
    return ":".join(key_parts)

async def get_cached_data(key: str, redis_conn: redis.Redis) -> Optional[Any]:
    """Get data from Redis cache."""
    try:
        data = await redis_conn.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None

async def set_cached_data(key: str, data: Any, ttl: int, redis_conn: redis.Redis):
    """Set data in Redis cache."""
    try:
        await redis_conn.setex(key, ttl, json.dumps(data))
    except Exception as e:
        logger.warning(f"Cache write error: {e}")

# Async SMS service wrapper
class AsyncSMSService:
    """Async wrapper for SMS operations."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._service = default_sms_service or SMSService()

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def send_sms_async(self, to: str, message: str, priority: str = "normal") -> Dict[str, Any]:
        """Send SMS asynchronously with retry logic."""
        if not self._service:
            raise HTTPException(status_code=500, detail="SMS service not configured")

        # Implement priority-based delays
        if priority == "high":
            await asyncio.sleep(0.1)  # Small delay for high priority
        elif priority == "low":
            await asyncio.sleep(1.0)  # Longer delay for low priority

        try:
            # Use thread pool for synchronous SMS service
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._service.send, to, message)

            return {
                "success": result.get("success", False),
                "message_id": result.get("message_id"),
                "status": result.get("status", "unknown"),
                "error": result.get("error")
            }
        except Exception as e:
            logger.error(f"SMS send error: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e)
            }

# Celery task for background SMS processing
from celery import Celery

celery_app = Celery(
    "sms_alert",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
)

@celery_app.task(bind=True)
def send_bulk_sms_task(self, messages: List[Dict[str, Any]]):
    """Background task for sending bulk SMS messages."""
    results = []
    for msg in messages:
        try:
            result = default_sms_service.send(msg["to"], msg["message"])
            results.append(result)
        except Exception as e:
            results.append({"success": False, "error": str(e)})

    return results

# CDN service
class CDNService:
    """CDN service for static asset management."""

    def __init__(self):
        self.enabled = CDN_ENABLED
        self.base_url = CDN_BASE_URL

        if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
            import cloudinary
            cloudinary.config(
                cloud_name=CLOUDINARY_CLOUD_NAME,
                api_key=CLOUDINARY_API_KEY,
                api_secret=CLOUDINARY_API_SECRET
            )
            self.cloudinary_available = True
        else:
            self.cloudinary_available = False

    async def upload_asset(self, file_path: str, public_id: str = None) -> Optional[str]:
        """Upload asset to CDN."""
        if not self.enabled:
            return None

        try:
            if self.cloudinary_available:
                import cloudinary.uploader
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    cloudinary.uploader.upload,
                    file_path,
                    {"public_id": public_id} if public_id else {}
                )
                return result.get("secure_url")
            else:
                # Fallback to direct URL construction
                filename = Path(file_path).name
                return f"{self.base_url}/{filename}"
        except Exception as e:
            logger.error(f"CDN upload error: {e}")
            return None

# FastAPI app with lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global redis_client

    # Startup
    logger.info("Starting SMS Alert API Server...")

    # Initialize Redis
    try:
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        redis_client = None

    # Initialize CDN service
    app.state.cdn = CDNService()

    yield

    # Shutdown
    logger.info("Shutting down SMS Alert API Server...")
    if redis_client:
        await redis_client.close()

app = FastAPI(
    title="SMS Alert API",
    description="High-performance SMS Alert API with async operations and caching",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
_assets_dir = resource_path("assets")
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

# API Routes
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    services_status = {
        "redis": redis_client is not None,
        "sms_service": default_sms_service is not None,
        "cdn": app.state.cdn.enabled
    }

    return HealthResponse(
        status="healthy" if all(services_status.values()) else "degraded",
        timestamp=datetime.utcnow(),
        services=services_status
    )

# Machine CRUD endpoints
@app.get("/api/v1/machines", response_model=List[Dict[str, Any]])
async def get_machines(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all machines with optional filtering."""
    if status:
        machines = machine_repo.get_by_status(db, status)
    else:
        machines = machine_repo.get_all(db, skip, limit)

    return [{"id": m.id, "type": m.type, "status": m.status,
             "operator_phone": m.operator_phone, "location": m.location,
             "last_maintenance": m.last_maintenance.isoformat() if m.last_maintenance else None,
             "next_maintenance": m.next_maintenance.isoformat() if m.next_maintenance else None}
            for m in machines]

@app.get("/api/v1/machines/{machine_id}", response_model=Dict[str, Any])
async def get_machine(machine_id: str, db: Session = Depends(get_db)):
    """Get machine by ID."""
    machine = machine_repo.get_by_id(db, machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    return {"id": machine.id, "type": machine.type, "status": machine.status,
            "operator_phone": machine.operator_phone, "location": machine.location,
            "last_maintenance": machine.last_maintenance.isoformat() if machine.last_maintenance else None,
            "next_maintenance": machine.next_maintenance.isoformat() if machine.next_maintenance else None}

@app.post("/api/v1/machines", response_model=Dict[str, Any])
async def create_machine(machine_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Create new machine."""
    try:
        # Validate required fields
        machine_id = validate_machine_id(machine_data.get("id"))
        machine_type = validate_required_field(machine_data.get("type"), "type")
        status = machine_data.get("status", "normal")

        # Validate status
        valid_statuses = ["normal", "maintenance", "critical", "offline"]
        if status not in valid_statuses:
            raise ValidationError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}", field="status")

        # Check if machine already exists
        existing = machine_repo.get_by_id(db, machine_id)
        if existing:
            raise ValidationError(f"Machine with ID '{machine_id}' already exists", field="id")

        machine = machine_repo.create(db,
            id=machine_id,
            type=machine_type,
            status=status,
            operator_phone=machine_data.get("operator_phone"),
            location=machine_data.get("location"),
            notes=machine_data.get("notes")
        )

        return {"id": machine.id, "type": machine.type, "status": machine.status,
                "operator_phone": machine.operator_phone, "location": machine.location,
                "message": "Machine created successfully"}

    except ValidationError as e:
        raise handle_sms_alert_exception(e)
    except Exception as e:
        logger.error(f"Failed to create machine: {e}")
        raise handle_sms_alert_exception(DatabaseError(f"Failed to create machine: {str(e)}", "create"))


@app.post("/api/v1/sync/actions")
async def receive_sync_actions(request: Request):
    """Receive a batch of offline actions and acknowledge processing.

    This is a simple stub that accepts `{'actions': [...]}` and returns which IDs
    were processed. In a real deployment this would validate payload, authenticate,
    and perform each action (create machine, update task, etc.).
    """
    try:
        body = await request.json()
        actions = body.get('actions', []) or []
        processed = []
        errors = []
        # naive processing: accept all and echo back ids
        for a in actions:
            aid = a.get('id')
            try:
                # Here you would validate and apply the action
                processed.append(aid)
            except Exception as e:
                errors.append({'id': aid, 'error': str(e)})

        return JSONResponse({'processed_ids': processed, 'errors': errors})
    except Exception as e:
        logger.exception('Failed to process sync actions: %s', e)
        return JSONResponse({'processed_ids': [], 'errors': [{'error': str(e)}]}, status_code=500)

@app.put("/api/v1/machines/{machine_id}", response_model=Dict[str, Any])
async def update_machine(machine_id: str, machine_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Update machine."""
    machine = machine_repo.update(db, machine_id, **machine_data)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    return {"id": machine.id, "type": machine.type, "status": machine.status,
            "operator_phone": machine.operator_phone, "location": machine.location}

@app.delete("/api/v1/machines/{machine_id}")
async def delete_machine(machine_id: str, db: Session = Depends(get_db)):
    """Delete machine."""
    success = machine_repo.delete(db, machine_id)
    if not success:
        raise HTTPException(status_code=404, detail="Machine not found")

    return {"message": "Machine deleted successfully"}

# Operator CRUD endpoints
@app.get("/api/v1/operators", response_model=List[Dict[str, Any]])
async def get_operators(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get all operators with optional filtering."""
    if active_only:
        operators = operator_repo.get_active(db)
    else:
        operators = operator_repo.get_all(db, skip, limit)

    return [{"id": o.id, "name": o.name, "phone": o.phone, "email": o.email,
             "role": o.role, "is_active": o.is_active} for o in operators]

@app.get("/api/v1/operators/{operator_id}", response_model=Dict[str, Any])
async def get_operator(operator_id: int, db: Session = Depends(get_db)):
    """Get operator by ID."""
    operator = operator_repo.get_by_id(db, operator_id)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")

    return {"id": operator.id, "name": operator.name, "phone": operator.phone,
            "email": operator.email, "role": operator.role, "is_active": operator.is_active}

@app.post("/api/v1/operators", response_model=Dict[str, Any])
async def create_operator(operator_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Create new operator."""
    try:
        # Validate required fields
        name = validate_required_field(operator_data.get("name"), "name")
        phone = validate_phone_number(operator_data.get("phone"))

        # Check if phone number already exists
        existing = operator_repo.get_by_phone(db, phone)
        if existing:
            raise ValidationError(f"Operator with phone number '{phone}' already exists", field="phone")

        operator = operator_repo.create(db,
            name=name,
            phone=phone,
            email=operator_data.get("email"),
            role=operator_data.get("role", "operator"),
            is_active=operator_data.get("is_active", True)
        )

        return {"id": operator.id, "name": operator.name, "phone": operator.phone,
                "email": operator.email, "role": operator.role, "is_active": operator.is_active,
                "message": "Operator created successfully"}

    except ValidationError as e:
        raise handle_sms_alert_exception(e)
    except Exception as e:
        logger.error(f"Failed to create operator: {e}")
        raise handle_sms_alert_exception(DatabaseError(f"Failed to create operator: {str(e)}", "create"))

@app.put("/api/v1/operators/{operator_id}", response_model=Dict[str, Any])
async def update_operator(operator_id: int, operator_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Update operator."""
    operator = operator_repo.update(db, operator_id, **operator_data)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")

    return {"id": operator.id, "name": operator.name, "phone": operator.phone,
            "email": operator.email, "role": operator.role, "is_active": operator.is_active}

@app.delete("/api/v1/operators/{operator_id}")
async def delete_operator(operator_id: int, db: Session = Depends(get_db)):
    """Delete operator."""
    success = operator_repo.delete(db, operator_id)
    if not success:
        raise HTTPException(status_code=404, detail="Operator not found")

    return {"message": "Operator deleted successfully"}

# SMS Log endpoints
@app.get("/api/v1/sms-logs", response_model=List[Dict[str, Any]])
async def get_sms_logs(
    machine_id: Optional[str] = None,
    operator_id: Optional[int] = None,
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get SMS logs with optional filtering."""
    if machine_id:
        logs = sms_log_repo.get_by_machine(db, machine_id)
    elif operator_id:
        logs = sms_log_repo.get_by_operator(db, operator_id)
    else:
        logs = sms_log_repo.get_recent_logs(db, hours)

    return [{"id": log.id, "machine_id": log.machine_id, "operator_id": log.operator_id,
             "message": log.message, "status": log.status, "message_id": log.message_id,
             "provider": log.provider, "cost": log.cost,
             "sent_at": log.sent_at.isoformat() if log.sent_at else None,
             "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None}
            for log in logs]

@app.get("/api/v1/sms-stats")
async def get_sms_stats(hours: int = 24, db: Session = Depends(get_db)):
    """Get SMS statistics."""
    stats = sms_log_repo.get_success_rate(db, hours)
    return stats


# Audit (DB) endpoints using src.db SMSAudit model when available
@app.get("/api/v1/audit")
async def list_sms_audit(
    to_number: Optional[str] = None,
    provider: Optional[str] = None,
    hours: int = 168,
    page: int = 1,
    per_page: int = 50,
    request: Request = None
):
    try:
        from .db import get_session, SMSAudit
    except Exception:
        raise HTTPException(status_code=500, detail="Audit DB not available")

    # Optional API key protection (same pattern as /sms/send)
    server_key = os.getenv("SERVER_API_KEY")
    if server_key:
        provided = None
        try:
            provided = request.headers.get("X-API-KEY")
        except Exception:
            provided = None
        if not provided:
            provided = (request.query_params.get("api_key") if request is not None else None)
        if provided != server_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    sess = get_session()
    try:
        q = sess.query(SMSAudit)
        if to_number:
            q = q.filter(SMSAudit.to_number == to_number)
        if provider:
            q = q.filter(SMSAudit.provider == provider)
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            q = q.filter(SMSAudit.created_at >= cutoff)

        total = q.count()
        q = q.order_by(SMSAudit.created_at.desc())
        if per_page and per_page > 0:
            q = q.offset((max(page, 1) - 1) * per_page).limit(per_page)
        rows = q.all()
        out = [
            {
                "id": r.id,
                "to": r.to_number,
                "provider": r.provider,
                "message": r.message,
                "success": bool(r.success),
                "status_code": r.status_code,
                "response": r.response,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        return {"total": total, "page": page, "per_page": per_page, "items": out}
    finally:
        sess.close()


@app.get("/api/v1/audit/export")
async def export_sms_audit(provider: Optional[str] = None, hours: int = 168):
    try:
        from .db import get_session, SMSAudit
    except Exception:
        raise HTTPException(status_code=500, detail="Audit DB not available")

    sess = get_session()
    try:
        q = sess.query(SMSAudit)
        if provider:
            q = q.filter(SMSAudit.provider == provider)
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            q = q.filter(SMSAudit.created_at >= cutoff)
        rows = q.order_by(SMSAudit.created_at.desc()).all()

        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "to", "provider", "success", "status_code", "error", "created_at", "message"])
        for r in rows:
            writer.writerow([r.id, r.to_number, r.provider, int(r.success), r.status_code or "", (r.error or ""), (r.created_at.isoformat() if r.created_at else ""), (r.message or "")])
        return JSONResponse(content=buf.getvalue(), media_type="text/csv")
    finally:
        sess.close()


# Tasks & Templates (file-backed) helpers
def _data_dir() -> Path:
    p = data_path()
    p.mkdir(parents=True, exist_ok=True)
    return p

def _tasks_path() -> Path:
    return _data_dir() / "maintenance_tasks.json"

def _templates_path() -> Path:
    return _data_dir() / "task_templates.json"

def _read_json(p: Path) -> List[Dict[str, Any]]:
    try:
        if p.exists():
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f) or []
    except Exception:
        logger.exception('Failed to read %s', p)
    return []

def _write_json(p: Path, data: List[Dict[str, Any]]) -> None:
    try:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        logger.exception('Failed to write %s', p)

def _ensure_task_id(task: Dict[str, Any]) -> str:
    if 'id' in task and task.get('id'):
        return str(task['id'])
    tid = f"task_{int(datetime.utcnow().timestamp())}"
    task['id'] = tid
    return tid


# Tasks endpoints
@app.get("/api/v1/tasks", response_model=List[Dict[str, Any]])
async def list_tasks(status: Optional[str] = None):
    tasks = _read_json(_tasks_path())
    if status:
        tasks = [t for t in tasks if t.get('status') == status]
    return tasks


@app.post("/api/v1/tasks", response_model=Dict[str, Any])
async def create_task(task_data: Dict[str, Any]):
    tasks = _read_json(_tasks_path())
    # assign id and basic defaults
    _ensure_task_id(task_data)
    task_data.setdefault('status', 'pending')
    task_data.setdefault('created_at', datetime.utcnow().isoformat())
    tasks.append(task_data)
    _write_json(_tasks_path(), tasks)
    return task_data


@app.put("/api/v1/tasks/{task_id}")
async def update_task(task_id: str, task_data: Dict[str, Any]):
    tasks = _read_json(_tasks_path())
    for i, t in enumerate(tasks):
        if str(t.get('id')) == str(task_id):
            tasks[i].update(task_data)
            tasks[i]['updated_at'] = datetime.utcnow().isoformat()
            _write_json(_tasks_path(), tasks)
            return tasks[i]
    raise HTTPException(status_code=404, detail='Task not found')


@app.delete("/api/v1/tasks/{task_id}")
async def delete_task(task_id: str):
    tasks = _read_json(_tasks_path())
    for i, t in enumerate(tasks):
        if str(t.get('id')) == str(task_id):
            tasks.pop(i)
            _write_json(_tasks_path(), tasks)
            return {"message": "Task deleted"}
    raise HTTPException(status_code=404, detail='Task not found')


# DB-backed scheduler endpoints (persist tasks using DB.Task)
@app.get("/api/v1/scheduler/tasks", response_model=List[Dict[str, Any]])
async def db_list_tasks(status: Optional[str] = None):
    try:
        from .db import get_session, Task
    except Exception:
        raise HTTPException(status_code=500, detail="DB not available")
    sess = get_session()
    try:
        q = sess.query(Task)
        if status:
            q = q.filter(Task.status == status)
        rows = q.order_by(Task.due_at.asc()).all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "subject": r.subject,
                "machine_id": r.machine_id,
                "due_at": r.due_at.isoformat() if r.due_at else None,
                "status": r.status,
                "metadata": r.metadata_json if getattr(r, 'metadata_json', None) is not None else None
            })
        return out
    finally:
        sess.close()


@app.post("/api/v1/scheduler/tasks", response_model=Dict[str, Any])
async def db_create_task(task_data: Dict[str, Any]):
    try:
        from .db import get_session, Task
    except Exception:
        raise HTTPException(status_code=500, detail="DB not available")

    subject = task_data.get('subject') or 'Scheduled Task'
    machine_id = task_data.get('machine_id')
    due_txt = task_data.get('due_at')
    if not due_txt:
        raise HTTPException(status_code=400, detail='due_at is required (ISO datetime)')
    try:
        due = datetime.fromisoformat(due_txt)
        if due.tzinfo is None:
            # assume UTC when no tz provided
            due = due.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid due_at format; expected ISO datetime')

    sess = get_session()
    try:
        t = Task(subject=subject, machine_id=machine_id, due_at=due, status=task_data.get('status', 'pending'), metadata_json=task_data.get('metadata'))
        sess.add(t)
        sess.commit()
        sess.refresh(t)
        return {"id": t.id, "subject": t.subject, "machine_id": t.machine_id, "due_at": t.due_at.isoformat(), "status": t.status}
    finally:
        sess.close()


@app.put("/api/v1/scheduler/tasks/{task_id}")
async def db_update_task(task_id: int, task_data: Dict[str, Any]):
    try:
        from .db import get_session, Task
    except Exception:
        raise HTTPException(status_code=500, detail="DB not available")
    sess = get_session()
    try:
        t = sess.query(Task).get(task_id)
        if not t:
            raise HTTPException(status_code=404, detail='Task not found')
        for k, v in task_data.items():
            if k == 'due_at':
                try:
                    dv = datetime.fromisoformat(v)
                    if dv.tzinfo is None:
                        dv = dv.replace(tzinfo=timezone.utc)
                    setattr(t, 'due_at', dv)
                except Exception:
                    raise HTTPException(status_code=400, detail='Invalid due_at format')
            elif k == 'metadata':
                setattr(t, 'metadata_json', v)
            else:
                setattr(t, k, v)
        sess.commit()
        return {"id": t.id, "status": t.status}
    finally:
        sess.close()


# Templates endpoints
@app.get("/api/v1/templates", response_model=List[Dict[str, Any]])
async def list_templates():
    return _read_json(_templates_path())


@app.post("/api/v1/templates", response_model=Dict[str, Any])
async def create_template(template_data: Dict[str, Any]):
    templates = _read_json(_templates_path())
    if not template_data.get('id'):
        template_data['id'] = f"tpl_{int(datetime.utcnow().timestamp())}"
    templates.append(template_data)
    _write_json(_templates_path(), templates)
    return template_data


@app.delete("/api/v1/templates/{template_id}")
async def delete_template(template_id: str):
    templates = _read_json(_templates_path())
    for i, t in enumerate(templates):
        if str(t.get('id')) == str(template_id):
            templates.pop(i)
            _write_json(_templates_path(), templates)
            return {"message": "Template deleted"}
    raise HTTPException(status_code=404, detail='Template not found')


# Trigger generation from templates (server-side)
@app.post("/api/v1/generate-from-templates")
async def api_generate_from_templates(horizon_days: int = 30, dedup_minutes: int = 60):
    templates = _read_json(_templates_path())
    tasks = _read_json(_tasks_path())
    now = datetime.utcnow()
    horizon = now + timedelta(days=horizon_days)
    new = []
    for tpl in templates:
        try:
            ttype = tpl.get('type')
            start_txt = tpl.get('start')
            start = now
            if start_txt:
                try:
                    start = datetime.fromisoformat(start_txt)
                except Exception:
                    start = now

            occ = []
            if ttype == 'daily':
                every = int(tpl.get('every', 1))
                cur = start.date()
                while datetime.combine(cur, datetime.min.time()) <= horizon:
                    occ_dt = datetime.combine(cur, datetime.min.time())
                    if occ_dt >= start:
                        occ.append(occ_dt)
                    cur = cur + timedelta(days=every)
            elif ttype == 'hourly':
                ival = float(tpl.get('interval_hours', 24))
                cur = start
                while cur <= horizon:
                    occ.append(cur)
                    cur = cur + timedelta(hours=ival)
            else:
                # skip unsupported types for now
                continue

            for dt in occ:
                subj = tpl.get('subject') or tpl.get('name') or 'Scheduled Task'
                dup = False
                for ex in tasks + new:
                    try:
                        if ex.get('subject') == subj:
                            ex_dt = ex.get('scheduled_at')
                            if not ex_dt:
                                continue
                            try:
                                ex_d = datetime.fromisoformat(ex_dt)
                                if abs((ex_d - dt).total_seconds()) <= dedup_minutes * 60:
                                    dup = True
                                    break
                            except Exception:
                                continue
                    except Exception:
                        continue
                if dup:
                    continue
                task = {'id': f"task_{int(datetime.utcnow().timestamp())}", 'subject': subj, 'scheduled_at': dt.isoformat(), 'status': 'pending', 'template': tpl.get('id')}
                new.append(task)
        except Exception:
            continue

    if new:
        tasks.extend(new)
        _write_json(_tasks_path(), tasks)
    return {"created": len(new)}

# System endpoints
@app.get("/api/v1/system/logs", response_model=List[Dict[str, Any]])
async def get_system_logs(hours: int = 24, db: Session = Depends(get_db)):
    """Get system logs."""
    logs = system_log_repo.get_recent_logs(db, hours)
    return [{"id": log.id, "level": log.level, "message": log.message,
             "module": log.module, "function": log.function,
             "timestamp": log.timestamp.isoformat(),
             "user_id": log.user_id, "ip_address": log.ip_address}
            for log in logs]

@app.get("/api/v1/audit/export")
async def export_sms_audit(provider: Optional[str] = None, hours: int = 168, request: Request = None):
    try:
        from .db import get_session, SMSAudit
    except Exception:
        raise HTTPException(status_code=500, detail="Audit DB not available")

    # API key protection
    server_key = os.getenv("SERVER_API_KEY")
    if server_key:
        provided = None
        try:
            provided = request.headers.get("X-API-KEY")
        except Exception:
            provided = None
        if not provided:
            provided = (request.query_params.get("api_key") if request is not None else None)
        if provided != server_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    sess = get_session()
    try:
        q = sess.query(SMSAudit)
        if provider:
            q = q.filter(SMSAudit.provider == provider)
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            q = q.filter(SMSAudit.created_at >= cutoff)
        q = q.order_by(SMSAudit.created_at.desc())

        def row_iter():
            # yield CSV header
            yield ",".join(["id", "to", "provider", "success", "status_code", "error", "created_at", "message"]) + "\n"
            for r in q:
                cols = [str(r.id), (r.to_number or ''), (r.provider or ''), str(int(r.success)), str(r.status_code or ''), (r.error or ''), (r.created_at.isoformat() if r.created_at else ''), (r.message or '').replace('\n',' ')]
                yield ",".join(cols) + "\n"

        from fastapi.responses import StreamingResponse
        return StreamingResponse(row_iter(), media_type="text/csv")
    finally:
        sess.close()
        provided = request.headers.get("X-API-KEY") or request.query_params.get("api_key")
        if provided != server_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    async with AsyncSMSService() as sms_service:
        result = await sms_service.send_sms_async(
            sms_request.to,
            sms_request.message,
            sms_request.priority
        )

    if result["success"]:
        return SMSResponse(
            success=True,
            message_id=result.get("message_id"),
            status=result.get("status", "sent")
        )
    else:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "SMS send failed")
        )

@app.post("/sms/send-bulk")
async def send_bulk_sms(
    messages: List[SMSRequest],
    background_tasks: BackgroundTasks,
    request: Request
):
    """Send bulk SMS messages using background tasks."""
    # API key authentication
    server_key = os.getenv("SERVER_API_KEY")
    if server_key:
        provided = request.headers.get("X-API-KEY") or request.query_params.get("api_key")
        if provided != server_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    # Add to background queue
    background_tasks.add_task(send_bulk_sms_task.delay, [msg.dict() for msg in messages])

    return {"message": "Bulk SMS job queued", "count": len(messages)}

@app.get("/machines")
async def get_machines_legacy(redis_conn: redis.Redis = Depends(get_redis)):
    """Legacy machines endpoint with caching."""
    cache_key_str = "machines:list"

    # Try cache first
    cached_data = await get_cached_data(cache_key_str, redis_conn)
    if cached_data:
        return cached_data

    # Fetch from database using repository
    db = SessionLocal()
    try:
        machines = machine_repo.get_all(db)
        machine_data = {
            "machines": [{"id": m.id, "type": m.type, "status": m.status,
                         "operator_phone": m.operator_phone, "location": m.location}
                        for m in machines],
            "count": len(machines)
        }

        # Cache for 5 minutes
        await set_cached_data(cache_key_str, machine_data, 300, redis_conn)

        return machine_data
    finally:
        db.close()

@app.post("/cdn/upload")
async def upload_to_cdn(file_path: str, public_id: Optional[str] = None):
    """Upload file to CDN."""
    if not app.state.cdn.enabled:
        raise HTTPException(status_code=503, detail="CDN service not available")

    url = await app.state.cdn.upload_asset(file_path, public_id)
    if url:
        return {"url": url, "success": True}
    else:
        raise HTTPException(status_code=500, detail="CDN upload failed")

# Error handlers
@app.exception_handler(SMSAlertException)
async def sms_alert_exception_handler(request: Request, exc: SMSAlertException):
    """Handle custom SMSAlert exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server_async:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level="info"
    )
