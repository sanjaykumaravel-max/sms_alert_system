"""
Celery Tasks for SMS Alert App Background Processing.

This module defines background tasks for:
- SMS sending operations
- Bulk message processing
- Scheduled notifications
- Report generation and cleanup
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from celery_app import celery_app
from sms_service import default_sms_service
from api_client import sync_get_machines
from config import SMS_ENABLED

from redis import Redis
import psutil

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="src.tasks.send_sms_task")
def send_sms_task(self, to: str, message: str, priority: str = "normal") -> Dict[str, Any]:
    """
    Background task for sending individual SMS messages.

    Args:
        to: Recipient phone number
        message: SMS message content
        priority: Message priority

    Returns:
        Dict with send result
    """
    try:
        if not default_sms_service or not SMS_ENABLED:
            return {"success": False, "error": "SMS service not available"}

        result = default_sms_service.send(to, message)

        logger.info(f"SMS sent to {to}: {result.get('success', False)}")
        return result

    except Exception as e:
        logger.error(f"SMS task error for {to}: {e}")
        self.retry(countdown=60, max_retries=3)  # Retry after 1 minute
        return {"success": False, "error": str(e)}

@celery_app.task(bind=True, name="src.tasks.send_bulk_sms_task")
def send_bulk_sms_task(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Background task for sending bulk SMS messages.

    Args:
        messages: List of dicts with 'to' and 'message' keys

    Returns:
        List of send results
    """
    results = []
    success_count = 0
    failure_count = 0

    try:
        if not default_sms_service or not SMS_ENABLED:
            error_result = {"success": False, "error": "SMS service not available"}
            return [error_result] * len(messages)

        for i, msg in enumerate(messages):
            try:
                result = default_sms_service.send(msg["to"], msg["message"])
                results.append(result)

                if result.get("success"):
                    success_count += 1
                else:
                    failure_count += 1

                # Update task state for progress tracking
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current": i + 1,
                        "total": len(messages),
                        "success": success_count,
                        "failure": failure_count
                    }
                )

            except Exception as e:
                logger.error(f"Bulk SMS error for {msg.get('to', 'unknown')}: {e}")
                results.append({"success": False, "error": str(e)})
                failure_count += 1

        logger.info(f"Bulk SMS completed: {success_count} success, {failure_count} failure")
        return results

    except Exception as e:
        logger.error(f"Bulk SMS task error: {e}")
        self.retry(countdown=300, max_retries=2)  # Retry after 5 minutes
        return [{"success": False, "error": str(e)}] * len(messages)

@celery_app.task(bind=True, name="src.tasks.send_scheduled_notifications")
def send_scheduled_notifications(self, notification_type: str) -> Dict[str, Any]:
    """
    Background task for sending scheduled notifications.

    Args:
        notification_type: Type of notifications ('maintenance', 'critical', 'overdue')

    Returns:
        Dict with operation results
    """
    try:
        machines = sync_get_machines() or []
        results = {"total": 0, "sent": 0, "failed": 0, "type": notification_type}

        if not machines:
            logger.warning("No machines found for scheduled notifications")
            return results

        for machine in machines:
            try:
                status = machine.get("status", "").lower()
                operator_phone = machine.get("operator_phone")

                if not operator_phone:
                    continue

                # Check if notification should be sent based on type
                should_send = False
                message = ""

                if notification_type == "maintenance" and status in ("due", "maintenance"):
                    should_send = True
                    message = f"MAINTENANCE REMINDER: {machine.get('id')} requires maintenance."

                elif notification_type == "critical" and status == "critical":
                    should_send = True
                    message = f"CRITICAL ALERT: {machine.get('id')} needs immediate attention!"

                elif notification_type == "overdue" and status == "overdue":
                    should_send = True
                    message = f"OVERDUE MAINTENANCE: {machine.get('id')} is overdue for service."

                if should_send and message:
                    result = send_sms_task.apply(args=[operator_phone, message, "normal"])
                    results["total"] += 1

                    if result.get("success"):
                        results["sent"] += 1
                    else:
                        results["failed"] += 1

            except Exception as e:
                logger.error(f"Error processing machine {machine.get('id')}: {e}")
                results["failed"] += 1

        logger.info(f"Scheduled {notification_type} notifications: {results}")
        return results

    except Exception as e:
        logger.error(f"Scheduled notifications task error: {e}")
        self.retry(countdown=600, max_retries=3)  # Retry after 10 minutes
        return {"error": str(e), "type": notification_type}

@celery_app.task(bind=True, name="src.tasks.generate_reports")
def generate_reports(self, report_type: str) -> Dict[str, Any]:
    """
    Background task for generating reports.

    Args:
        report_type: Type of report ('daily', 'weekly', 'monthly')

    Returns:
        Dict with report generation results
    """
    try:
        from datetime import datetime
        import csv
        from pathlib import Path

        # Create reports directory
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_type}_report_{timestamp}.csv"
        filepath = reports_dir / filename

        machines = sync_get_machines() or []

        # Generate report data
        with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["id", "type", "status", "operator_phone", "last_maintenance"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for machine in machines:
                writer.writerow({
                    "id": machine.get("id", ""),
                    "type": machine.get("type", ""),
                    "status": machine.get("status", ""),
                    "operator_phone": machine.get("operator_phone", ""),
                    "last_maintenance": machine.get("last_maintenance", "")
                })

        result = {
            "success": True,
            "report_type": report_type,
            "filename": filename,
            "filepath": str(filepath),
            "records": len(machines),
            "timestamp": timestamp
        }

        logger.info(f"Report generated: {result}")
        return result

    except Exception as e:
        logger.error(f"Report generation error: {e}")
        self.retry(countdown=300, max_retries=2)  # Retry after 5 minutes
        return {"success": False, "error": str(e), "report_type": report_type}

@celery_app.task(bind=True, name="src.tasks.cleanup_old_data")
def cleanup_old_data(self) -> Dict[str, Any]:
    """
    Background task for cleaning up old data and logs.

    Returns:
        Dict with cleanup results
    """
    try:
        from pathlib import Path
        import shutil
        from datetime import datetime, timedelta

        results = {"logs_cleaned": 0, "temp_files_cleaned": 0, "cache_cleared": False}

        # Clean old log files (older than 30 days)
        logs_dir = Path("logs")
        if logs_dir.exists():
            cutoff_date = datetime.now() - timedelta(days=30)

            for log_file in logs_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    results["logs_cleaned"] += 1

        # Clean temporary files
        temp_dirs = ["temp", "tmp", "__pycache__"]
        for temp_dir in temp_dirs:
            temp_path = Path(temp_dir)
            if temp_path.exists() and temp_path.is_dir():
                shutil.rmtree(temp_path, ignore_errors=True)
                results[f"{temp_dir}_cleaned"] = True

        # Clean __pycache__ directories recursively
        for pycache_dir in Path(".").rglob("__pycache__"):
            if pycache_dir.is_dir():
                shutil.rmtree(pycache_dir, ignore_errors=True)

        results["cache_cleared"] = True

        logger.info(f"Cleanup completed: {results}")
        return results

    except Exception as e:
        logger.error(f"Cleanup task error: {e}")
        return {"success": False, "error": str(e)}

@celery_app.task(bind=True, name="src.tasks.health_check")
def health_check_task(self) -> Dict[str, Any]:
    """
    Background task for system health checks.

    Returns:
        Dict with health check results
    """
    try:
        results = {
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "system": {}
        }

        # Check Redis
        try:
            r = Redis()
            r.ping()
            results["services"]["redis"] = "healthy"
        except:
            results["services"]["redis"] = "unhealthy"

        # Check SMS service
        try:
            from .sms_service import default_sms_service
            results["services"]["sms"] = "healthy" if default_sms_service else "unhealthy"
        except:
            results["services"]["sms"] = "unhealthy"

        # System metrics
        results["system"] = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }

        return results

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}