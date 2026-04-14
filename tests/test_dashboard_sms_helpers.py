from src.ui.dashboard import _normalize_sms_phone, _is_placeholder_sms_phone


def test_normalize_sms_phone_indian_local_number():
    assert _normalize_sms_phone("6381528758") == "+916381528758"


def test_normalize_sms_phone_country_prefixed_number():
    assert _normalize_sms_phone("91 63815 28758") == "+916381528758"


def test_normalize_sms_phone_invalid_short_number():
    assert _normalize_sms_phone("12345") is None


def test_placeholder_phone_filter():
    assert _is_placeholder_sms_phone("555-0101") is True
    assert _is_placeholder_sms_phone("+916381528758") is False
