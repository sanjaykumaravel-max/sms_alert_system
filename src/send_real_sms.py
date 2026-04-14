from sms_service import default_sms_service

if __name__ == "__main__":
    # target number requested by user (assume India code)
    to = "+91" + "6381528758"
    message = "ALERT: Test alert from Mining PMS — please acknowledge."
    print("Sending SMS to", to)
    if hasattr(default_sms_service, "send_with_delivery_retry"):
        res = default_sms_service.send_with_delivery_retry(
            to,
            message,
            max_retries=1,
            delivery_timeout_seconds=120,
            poll_interval_seconds=12,
            initial_poll_delay_seconds=18,
            retry_backoff_seconds=10,
        )
    else:
        res = default_sms_service.send(to, message)
    print("Result:", res)
