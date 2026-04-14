import pytest
from src.sms_service import SMSService


def test_send_generic_requires_config():
    svc = SMSService(api_key=None, provider_url=None, provider='generic')
    with pytest.raises(RuntimeError):
        svc._send_generic('+123', 'hello')


def test_send_fast2sms_requires_api_key():
    svc = SMSService(api_key=None, provider='fast2sms')
    with pytest.raises(RuntimeError):
        svc._send_fast2sms('+123', 'hi')


def test_extract_request_id_from_nested_response():
    svc = SMSService(provider='fast2sms')
    result = {"success": True, "response": {"request_id": "REQ_12345"}}
    assert svc._extract_request_id(result) == "REQ_12345"


def test_check_delivery_status_parses_delivered(monkeypatch):
    svc = SMSService(api_key="dummy_key", provider='fast2sms')

    class DummyResponse:
        status_code = 200
        content = b"{}"

        def raise_for_status(self):
            return

        def json(self):
            return {"return": True, "data": {"delivery_status": "Delivered"}}

    def fake_get(url, params=None, timeout=0):
        assert "dev/dlr/REQ_1" in url
        assert params.get("authorization") == "dummy_key"
        return DummyResponse()

    monkeypatch.setattr("src.sms_service.requests.get", fake_get)
    out = svc.check_delivery_status("REQ_1")
    assert out["success"] is True
    assert out["delivery_status"] == "delivered"
    assert out["delivered"] is True
    assert out["terminal"] is True


def test_send_with_delivery_retry_retries_until_delivered(monkeypatch):
    svc = SMSService(provider='fast2sms')

    send_calls = []
    send_results = [
        {"success": True, "response": {"request_id": "REQ_A"}},
        {"success": True, "response": {"request_id": "REQ_B"}},
    ]
    delivery_reports = [
        {
            "success": True,
            "request_id": "REQ_A",
            "delivery_status": "pending_timeout",
            "delivered": False,
            "terminal": False,
            "timed_out": True,
        },
        {
            "success": True,
            "request_id": "REQ_B",
            "delivery_status": "delivered",
            "delivered": True,
            "terminal": True,
            "timed_out": False,
        },
    ]

    def fake_send(to, message):
        send_calls.append((to, message))
        return send_results[len(send_calls) - 1]

    def fake_poll(request_id, timeout_seconds=0, poll_interval_seconds=0):
        return delivery_reports.pop(0)

    monkeypatch.setattr(svc, "send", fake_send)
    monkeypatch.setattr(svc, "poll_delivery_status", fake_poll)
    monkeypatch.setattr("src.sms_service.time.sleep", lambda *_args, **_kwargs: None)

    out = svc.send_with_delivery_retry(
        "+916381528758",
        "hello",
        max_retries=1,
        delivery_timeout_seconds=5,
        poll_interval_seconds=1,
        initial_poll_delay_seconds=0,
        retry_backoff_seconds=0,
    )

    assert len(send_calls) == 2
    assert out["success"] is True
    assert out["delivered"] is True
    assert out["retry_attempts"] == 1
