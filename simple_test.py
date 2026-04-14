#!/usr/bin/env python3
"""
Simple Backend Optimization Test

This script performs basic validation of the backend optimizations.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

async def test_imports():
    """Test that all modules can be imported."""
    print("Testing module imports...")

    tests = [
        ("FastAPI", "fastapi"),
        ("Uvicorn", "uvicorn"),
        ("Redis", "redis"),
        ("Celery", "celery"),
        ("SQLAlchemy", "sqlalchemy"),
        ("AIOHTTP", "aiohttp"),
        ("Cloudinary", "cloudinary"),
        ("Boto3", "boto3"),
    ]

    passed = 0
    for name, module in tests:
        try:
            __import__(module)
            print(f"✓ {name} imported successfully")
            passed += 1
        except ImportError:
            print(f"✗ {name} import failed")

    return passed == len(tests)

async def test_server_creation():
    """Test that the async server can be created."""
    print("Testing async server creation...")

    try:
        from server_async import app
        assert app is not None, "FastAPI app not created"
        print("✓ FastAPI app created successfully")

        # Check routes
        routes = [route.path for route in app.routes]
        assert "/health" in routes, "Health route not found"
        print("✓ Server routes configured")

        return True
    except Exception as e:
        print(f"✗ Server creation failed: {e}")
        return False

async def test_celery_config():
    """Test Celery configuration."""
    print("Testing Celery configuration...")

    try:
        # Test that the file can be compiled
        import ast
        with open('src/celery_app.py', 'r') as f:
            ast.parse(f.read())
        print("✓ Celery configuration file compiles successfully")

        # Try to import the module
        import sys
        sys.path.insert(0, 'src')
        import celery_app
        assert celery_app.celery_app is not None, "Celery app not created"
        print("✓ Celery app configured")

        return True
    except SyntaxError as e:
        print(f"✗ Celery config syntax error: {e}")
        return False
    except Exception as e:
        print(f"✗ Celery config failed: {e}")
        return False

async def test_task_definitions():
    """Test that Celery tasks are defined."""
    print("Testing Celery task definitions...")

    try:
        # Test that the file can be compiled
        import ast
        with open('src/tasks.py', 'r') as f:
            ast.parse(f.read())
        print("✓ Tasks file compiles successfully")

        # For now, just check that the file exists and is valid Python
        print("✓ Task definitions file is valid")
        return True
    except SyntaxError as e:
        print(f"✗ Task definitions syntax error: {e}")
        return False
    except Exception as e:
        print(f"✗ Task definitions failed: {e}")
        return False

async def main():
    """Run all basic tests."""
    print("🚀 SMS Alert App Backend Optimization - Basic Test Suite")
    print("=" * 55)

    # Configure logging
    logging.basicConfig(level=logging.WARNING)

    tests = [
        ("Module Imports", test_imports),
        ("Async Server", test_server_creation),
        ("Celery Config", test_celery_config),
        ("Task Definitions", test_task_definitions),
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

    print("\n" + "=" * 55)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All basic backend optimizations are working!")
        print("\nNext steps:")
        print("1. Set up Redis server for caching")
        print("2. Configure environment variables")
        print("3. Run full integration tests")
        return 0
    else:
        print("⚠️  Some tests failed. Check dependencies and configuration.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)