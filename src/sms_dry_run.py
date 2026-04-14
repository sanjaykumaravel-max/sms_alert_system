from config import SMS_API_KEY, SMS_SENDER_ID

def build_fast2sms_payload(to: str, message: str) -> dict:
    return {
        "url": "https://www.fast2sms.com/dev/bulkV2",
        "headers": {"authorization": SMS_API_KEY, "Content-Type": "application/json"},
        "payload": {
            "message": message,
            "language": "english",
            "route": "q",
            "numbers": to.replace(" ", "")
        }
    }


if __name__ == "__main__":
    # Dry-run: no network call, just show the request that WOULD be made.
    # User supplied number: 6381528758 — assuming India (+91) prefix for international format.
    to = "+91" + "6381528758"
    message = "DRY-RUN ALERT: This is a test alert from Mining PMS."

    req = build_fast2sms_payload(to, message)
    print("Dry-run Fast2SMS request (no network call):")
    print("URL:", req["url"])
    print("Headers:", req["headers"])
    print("Payload:", req["payload"])
