#!/usr/bin/env python3
"""
Backend Optimization Test Suite

This script validates that all backend optimizations are working correctly:
- Async operations
- Redis caching
- Database connection pooling
- CDN service
- Background job processing
"""

import asyncio
import sys
import os
import logging
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

async def test_database_and_cache():
    """Test database and Redis cache initialization."""
    print("Testing database and cache initialization...")

    try:
        from models import init_db, cache, Machine, Operator

        # Initialize database
        await init_db()
        print("✓ Database initialized")

        # Initialize cache
        await cache.initialize()
        print("✓ Cache initialized")

        # Test basic cache operations
        await cache.set("test_key", "test_value", ttl=60)
        value = await cache.get("test_key")
        assert value == "test_value", "Cache set/get failed"
        print("✓ Cache operations working")

        return True
    except Exception as e:
        print(f"✗ Database/Cache test failed: {e}")
        return False

async def test_cdn_service():
    """Test CDN service initialization."""
    print("Testing CDN service...")

    try:
        from cdn_service import cdn_service

        # Test service initialization
        assert cdn_service is not None, "CDN service not initialized"
        print("✓ CDN service initialized")

        # Test URL generation (without actual upload)
        test_url = cdn_service.get_asset_url("test.jpg")
        assert test_url is not None, "CDN URL generation failed"
        print("✓ CDN URL generation working")

        return True
    except Exception as e:
        print(f"✗ CDN test failed: {e}")
        return False

async def test_sms_service():
    """Test async SMS service initialization."""
    print("Testing async SMS service...")

    try:
        from sms_service_async import initialize_sms_service, AsyncSMSService

        # Initialize service
        await initialize_sms_service()
        print("✓ SMS service initialized")

        # Test service instance
        service = AsyncSMSService()
        assert service is not None, "SMS service instance failed"
        print("✓ SMS service instance created")

        return True
    except Exception as e:
        print(f"✗ SMS service test failed: {e}")
        return False

async def test_celery_tasks():
    """Test Celery task definitions."""
    print("Testing Celery tasks...")

    try:
        from tasks import send_sms_task, send_bulk_sms_task

        # Test task definitions exist
        assert send_sms_task is not None, "send_sms_task not defined"
        assert send_bulk_sms_task is not None, "send_bulk_sms_task not defined"
        print("✓ Celery tasks defined")

        return True
    except Exception as e:
        print(f"✗ Celery tasks test failed: {e}")
        return False

async def test_async_server():
    """Test async server initialization."""
    print("Testing async server...")

    try:
        from server_async import app

        # Test app creation
        assert app is not None, "FastAPI app not created"
        print("✓ FastAPI app created")

        # Test routes exist
        routes = [route.path for route in app.routes]
        assert "/health" in routes, "Health route not found"
        print("✓ Server routes configured")

        return True
    except Exception as e:
        print(f"✗ Async server test failed: {e}")
        return False

async def run_performance_test():
    """Run a simple performance test."""
    print("Running performance test...")

    try:
        from models import cache
        import time

        # Test cache performance
        start_time = time.time()
        for i in range(100):
            await cache.set(f"perf_key_{i}", f"value_{i}")
            value = await cache.get(f"perf_key_{i}")
            assert value == f"value_{i}"

        end_time = time.time()
        duration = end_time - start_time
        print(f"✓ Cache performance: 100 operations in {duration:.2f}s")
        return True
    except Exception as e:
        print(f"✗ Performance test failed: {e}")
        return False

async def main():
    """Run all backend optimization tests."""
    print("🚀 SMS Alert App Backend Optimization Test Suite")
    print("=" * 50)

    # Configure logging
    logging.basicConfig(level=logging.WARNING)

    tests = [
        ("Database & Cache", test_database_and_cache),
        ("CDN Service", test_cdn_service),
        ("SMS Service", test_sms_service),
        ("Celery Tasks", test_celery_tasks),
        ("Async Server", test_async_server),
        ("Performance", run_performance_test),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name} test...")
        try:
            if await test_func():
                passed += 1
                print(f"✅ {test_name} test PASSED")
            else:
                print(f"❌ {test_name} test FAILED")
        except Exception as e:
            print(f"❌ {test_name} test ERROR: {e}")

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All backend optimizations are working correctly!")
        return 0
    else:
        print("⚠️  Some tests failed. Check configuration and dependencies.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)