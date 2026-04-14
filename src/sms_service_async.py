"""
Async SMS Service with Redis Caching and Background Processing.

This module provides an asynchronous SMS service with the following optimizations:

- Async/await patterns for all operations
- Redis caching for frequently accessed data
- Background job processing with Celery
- Connection pooling and retry logic
- Performance monitoring and metrics
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import aiohttp
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    from config import SMS_ENABLED, SMS_API_KEY, SMS_SENDER_ID
except ImportError:
    SMS_ENABLED = True
    SMS_API_KEY = None
    SMS_SENDER_ID = None

logger = logging.getLogger(__name__)

# Module-level flag to avoid noisy repeated Redis warnings
_redis_warned = False

# Configuration
REDIS_URL = "redis://localhost:6379"
CACHE_TTL = 3600  # 1 hour
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT = 30

@dataclass
class SMSResult:
    """SMS send result."""
    success: bool
    message_id: Optional[str] = None
    status: str = "unknown"
    error: Optional[str] = None
    provider: str = "unknown"
    cost: Optional[float] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

class AsyncSMSService:
    """
    Asynchronous SMS service with caching and background processing.

    Features:
    - Async HTTP requests with connection pooling
    - Redis caching for rate limits and responses
    - Automatic retry with exponential backoff
    - Multiple provider support
    - Background job queuing
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        sender_id: Optional[str] = None,
        provider: str = "generic",
        provider_url: Optional[str] = None,
        redis_url: str = REDIS_URL
    ):
        self.api_key = api_key or SMS_API_KEY
        self.sender_id = sender_id or SMS_SENDER_ID
        self.provider = provider
        self.provider_url = provider_url

        # Async components
        self._session: Optional[aiohttp.ClientSession] = None
        self._redis: Optional[redis.Redis] = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        # Initialize Redis
        self.redis_url = redis_url
        self._redis_initialized = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    async def initialize(self):
        """Initialize async resources."""
        # Create HTTP session with connection pooling
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
        )

        # Initialize Redis
        try:
            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self._redis_initialized = True
            logger.info("Redis connection established for SMS service")
        except Exception as e:
            # Suppress noisy repeated warnings; log once as info and continue without Redis
            global _redis_warned
            if not _redis_warned:
                logger.info("Redis not available for SMS service; continuing without cache")
                _redis_warned = True
            self._redis = None

    async def cleanup(self):
        """Cleanup async resources."""
        if self._session:
            await self._session.close()

        if self._redis:
            await self._redis.close()

    async def _get_cache_key(self, action: str, *args) -> str:
        """Generate cache key."""
        key_parts = ["sms", action]
        key_parts.extend(str(arg) for arg in args)
        return ":".join(key_parts)

    async def _get_cached_result(self, key: str) -> Optional[SMSResult]:
        """Get cached SMS result."""
        if not self._redis:
            return None

        try:
            data = await self._redis.get(key)
            if data:
                return SMSResult(**json.loads(data))
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

        return None

    async def _cache_result(self, key: str, result: SMSResult, ttl: int = CACHE_TTL):
        """Cache SMS result."""
        if not self._redis:
            return

        try:
            await self._redis.setex(key, ttl, json.dumps({
                "success": result.success,
                "message_id": result.message_id,
                "status": result.status,
                "error": result.error,
                "provider": result.provider,
                "cost": result.cost,
                "timestamp": result.timestamp.isoformat()
            }))
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def _send_request(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send HTTP request with retry logic."""
        async with self._semaphore:  # Rate limiting
            if not self._session:
                raise RuntimeError("HTTP session not initialized")

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with self._session.post(url, json=data, headers=headers) as response:
                response.raise_for_status()
                return await response.json()

    async def send_sms_async(
        self,
        to: str,
        message: str,
        priority: str = "normal"
    ) -> SMSResult:
        """
        Send SMS asynchronously with caching and retry logic.

        Args:
            to: Recipient phone number
            message: SMS message content
            priority: Message priority (low, normal, high)

        Returns:
            SMSResult object with send status
        """
        if not self.api_key:
            return SMSResult(
                success=False,
                error="SMS API key not configured",
                provider=self.provider
            )

        # Check cache for recent identical messages (to prevent duplicates)
        cache_key = await self._get_cache_key("send", to, hash(message))
        cached_result = await self._get_cached_result(cache_key)
        if cached_result and (datetime.utcnow() - cached_result.timestamp).seconds < 60:
            logger.info(f"Using cached SMS result for {to}")
            return cached_result

        try:
            # Prepare request data based on provider
            if self.provider == "twilio":
                url = f"https://api.twilio.com/2010-04-01/Accounts/{self.api_key}/Messages.json"
                data = {
                    "To": to,
                    "From": self.sender_id,
                    "Body": message
                }
            elif self.provider == "fast2sms":
                url = "https://www.fast2sms.com/dev/bulkV2"
                data = {
                    "route": "v3",
                    "sender_id": self.sender_id,
                    "message": message,
                    "language": "english",
                    "flash": 0,
                    "numbers": to
                }
            else:
                # Generic provider
                url = self.provider_url or "https://api.example.com/sms"
                data = {
                    "to": to,
                    "message": message,
                    "sender": self.sender_id
                }

            # Send request with retry
            response = await self._send_request(url, data)

            # Parse response based on provider
            if self.provider == "twilio":
                success = response.get("status") == "queued"
                message_id = response.get("sid")
                status = response.get("status", "unknown")
            elif self.provider == "fast2sms":
                success = response.get("return", False)
                message_id = str(response.get("request_id", ""))
                status = "sent" if success else "failed"
            else:
                success = response.get("success", False)
                message_id = response.get("message_id")
                status = response.get("status", "unknown")

            result = SMSResult(
                success=success,
                message_id=message_id,
                status=status,
                provider=self.provider,
                error=response.get("error") if not success else None
            )

            # Cache successful results for 5 minutes
            if success:
                await self._cache_result(cache_key, result, 300)

            return result

        except Exception as e:
            logger.error(f"SMS send error: {e}")
            result = SMSResult(
                success=False,
                error=str(e),
                provider=self.provider
            )

            # Cache failed results for 1 minute to prevent rapid retries
            await self._cache_result(cache_key, result, 60)

            return result

    async def send_bulk_sms_async(
        self,
        messages: List[Dict[str, str]],
        priority: str = "normal"
    ) -> List[SMSResult]:
        """
        Send bulk SMS messages asynchronously.

        Args:
            messages: List of dicts with 'to' and 'message' keys
            priority: Message priority

        Returns:
            List of SMSResult objects
        """
        tasks = []
        for msg in messages:
            task = self.send_sms_async(
                msg["to"],
                msg["message"],
                priority
            )
            tasks.append(task)

        # Execute with concurrency control
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions in results
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append(SMSResult(
                    success=False,
                    error=str(result),
                    provider=self.provider
                ))
            else:
                processed_results.append(result)

        return processed_results

    async def get_sms_status(self, message_id: str) -> Optional[SMSResult]:
        """Get SMS delivery status."""
        cache_key = await self._get_cache_key("status", message_id)
        cached_result = await self._get_cached_result(cache_key)

        if cached_result:
            return cached_result

        # Implement provider-specific status checking here
        # For now, return cached result or None
        return cached_result

    async def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        if not self._redis:
            return {"error": "Redis not available"}

        try:
            # Get rate limit counters from Redis
            keys = await self._redis.keys("sms:ratelimit:*")
            limits = {}
            for key in keys:
                value = await self._redis.get(key)
                limits[key] = int(value) if value else 0

            return {
                "limits": limits,
                "provider": self.provider,
                "max_concurrent": MAX_CONCURRENT_REQUESTS
            }
        except Exception as e:
            return {"error": str(e)}

# Global async SMS service instance
async_sms_service = AsyncSMSService()

# Celery tasks for background processing
from celery import Celery

celery_app = Celery(
    "sms_service",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

@celery_app.task(bind=True)
def send_sms_background(self, to: str, message: str, priority: str = "normal"):
    """Background task for sending SMS."""
    try:
        # Use synchronous service for background tasks
        from sms_service import default_sms_service
        if default_sms_service:
            result = default_sms_service.send(to, message)
            return result
        else:
            return {"success": False, "error": "SMS service not available"}
    except Exception as e:
        logger.error(f"Background SMS send error: {e}")
        return {"success": False, "error": str(e)}

@celery_app.task(bind=True)
def send_bulk_sms_background(self, messages: List[Dict[str, str]]):
    """Background task for sending bulk SMS."""
    results = []
    try:
        from sms_service import default_sms_service
        if default_sms_service:
            for msg in messages:
                try:
                    result = default_sms_service.send(msg["to"], msg["message"])
                    results.append(result)
                except Exception as e:
                    results.append({"success": False, "error": str(e)})
        else:
            results = [{"success": False, "error": "SMS service not available"} for _ in messages]
    except Exception as e:
        logger.error(f"Background bulk SMS error: {e}")
        results = [{"success": False, "error": str(e)} for _ in messages]

    return results

# Utility functions
async def initialize_sms_service():
    """Initialize the async SMS service."""
    await async_sms_service.initialize()

async def cleanup_sms_service():
    """Cleanup the async SMS service."""
    await async_sms_service.cleanup()

# Backward compatibility
def get_async_sms_service():
    """Get async SMS service instance."""
    return async_sms_service
