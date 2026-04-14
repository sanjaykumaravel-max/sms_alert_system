import sys
import os
import threading

# ensure src is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from ui import dashboard


def test_schedule_retries_mixed_results():
    # prepare two operators: one success, one failure
    ops = [
        {'name': 'Alice', 'phone': '111'},
        {'name': 'Bob', 'phone': '222'},
    ]

    # fake sms_service with send_async that immediately calls back
    class FakeSMS:
        def __init__(self):
            self.calls = []

        def send_async(self, phone, msg, callback=None):
            self.calls.append((phone, msg))
            # call callback in-thread to simulate immediate result
            if phone == '111':
                if callback:
                    callback({'success': True})
            else:
                if callback:
                    callback({'success': False, 'error': 'network'})

    sms = FakeSMS()

    results = []

    def on_result(op, res):
        results.append((op, res))

    dashboard.schedule_retries(ops, sms, "ALERT: {name}", callback=on_result)

    # both operators should have been invoked
    assert len(sms.calls) == 2
    # callbacks should have been collected for both ops
    assert len(results) == 2
    # check success flag for first and failure for second
    assert results[0][1].get('success') is True
    assert results[1][1].get('success') is False
