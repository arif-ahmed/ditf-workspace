"""Shared steps for the cases (not a case file: the runner only loads cases/NN_*.py)."""
import hashlib, hmac, importlib, time, uuid

from client import adm, mock, pub, sql


MOCK_SECRET = "mocksecret0123456789abcdef"  # fixed test value from dev.ps1 -MockPayments (DGEPAY_CLIENT_SECRET)


def ipn_sig(uid):
    return hmac.new(MOCK_SECRET.encode(), ("ipn:" + uid).encode(), hashlib.sha256).hexdigest()[:40]


def b3():
    return importlib.import_module("cases.03_booking_public")


def ean13(d12):
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12))
    return d12 + str((10 - total % 10) % 10)


def txn_of(booking_id):
    return sql(f"SELECT txn_id FROM booking_master WHERE id = '{booking_id}'")


def checkout(booking_id, method=None):
    """Start a DGePay checkout on the mock; returns (unique_txn_id, mock's record of it)."""
    body = {"booking_master_id": booking_id}
    if method:
        body["payment_method"] = method
    r = pub("POST", "/initiate-payment", body=body, encrypted=True)
    uid = txn_of(booking_id)
    return uid, mock("/mock/state")["checkouts"].get(uid), r


def pay(booking_id, via_callback=True):
    """Full happy path: checkout, customer pays on the mock, browser returns to the callback."""
    uid, co, _ = checkout(booking_id)
    mock("/mock/result", {"unique_txn_id": uid, "status_code": 3})
    if via_callback:
        pub("GET", co["redirect_url"], params={"data": "x"})
    return uid, co


def wait(pred, seconds=30, every=0.5):
    end = time.time() + seconds
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(every)
    return pred()


def barcode_of(booking_id):
    return sql(f"SELECT trade_fair_ticket_barcode FROM booking_barcode_details WHERE booking_master_id = '{booking_id}' LIMIT 1")


def unique_phone():
    return "017" + str(uuid.uuid4().int)[:8]
