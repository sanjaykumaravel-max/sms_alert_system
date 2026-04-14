"""Service lifecycle management: start/stop DB, cache, SMS, scheduler."""
import logging
from typing import Optional
import time

logger = logging.getLogger(__name__)


class Services:
    def __init__(self):
        self.db_inited = False
        self.sms = None
        self.cache = None
        self.scheduler = None

    def start(self, *, retries: int = 2, backoff: float = 1.0) -> None:
        """Start services with simple retry/backoff logic."""
        for attempt in range(retries + 1):
            try:
                # DB
                from .db import init_db
                init_db()
                self.db_inited = True

                # SMS default service
                from .sms_service import default_sms_service
                self.sms = default_sms_service

                # cache placeholder
                try:
                    from .models import cache
                    self.cache = cache
                except Exception:
                    self.cache = None

                # scheduler placeholder
                self.scheduler = None

                # Start offline queue processor thread (best-effort)
                try:
                    from .offline_queue import process_queue
                    import threading as _threading

                    def _queue_worker():
                        import os as _os
                        server = _os.getenv('API_SERVER_URL')
                        api_key = _os.getenv('SERVER_API_KEY')
                        interval = int(_os.getenv('OFFLINE_SYNC_INTERVAL', '300'))
                        while True:
                            try:
                                if server:
                                    process_queue(server, api_key)
                            except Exception:
                                logger.exception('Offline queue worker error')
                            try:
                                time.sleep(interval)
                            except Exception:
                                time.sleep(60)

                    self._offline_thread = _threading.Thread(target=_queue_worker, daemon=True)
                    self._offline_thread.start()
                except Exception:
                    pass

                logger.info('Services started')
                return
            except Exception as e:
                logger.exception('Failed to start services (attempt %s): %s', attempt, e)
                try:
                    time.sleep(backoff * (1 + attempt))
                except Exception:
                    pass
        raise RuntimeError('Failed to start services after retries')

    def stop(self) -> None:
        try:
            # shutdown scheduler if present
            if getattr(self, 'scheduler', None):
                try:
                    self.scheduler.stop()
                except Exception:
                    pass

            # stop offline thread (best-effort)
            try:
                if getattr(self, '_offline_thread', None):
                    # daemon thread will exit when process exits; attempt graceful join
                    try:
                        self._offline_thread.join(timeout=0.1)
                    except Exception:
                        pass
            except Exception:
                pass

            # shutdown sms futures
            try:
                from .sms_service import shutdown as sms_shutdown
                sms_shutdown(wait=False)
            except Exception:
                pass

            logger.info('Services stopped')
        except Exception:
            logger.exception('Error stopping services')


_services: Optional[Services] = None


def get_services() -> Services:
    global _services
    if _services is None:
        _services = Services()
    return _services


def start_services():
    s = get_services()
    s.start()
    return s


def stop_services():
    s = get_services()
    s.stop()
