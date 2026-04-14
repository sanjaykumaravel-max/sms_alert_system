"""
API Client for SMS Alert App

This module provides a client for interacting with the SMS Alert API,
allowing the UI to communicate with the backend services.
"""

import asyncio
import os
import aiohttp
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path


def _operators_path():
    return data_path("operators.json")


def _load_operator_store() -> List[Dict[str, Any]]:
    try:
        path = _operators_path()
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8")) or []
        if not isinstance(payload, list):
            return []
        return [dict(item) for item in payload if isinstance(item, dict)]
    except Exception:
        return []


def _save_operator_store(rows: List[Dict[str, Any]]) -> None:
    path = _operators_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _normalize_operator_record(record: Dict[str, Any], *, fallback_id: int) -> Dict[str, Any]:
    normalized = dict(record or {})
    normalized["id"] = int(normalized.get("id") or fallback_id)
    normalized["name"] = str(normalized.get("name") or "").strip()
    normalized["phone"] = str(normalized.get("phone") or "").strip()
    normalized["email"] = str(normalized.get("email") or "").strip()
    normalized["active"] = bool(normalized.get("active", True))
    normalized["last_updated"] = datetime.now().isoformat(timespec="seconds")
    return normalized

class APIClient:
    """Client for SMS Alert API operations."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key: Optional[str] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def set_api_key(self, api_key: str):
        """Set API key for authenticated requests."""
        self.api_key = api_key

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to API."""
        # Create a short-lived session if client not initialized to avoid leaking sessions
        url = f"{self.base_url}{endpoint}"

        # Add API key if available
        headers = kwargs.get('headers', {})
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        kwargs['headers'] = headers

        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = aiohttp.ClientTimeout(total=10)  # 10 second timeout

        session = self.session
        close_after = False
        if not session:
            session = aiohttp.ClientSession()
            close_after = True

        try:
            async with session.request(method, url, **kwargs) as response:
                if response.status >= 400:
                    try:
                        error_data = await response.json()
                    except Exception:
                        error_data = {'message': 'API request failed'}
                    raise APIError(response.status, error_data.get('message', 'API request failed'), error_data)

                return await response.json()
        finally:
            if close_after:
                try:
                    await session.close()
                except Exception:
                    pass

    # Machine operations
    async def get_machines(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all machines.

        Read from the shared local machine store so the UI, reports, and alerts
        all use the same user-managed machine list.
        """
        machines: List[Dict[str, Any]] = []
        try:
            try:
                from .machine_store import load_machines
            except Exception:
                from machine_store import load_machines

            raw = load_machines() or []
            for it in raw:
                rec: Dict[str, Any] = dict(it)
                if 'id' not in rec and 'machine_id' in rec:
                    rec['id'] = rec.get('machine_id')
                if 'machine_id' not in rec:
                    rec['machine_id'] = rec.get('id')
                if not rec.get('name'):
                    rec['name'] = rec.get('model') or rec.get('type') or str(rec.get('id'))
                if 'operator' not in rec and 'operator_phone' in rec:
                    rec['operator'] = rec.get('operator_phone')
                machines.append(rec)
        except Exception:
            machines = []

        if status:
            return [m for m in machines if (m.get('status') or '') == status]
        return machines

    async def get_machine(self, machine_id: str) -> Dict[str, Any]:
        """Get machine by ID."""
        return await self._make_request('GET', f'/api/v1/machines/{machine_id}')

    async def create_machine(self, machine_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new machine."""
        return await self._make_request('POST', '/api/v1/machines', json=machine_data)

    async def update_machine(self, machine_id: str, machine_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update machine."""
        return await self._make_request('PUT', f'/api/v1/machines/{machine_id}', json=machine_data)

    async def delete_machine(self, machine_id: str) -> Dict[str, Any]:
        """Delete machine."""
        return await self._make_request('DELETE', f'/api/v1/machines/{machine_id}')

    # Operator operations
    async def get_operators(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """Get operators from the shared local operator store."""
        operators = _load_operator_store()
        if active_only:
            return [op for op in operators if bool(op.get("active", True))]
        return operators

    async def get_operator(self, operator_id: int) -> Dict[str, Any]:
        """Get operator by ID from the local operator store."""
        for operator in _load_operator_store():
            try:
                if int(operator.get("id") or 0) == int(operator_id):
                    return operator
            except Exception:
                continue
        raise APIError(404, "Operator not found")

    async def create_operator(self, operator_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new operator in the shared local operator store."""
        operators = _load_operator_store()
        next_id = max([int(op.get("id") or 0) for op in operators] + [0]) + 1
        created = _normalize_operator_record(operator_data, fallback_id=next_id)
        operators.append(created)
        _save_operator_store(operators)
        return created

    async def update_operator(self, operator_id: int, operator_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an operator in the shared local operator store."""
        operators = _load_operator_store()
        updated = None
        for idx, operator in enumerate(operators):
            try:
                if int(operator.get("id") or 0) != int(operator_id):
                    continue
            except Exception:
                continue
            merged = dict(operator)
            merged.update(operator_data or {})
            updated = _normalize_operator_record(merged, fallback_id=int(operator_id))
            operators[idx] = updated
            break
        if updated is None:
            raise APIError(404, "Operator not found")
        _save_operator_store(operators)
        return updated

    async def delete_operator(self, operator_id: int) -> Dict[str, Any]:
        """Delete an operator from the shared local operator store."""
        operators = _load_operator_store()
        kept = []
        deleted = False
        for operator in operators:
            try:
                if int(operator.get("id") or 0) == int(operator_id):
                    deleted = True
                    continue
            except Exception:
                pass
            kept.append(operator)
        if not deleted:
            raise APIError(404, "Operator not found")
        _save_operator_store(kept)
        return {"success": True, "deleted": True, "id": int(operator_id)}

    # SMS operations
    async def send_sms(self, to: str, message: str, priority: str = "normal") -> Dict[str, Any]:
        """Send SMS message."""
        data = {"to": to, "message": message, "priority": priority}
        return await self._make_request('POST', '/sms/send', json=data)

    async def get_sms_logs(self, machine_id: Optional[str] = None,
                          operator_id: Optional[int] = None, hours: int = 24) -> List[Dict[str, Any]]:
        """Get SMS logs."""
        params = {'hours': hours}
        if machine_id:
            params['machine_id'] = machine_id
        if operator_id:
            params['operator_id'] = operator_id

        return await self._make_request('GET', '/api/v1/sms-logs', params=params)

    # Plant components operations
    async def get_plant_components(self) -> Dict[str, Any]:
        """Retrieve plant components mapping from the API.

        Expected shape: {"primary_crusher": [{"name":"...","details":"..."}], ...}
        """
        return await self._make_request('GET', '/api/plant_components')

    async def save_plant_components(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save plant components mapping to the API (replace).
        """
        return await self._make_request('PUT', '/api/plant_components', json=data)

    async def get_sms_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get SMS statistics."""
        params = {'hours': hours}
        return await self._make_request('GET', '/api/v1/sms-stats', params=params)

    # Hour entries operations
    async def get_hour_entries(self) -> List[Dict[str, Any]]:
        """Retrieve hour entries list from API."""
        return await self._make_request('GET', '/api/hour_entries')

    async def create_hour_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Create a single hour entry on the API."""
        return await self._make_request('POST', '/api/hour_entries', json=entry)

    # System operations
    async def get_system_logs(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get system logs."""
        params = {'hours': hours}
        return await self._make_request('GET', '/api/v1/system/logs', params=params)

    async def create_system_log(self, level: str, message: str, **kwargs) -> Dict[str, Any]:
        """Create system log entry."""
        data = {"level": level, "message": message, **kwargs}
        return await self._make_request('POST', '/api/v1/system/logs', json=data)

    # Health check
    async def health_check(self) -> Dict[str, Any]:
        """Check API health."""
        return await self._make_request('GET', '/health')

class APIError(Exception):
    """Exception raised for API errors."""

    def __init__(self, status_code: int, message: str, details: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"API Error {status_code}: {message}")

# Global API client instance
# Allow overriding the API base URL from the environment (useful for local testing on a different port)
_base = os.environ.get('API_BASE_URL') or os.environ.get('SERVER_BASE_URL') or "http://localhost:8000"
api_client = APIClient(_base)

# If server uses a shared API key, pick it up from the environment so
# synchronous wrappers that construct temporary clients will forward it.
try:
    env_key = os.environ.get('SERVER_API_KEY')
    if env_key:
        api_client.set_api_key(env_key)
except Exception:
    pass

# Synchronous wrapper functions for UI compatibility
def get_api_client() -> APIClient:
    """Get API client instance."""
    return api_client

async def init_api_client(base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
    """Initialize API client."""
    global api_client
    api_client = APIClient(base_url)
    if api_key:
        api_client.set_api_key(api_key)

# --------------------------------------------------------------------------
# Background Event Loop for Synchronous UI Wrappers
# --------------------------------------------------------------------------
import threading
import concurrent.futures

_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_thread: Optional[threading.Thread] = None

def _start_bg_loop():
    """Start the background event loop if it's not already running."""
    global _bg_loop, _bg_thread
    if _bg_loop is None or not _bg_loop.is_running():
        _bg_loop = asyncio.new_event_loop()
        def run_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        
        _bg_thread = threading.Thread(target=run_loop, args=(_bg_loop,), daemon=True, name="APIClientBgLoop")
        _bg_thread.start()

def _run_in_background_loop(coro, timeout=5.0, default_return=None):
    """Run a coroutine in the background event loop safely."""
    _start_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _bg_loop)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        future.cancel()
        return default_return
    except Exception:
        return default_return

# Synchronous helper functions for UI
def sync_get_machines(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for get_machines."""
    async def _get():
        async with APIClient(api_client.base_url) as client:
            if api_client.api_key:
                client.set_api_key(api_client.api_key)
            return await client.get_machines(status)
    return _run_in_background_loop(_get(), default_return=[])

def sync_get_operators(active_only: bool = False) -> List[Dict[str, Any]]:
    """Synchronous wrapper for get_operators."""
    async def _get():
        async with APIClient(api_client.base_url) as client:
            if api_client.api_key:
                client.set_api_key(api_client.api_key)
            return await client.get_operators(active_only)
    return _run_in_background_loop(_get(), default_return=[])

def sync_create_machine(machine_data: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper for create_machine."""
    async def _create():
        # Share the global api_client instead of recreating for creates to reuse session
        if api_client.session is None:
            await api_client.__aenter__()
        return await api_client.create_machine(machine_data)
    return _run_in_background_loop(_create(), default_return={})

def sync_create_operator(operator_data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for create_operator."""
    async def _create():
        if api_client.session is None:
            await api_client.__aenter__()
        payload = dict(operator_data or {})
        payload.update(kwargs)
        return await api_client.create_operator(payload)
    return _run_in_background_loop(_create(), default_return={})

def sync_get_plant_components() -> Dict[str, Any]:
    """Synchronous wrapper for getting plant components from API."""
    async def _get():
        async with APIClient(api_client.base_url) as client:
            if api_client.api_key:
                client.set_api_key(api_client.api_key)
            return await client.get_plant_components()
    return _run_in_background_loop(_get(), default_return={})

def sync_save_plant_components(data: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper for saving plant components to API."""
    async def _save():
        async with APIClient(api_client.base_url) as client:
            if api_client.api_key:
                client.set_api_key(api_client.api_key)
            return await client.save_plant_components(data)
    return _run_in_background_loop(_save(), default_return={})

def sync_get_hour_entries() -> List[Dict[str, Any]]:
    """Synchronous wrapper for getting hour entries from API."""
    async def _get():
        async with APIClient(api_client.base_url) as client:
            if api_client.api_key:
                client.set_api_key(api_client.api_key)
            return await client.get_hour_entries()
    return _run_in_background_loop(_get(), default_return=[])

def sync_create_hour_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper for creating an hour entry on the API."""
    async def _create():
        async with APIClient(api_client.base_url) as client:
            if api_client.api_key:
                client.set_api_key(api_client.api_key)
            return await client.create_hour_entry(entry)
    return _run_in_background_loop(_create(), default_return={})
