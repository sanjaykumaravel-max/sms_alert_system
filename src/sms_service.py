import logging
import os
from typing import Any, Iterable, List, Dict, Optional, Callable

import requests
import re
import time
import concurrent.futures

try:
    # When imported as package (src.sms_service)
    from .config import SMS_ENABLED, SMS_API_KEY, SMS_SENDER_ID
except Exception:
    # When src/ is on sys.path and modules are imported as top-level (tests do this)
    from config import SMS_ENABLED, SMS_API_KEY, SMS_SENDER_ID
import json
from pathlib import Path

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path

# runtime settings path
SETTINGS_FILE = data_path("settings.json")

# If a centralized `settings` object exists, prefer its values but keep
# module-level constants for backward compatibility.
try:
    try:
        from .config import settings as _settings
    except Exception:
        from config import settings as _settings
except Exception:
    _settings = None

if _settings:
    try:
        SMS_ENABLED = getattr(_settings, 'SMS_ENABLED', SMS_ENABLED)
    except Exception:
        pass
    try:
        SMS_API_KEY = getattr(_settings, 'SMS_API_KEY', SMS_API_KEY)
    except Exception:
        pass
    try:
        SMS_SENDER_ID = getattr(_settings, 'SMS_SENDER_ID', SMS_SENDER_ID)
    except Exception:
        pass

DEFAULT_PROVIDER = None
if _settings:
    DEFAULT_PROVIDER = getattr(_settings, 'SMS_PROVIDER', None)
if not DEFAULT_PROVIDER:
    DEFAULT_PROVIDER = os.getenv('SMS_PROVIDER', 'fast2sms')


def is_sms_enabled_runtime() -> bool:
    """Check runtime settings (data/settings.json) first, then fall back to config.SMS_ENABLED."""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            return bool(s.get("sms_enabled", SMS_ENABLED))
    except Exception:
        pass
    return bool(SMS_ENABLED)


logger = logging.getLogger(__name__)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_futures: List[concurrent.futures.Future] = []

# sentinel to distinguish omitted args from explicit None
_UNSET = object()


class SMSService:
    """Simple SMS service supporting a generic REST provider, Fast2SMS, or Twilio."""
    _REQUEST_ID_KEYS = ("request_id", "requestId", "message_id", "messageId", "sid", "id")

    _DELIVERY_STATUS_TERMINAL_SUCCESS_WORDS = ("delivered", "delivery complete", "dlvrd")
    _DELIVERY_STATUS_TERMINAL_FAILURE_WORDS = (
        "undelivered",
        "not delivered",
        "failed",
        "failure",
        "rejected",
        "expired",
        "dropped",
        "blocked",
        "invalid",
    )
    _DELIVERY_STATUS_PENDING_WORDS = (
        "pending",
        "queued",
        "submitted",
        "sent",
        "processing",
        "in transit",
        "in_transit",
    )

    def __init__(
        self,
        api_key: Optional[str] = _UNSET,
        sender_id: Optional[str] = _UNSET,
        provider_url: Optional[str] = None,
        provider: str = _UNSET,
        twilio_sid: Optional[str] = None,
        twilio_token: Optional[str] = None,
    ):
        self.enabled = SMS_ENABLED
        # If caller omitted the parameter (left as _UNSET), fall back to config constants.
        # If caller explicitly passed None, treat as "no key" and preserve None.
        self.api_key = SMS_API_KEY if api_key is _UNSET else api_key
        self.sender_id = SMS_SENDER_ID if sender_id is _UNSET else sender_id
        self.provider_url = provider_url
        # provider default precedence: explicit arg -> env/settings DEFAULT_PROVIDER -> 'generic'
        if provider is _UNSET:
            self.provider = DEFAULT_PROVIDER or 'generic'
        else:
            self.provider = provider
        self.twilio_sid = twilio_sid
        self.twilio_token = twilio_token

    def send(self, to: str, message: str) -> Dict:
        """Send a single SMS. `to` should be in international format (+...)."""
        # Mock provider short-circuit for local development/testing
        if (self.provider or '').lower() == 'mock' or os.getenv('SMS_PROVIDER', '').lower() == 'mock':
            logging.getLogger(__name__).info("Mock SMS provider: skipping real send to %s", to)
            return {"success": True, "mock": True}
        if not is_sms_enabled_runtime():
            logger.info("SMS disabled by runtime settings — skipping send to %s", to)
            return {"success": True, "skipped": True}

        if self.provider == "twilio":
            res = self._send_twilio(to, message)
            try:
                _record_audit_entry(to, self.provider, message, res)
            except Exception:
                pass
            return res
        if self.provider == "fast2sms":
            res = self._send_fast2sms(to, message)
            try:
                _record_audit_entry(to, self.provider, message, res)
            except Exception:
                pass
            return res
        return self._send_generic(to, message)

    def _attempt_send_with_retry(self, to: str, message: str, retries: int = 2, backoff: float = 1.5) -> Dict:
        last_err = None
        for attempt in range(0, retries + 1):
            try:
                if self.provider == "twilio":
                    res = self._send_twilio(to, message)
                elif self.provider == "fast2sms":
                    res = self._send_fast2sms(to, message)
                else:
                    res = self._send_generic(to, message)

                if res.get("success"):
                    try:
                        _record_audit_entry(to, self.provider, message, res)
                    except Exception:
                        pass
                    return res
                last_err = res
            except Exception as e:
                last_err = {"success": False, "error": str(e)}

            try:
                time.sleep(backoff * (1 + attempt))
            except Exception:
                pass

        try:
            if self.provider != "twilio" and self.twilio_sid and self.twilio_token:
                logger.info("Attempting fallback to Twilio for %s", to)
                return self._send_twilio(to, message)
        except Exception:
            logger.exception("Twilio fallback failed")

        try:
            if self.provider != "generic" and self.provider_url:
                logger.info("Attempting fallback to generic provider for %s", to)
                return self._send_generic(to, message)
        except Exception:
            logger.exception("Generic fallback failed")

        return last_err or {"success": False, "error": "unknown"}

    def send_async(self, to: str, message: str, callback: Optional[Callable[[Dict], None]] = None, retries: int = 2) -> concurrent.futures.Future:
        # If mock provider is enabled, return an immediate successful future
        if (self.provider or '').lower() == 'mock' or os.getenv('SMS_PROVIDER', '').lower() == 'mock':
            logger.info("Mock SMS async send to %s", to)
            fut = concurrent.futures.Future()
            fut.set_result({"success": True, "mock": True})
            if callback:
                try:
                    callback(fut.result())
                except Exception:
                    logger.exception("Callback failed")
            return fut

        if not is_sms_enabled_runtime():
            logger.info("SMS disabled - skipping async send to %s", to)
            fut = concurrent.futures.Future()
            fut.set_result({"success": True, "skipped": True})
            if callback:
                try:
                    callback(fut.result())
                except Exception:
                    logger.exception("Callback failed")
            return fut

        def _work():
            return self._attempt_send_with_retry(to, message, retries=retries)

        future = _executor.submit(_work)
        try:
            _futures.append(future)
        except Exception:
            pass

        if callback:
            def _on_done(fut):
                try:
                    callback(fut.result())
                except Exception:
                    logger.exception("send_async callback failed")
            future.add_done_callback(_on_done)

        return future

    def send_bulk_async(self, recipients: Iterable[str], message: str, callback: Optional[Callable[[Dict, str], None]] = None, retries: int = 2) -> List[concurrent.futures.Future]:
        futures = []
        for r in recipients:
            fut = self.send_async(r, message, callback=(lambda res, r=r: callback(res, r)) if callback else None, retries=retries)
            futures.append(fut)
        return futures

    def send_bulk(self, recipients: Iterable[str], message: str) -> List[Dict]:
        results = []
        for r in recipients:
            results.append(self.send(r, message))
        return results

    def send_to_operators(self, operators: Iterable[Dict], message_template: str) -> List[Dict]:
        results = []
        for op in operators:
            phone = op.get("phone")
            if not phone:
                logger.warning("Operator missing phone: %s", op)
                continue
            message = message_template.format(**op)
            results.append(self.send(phone, message))
        return results

    def _find_first_matching_scalar(self, payload: Any, candidate_keys: tuple[str, ...]) -> Optional[str]:
        """Recursively find the first scalar value for any matching key."""
        if isinstance(payload, dict):
            for key in candidate_keys:
                value = payload.get(key)
                if isinstance(value, (str, int, float)) and str(value).strip():
                    return str(value).strip()
            for value in payload.values():
                found = self._find_first_matching_scalar(value, candidate_keys)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_matching_scalar(item, candidate_keys)
                if found:
                    return found
        return None

    def _extract_request_id(self, result: Dict[str, Any]) -> Optional[str]:
        """Extract request/message id from nested provider response structures."""
        if not isinstance(result, dict):
            return None
        request_id = self._find_first_matching_scalar(result, self._REQUEST_ID_KEYS)
        if request_id:
            return request_id
        return None

    def _collect_status_candidates(self, payload: Any, out: List[str]) -> None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                key_l = str(key).lower()
                if isinstance(value, (str, int, float)):
                    if (
                        "status" in key_l
                        or "state" in key_l
                        or "delivery" in key_l
                        or "dlr" in key_l
                    ):
                        out.append(str(value).strip().lower())
                else:
                    self._collect_status_candidates(value, out)
        elif isinstance(payload, list):
            for item in payload:
                self._collect_status_candidates(item, out)

    def _normalize_delivery_status(self, payload: Any) -> str:
        candidates: List[str] = []
        self._collect_status_candidates(payload, candidates)
        text_blob = " ".join(candidates).lower()

        if any(word in text_blob for word in self._DELIVERY_STATUS_TERMINAL_FAILURE_WORDS):
            return "failed"

        if any(word in text_blob for word in self._DELIVERY_STATUS_TERMINAL_SUCCESS_WORDS):
            # Protect against phrases like "not delivered".
            if "not delivered" in text_blob or "undelivered" in text_blob:
                return "failed"
            return "delivered"

        if any(word in text_blob for word in self._DELIVERY_STATUS_PENDING_WORDS):
            return "pending"

        return "unknown"

    def check_delivery_status(self, request_id: str) -> Dict[str, Any]:
        """Check Fast2SMS delivery report for a request id."""
        request_id = str(request_id or "").strip()
        if not request_id:
            return {"success": False, "error": "request_id is required"}

        if (self.provider or "").lower() != "fast2sms":
            return {"success": False, "error": "delivery status check currently supports fast2sms only"}

        if not self.api_key:
            return {"success": False, "error": "Fast2SMS API key not configured"}

        url = f"https://www.fast2sms.com/dev/dlr/{request_id}"
        params = {"authorization": self.api_key}

        try:
            # Fast2SMS expects API key in query params for GET endpoints.
            resp = requests.get(url, params=params, timeout=12)
            resp.raise_for_status()
            payload = resp.json() if resp.content else {}
            status = self._normalize_delivery_status(payload)
            delivered = status == "delivered"
            terminal = status in ("delivered", "failed")
            return {
                "success": True,
                "provider": "fast2sms",
                "request_id": request_id,
                "delivery_status": status,
                "delivered": delivered,
                "terminal": terminal,
                "status_code": resp.status_code,
                "response": payload,
            }
        except requests.exceptions.HTTPError as exc:
            response = getattr(exc, "response", None)
            response_text = None
            status_code = None
            try:
                if response is not None:
                    response_text = response.text
                    status_code = response.status_code
            except Exception:
                pass
            return {
                "success": False,
                "provider": "fast2sms",
                "request_id": request_id,
                "error": str(exc),
                "status_code": status_code,
                "response_text": response_text,
            }
        except Exception as exc:
            return {
                "success": False,
                "provider": "fast2sms",
                "request_id": request_id,
                "error": str(exc),
            }

    def poll_delivery_status(
        self,
        request_id: str,
        timeout_seconds: int = 180,
        poll_interval_seconds: int = 12,
    ) -> Dict[str, Any]:
        """Poll provider DLR API until a terminal status or timeout."""
        timeout_seconds = max(10, int(timeout_seconds or 0))
        poll_interval_seconds = max(3, int(poll_interval_seconds or 0))

        deadline = time.time() + timeout_seconds
        last_report: Dict[str, Any] = {
            "success": False,
            "request_id": request_id,
            "delivery_status": "unknown",
            "delivered": False,
            "terminal": False,
        }

        while time.time() < deadline:
            report = self.check_delivery_status(request_id)
            if isinstance(report, dict):
                last_report = report
            if report.get("success") and report.get("terminal"):
                report["timed_out"] = False
                return report
            if time.time() + poll_interval_seconds >= deadline:
                break
            time.sleep(poll_interval_seconds)

        final_report = dict(last_report or {})
        final_report["timed_out"] = True
        if final_report.get("delivery_status") in (None, "", "unknown"):
            final_report["delivery_status"] = "pending_timeout"
        final_report.setdefault("delivered", False)
        final_report.setdefault("terminal", False)
        return final_report

    def send_with_delivery_retry(
        self,
        to: str,
        message: str,
        max_retries: int = 1,
        delivery_timeout_seconds: int = 180,
        poll_interval_seconds: int = 12,
        initial_poll_delay_seconds: int = 18,
        retry_backoff_seconds: int = 12,
    ) -> Dict[str, Any]:
        """Send SMS and verify delivery report; retry on non-delivery (Fast2SMS only)."""
        total_attempts = max(1, int(max_retries) + 1)
        attempts: List[Dict[str, Any]] = []
        last_result: Dict[str, Any] = {}

        for attempt_idx in range(total_attempts):
            send_result = self.send(to, message)
            current_result: Dict[str, Any] = dict(send_result or {})
            request_id = self._extract_request_id(current_result)
            if request_id:
                current_result["request_id"] = request_id
                current_result.setdefault("message_id", request_id)

            current_result["attempt"] = attempt_idx + 1
            current_result["retry_attempts"] = attempt_idx
            current_result.setdefault("send_success", bool(current_result.get("success")))
            current_result["delivery_checked"] = False
            current_result["delivered"] = False
            current_result["delivery_status"] = "unknown"

            if current_result.get("send_success") and (self.provider or "").lower() == "fast2sms" and request_id:
                if initial_poll_delay_seconds > 0:
                    time.sleep(max(1, int(initial_poll_delay_seconds)))
                delivery_report = self.poll_delivery_status(
                    request_id=request_id,
                    timeout_seconds=delivery_timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                )
                current_result["delivery_checked"] = True
                current_result["delivery"] = delivery_report
                current_result["delivery_status"] = delivery_report.get("delivery_status", "unknown")
                current_result["delivered"] = bool(delivery_report.get("delivered"))
                current_result["terminal"] = bool(delivery_report.get("terminal"))
                current_result["timed_out"] = bool(delivery_report.get("timed_out"))
                current_result["success"] = bool(current_result["delivered"])
                if current_result["delivered"]:
                    attempts.append(current_result)
                    current_result["attempts"] = attempts
                    current_result["final"] = "delivered"
                    return current_result
            else:
                # For non-Fast2SMS providers we cannot reliably check DLR here.
                current_result["success"] = bool(current_result.get("send_success"))
                if current_result["success"]:
                    attempts.append(current_result)
                    current_result["attempts"] = attempts
                    current_result["final"] = "sent_no_delivery_check"
                    return current_result

            attempts.append(current_result)
            last_result = current_result

            if attempt_idx < total_attempts - 1:
                time.sleep(max(1, int(retry_backoff_seconds)) * (attempt_idx + 1))

        out = dict(last_result or {"success": False, "error": "send_failed"})
        if out.get("send_success") and not out.get("delivered"):
            out["error"] = out.get("error") or "delivery_not_confirmed"
            out["warning"] = "SMS accepted by gateway but delivery not confirmed; retry may cause duplicate delivery."
        out["attempts"] = attempts
        return out

    def _send_generic(self, to: str, message: str) -> Dict:
        if not self.api_key:
            raise RuntimeError("SMS API key not configured")
        if not self.provider_url:
            raise RuntimeError("SMS provider URL not configured for generic provider")

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"to": to, "from": (self.sender_id or ""), "message": message}

        try:
            resp = requests.post(self.provider_url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            return {"success": True, "status_code": resp.status_code, "response": resp.json() if resp.content else {}}
        except Exception as e:
            logger.exception("Failed to send SMS to %s", to)
            return {"success": False, "error": str(e)}

    def _send_fast2sms(self, to: str, message: str) -> Dict:
        if not self.api_key:
            raise RuntimeError("Fast2SMS API key not configured")

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {"authorization": self.api_key, "Content-Type": "application/json"}
        clean_number = re.sub(r"\D", "", to or "")

        # Basic validation: Fast2SMS primarily supports Indian numbers (country code 91).
        # If number doesn't look like an Indian number, log and return a helpful error.
        def _validate_fast2sms_number(n: str) -> Optional[str]:
            if not n:
                return "empty"
            # Typical valid patterns: 10-digit local (XXXXXXXXXX) or 12-digit with 91 prefix (91XXXXXXXXXX)
            if len(n) == 10 and n.isdigit():
                return None
            if len(n) == 12 and n.startswith("91") and n[2:].isdigit():
                return None
            return f"unsupported format (digits={len(n)})"

        invalid_reason = _validate_fast2sms_number(clean_number)
        payload = {
            "message": message,
            "language": "english",
            "route": "q",
            "numbers": clean_number
        }

        if invalid_reason is not None:
            logger.warning("Fast2SMS: refusing to send to %s — %s", to, invalid_reason)
            return {"success": False, "error": "invalid_number_format", "reason": invalid_reason, "numbers": clean_number}

        logger.debug("Fast2SMS payload for %s -> %s", to, payload)

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            payload_json = resp.json() if resp.content else {}
            request_id = self._extract_request_id(payload_json if isinstance(payload_json, dict) else {})
            result = {"success": True, "status_code": resp.status_code, "response": payload_json}
            if request_id:
                result["request_id"] = request_id
                result["message_id"] = request_id
            return result
        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            resp_text = None
            status = None
            try:
                if resp is not None:
                    resp_text = resp.text
                    status = resp.status_code
            except Exception:
                pass
            logger.exception("Fast2SMS HTTP error sending to %s: %s", to, resp_text)

            # Detect common DLT / route-blocked error and attempt Twilio fallback if configured
            try:
                text_lower = (resp_text or "").lower()
                is_dlt_error = '998' in (resp_text or '') or 'route is blocked' in text_lower or 'dlt' in text_lower
            except Exception:
                is_dlt_error = False

            # Try Twilio fallback when DLT error and Twilio creds present
            if is_dlt_error:
                try:
                    sid = os.getenv('TWILIO_SID')
                    token = os.getenv('TWILIO_TOKEN')
                    sender = os.getenv('SMS_SENDER_ID') or self.sender_id
                    if sid and token:
                        try:
                            # lazy import to avoid hard dependency
                            from twilio.rest import Client as TwilioClient  # type: ignore
                            twc = TwilioClient(sid, token)
                            tw_resp = twc.messages.create(body=message, from_=sender, to=to)
                            return {"success": True, "provider": "twilio", "response": {"sid": getattr(tw_resp, 'sid', None)}}
                        except Exception:
                            logger.exception("Twilio fallback failed")
                except Exception:
                    pass

            return {"success": False, "status_code": status, "response_text": resp_text, "error": str(e)}
        except Exception as e:
            logger.exception("Fast2SMS send failed to %s", to)
            return {"success": False, "error": str(e)}

    def _send_twilio(self, to: str, message: str) -> Dict:
        if not (self.twilio_sid and self.twilio_token):
            raise RuntimeError("Twilio SID/token not configured")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        data = {"To": to, "From": self.sender_id or "", "Body": message}
        try:
            resp = requests.post(url, data=data, auth=(self.twilio_sid, self.twilio_token), timeout=10)
            resp.raise_for_status()
            return {"success": True, "status_code": resp.status_code, "response": resp.json()}
        except Exception as e:
            logger.exception("Twilio send failed to %s", to)
            return {"success": False, "error": str(e)}


def shutdown(wait: bool = False) -> None:
    try:
        for fut in list(_futures):
            try:
                if not fut.done():
                    fut.cancel()
            except Exception:
                pass
        _futures.clear()
    except Exception:
        pass

    try:
        _executor.shutdown(wait=wait)
    except Exception:
        pass

def _record_audit_entry(to: str, provider: str, message: str, result: dict) -> None:
    try:
        # Lazy import to avoid introducing DB dependency for callers that don't need it
        try:
            from .db import get_session, SMSAudit
        except Exception:
            from db import get_session, SMSAudit
        sess = get_session()
        sa = SMSAudit(
            to_number=to,
            provider=provider,
            message=message,
            success=1 if result.get('success') else 0,
            status_code=result.get('status_code'),
            response=result.get('response') or result.get('response_text') or None,
            error=result.get('error') or None,
        )
        sess.add(sa)
        sess.commit()
        sess.close()
    except Exception:
        logger.exception('Failed to record SMS audit entry')


# Convenience module-level instance using config values. You can override provider by creating
# your own `SMSService(...)` instance.
_default_twilio_sid = None
_default_twilio_token = None
if _settings:
    try:
        _default_twilio_sid = getattr(_settings, 'TWILIO_SID', None)
        _default_twilio_token = getattr(_settings, 'TWILIO_TOKEN', None)
    except Exception:
        pass

# Create a convenient module-level default service using configuration
default_sms_service = SMSService(
    provider=(DEFAULT_PROVIDER or 'fast2sms'),
    api_key=SMS_API_KEY,
    sender_id=SMS_SENDER_ID,
    twilio_sid=_default_twilio_sid,
    twilio_token=_default_twilio_token,
)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    svc = SMSService()
    print(svc.send("+1234567890", "Test alert from Mining PMS"))
