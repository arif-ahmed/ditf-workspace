"""Booking -> initiate-payment -> mock DGePay -> callback/IPN -> ticket. Needs `dev.ps1 up -MockPayments`."""
import importlib, time

from client import mock, pub, sql
from helpers import ipn_sig
from runner import case

b3 = importlib.import_module("cases.03_booking_public")


def txn_of(bid):
    return sql(f"SELECT txn_id FROM booking_master WHERE id = '{bid}'")


@case("Initiate payment creates a checkout on the gateway")
def initiate(t):
    bid = b3.new_booking(adults=1).data.get("booking_master_id")
    t.ctx["paid_booking"] = bid
    r = pub("POST", "/initiate-payment", body={"booking_master_id": bid}, encrypted=True)
    t.check("webview_url returned", bool(r.data.get("webview_url")), r.json)
    uid = txn_of(bid)
    co = mock("/mock/state")["checkouts"].get(uid)
    t.check("gateway saw the checkout", co is not None, uid)
    t.check("booking is pending (txn_status 1)", b3.booking(bid).get("txn_status") == 1, b3.booking(bid))
    t.check("gateway accepted our signature", not mock("/mock/state")["errors"], mock("/mock/state")["errors"])
    t.check("redirect_url points to our callback", co and co["redirect_url"].endswith(f"/payment/callback/{uid}"), co)
    t.ctx["uid"], t.ctx["checkout"] = uid, co


@case("IPN: bad signature ignored, pending -> retry")
def ipn_checks(t):
    t.need("uid")
    uid = t.ctx["uid"]
    base = f"/payment/ipn/{uid}/"
    body = {"unique_txn_id": uid, "status_code": 3}
    r = pub("POST", base + "0" * 40, body=body)
    t.check("bad signature -> 200 IGNORED_UNVERIFIED", r.status == 200 and r.json.get("raw") == "IGNORED_UNVERIFIED", (r.status, r.json))
    r = pub("POST", base + ipn_sig(uid), body=body)
    t.check("gateway still pending -> 503 so it retries", r.status == 503, (r.status, r.json))
    t.check("booking still pending", b3.booking(t.ctx["paid_booking"]).get("txn_status") == 1)


@case("Callback after a successful payment marks the booking paid")
def callback(t):
    t.need("uid", "checkout")
    uid, bid = t.ctx["uid"], t.ctx["paid_booking"]
    mock("/mock/result", {"unique_txn_id": uid, "status_code": 3})
    r = pub("GET", t.ctx["checkout"]["redirect_url"], params={"data": "SOME+ENCRYPTED BLOB"})
    t.check("302 back to the frontend", r.status == 302 and "txn_status=3" in r.headers.get("Location", ""), (r.status, r.headers.get("Location")))
    t.check("booking is paid (txn_status 3)", b3.booking(bid).get("txn_status") == 3, b3.booking(bid).get("txn_status"))
    r = pub("POST", f"/payment/ipn/{uid}/{ipn_sig(uid)}", body={"unique_txn_id": uid, "status_code": 3})
    t.check("later IPN is idempotent (ALREADY_SUCCESS)", r.status == 200 and r.json.get("raw") == "ALREADY_SUCCESS", (r.status, r.json))
    r = pub("POST", "/initiate-payment", body={"booking_master_id": bid}, encrypted=True)
    t.check("second checkout refused: BOOKING_ALREADY_PAID", r.error == "BOOKING_ALREADY_PAID", r.json)


@case("Ticket PDF is issued and stored after payment")
def ticket_pdf(t):
    t.need("paid_booking")
    bid, link = t.ctx["paid_booking"], None
    for _ in range(60):
        link = (b3.booking(bid).get("trade_fair_ticket_booking_info") or {}).get("ticket_link")
        if link:
            break
        time.sleep(1)
    t.check("ticket_link stored on the booking", bool(link), b3.booking(bid))
    ups = mock("/mock/state")["uploads"]
    t.check("uploads on the mock S3 are real PDFs", ups and all(u["is_pdf"] and u["size"] > 1000 for u in ups), ups)
    t.ctx["ticket_link"] = link


@case("A failed payment never marks the booking paid")
def failed_payment(t):
    bid = b3.new_booking(adults=1, phone="01700000009").data.get("booking_master_id")
    pub("POST", "/initiate-payment", body={"booking_master_id": bid}, encrypted=True)
    uid = txn_of(bid)
    co = mock("/mock/state")["checkouts"].get(uid)
    mock("/mock/result", {"unique_txn_id": uid, "status_code": 4})
    pub("GET", co["redirect_url"], params={"data": "x"})
    t.check("txn_status is not 3 (paid)", b3.booking(bid).get("txn_status") != 3, b3.booking(bid).get("txn_status"))
