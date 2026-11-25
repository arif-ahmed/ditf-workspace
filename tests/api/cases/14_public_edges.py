"""Public API edge cases: payment races/retries/failures, find-ticket lockout, gate scan concurrency."""
import threading

from client import adm, enc, mock, pub, sql
from helpers import b3, barcode_of, checkout, ean13, ipn_sig, pay, txn_of, unique_phone, wait
from runner import case

bk = b3()


def ipn(uid, sig=None, status=3):
    return pub("POST", f"/payment/ipn/{uid}/{sig or ipn_sig(uid)}", body={"unique_txn_id": uid, "status_code": status})


def new(phone, adults=1):
    return bk.new_booking(adults=adults, phone=phone).data.get("booking_master_id")


@case("Cancelled payment, retry creates a new attempt, old attempts cannot disturb it")
def retry(t):
    b = new("01900000010")
    uid_a, co_a, _ = checkout(b)
    mock("/mock/result", {"unique_txn_id": uid_a, "status_code": 4})
    r = pub("GET", co_a["redirect_url"], params={"data": "x"})
    t.check("cancelled payment stored as txn_status 4 and browser told so", bk.booking(b).get("txn_status") == 4 and "txn_status=4" in r.headers.get("Location", ""), (bk.booking(b).get("txn_status"), r.headers))
    uid_b, _, _ = checkout(b)
    row = sql(f"SELECT txn_status || '|' || payment_attempt_ids::text FROM booking_master WHERE id = '{b}'")
    t.check("retry makes a second attempt and goes back to pending", row.startswith("1|") and uid_a in row and uid_b in row and row.index(uid_a) < row.index(uid_b), row)
    r = ipn(uid_a)
    t.check("late failure IPN of the old attempt -> ALREADY_PROCESSED, new attempt untouched", r.json.get("raw") == "ALREADY_PROCESSED" and bk.booking(b).get("txn_status") == 1, (r.status, r.json))
    mock("/mock/result", {"unique_txn_id": uid_b, "status_code": 3})
    r = ipn(uid_b)
    t.check("IPN alone (browser never returned) settles the payment", r.json.get("raw") == "SUCCESS" and sql(f"SELECT payment_settled_by FROM booking_master WHERE id = '{b}'") == "IPN", (r.json,))
    mock("/mock/result", {"unique_txn_id": uid_a, "status_code": 3})
    r = ipn(uid_a)
    t.check("late success of the old attempt on a paid booking -> ALREADY_SUCCESS (no double settle)", r.json.get("raw") == "ALREADY_SUCCESS" and txn_of(b) == uid_b, (r.json, txn_of(b)))


@case("Concurrent IPNs and callback settle exactly once")
def concurrent_settle(t):
    b = new("01900000011")
    uid, co, _ = checkout(b)
    mock("/mock/result", {"unique_txn_id": uid, "status_code": 3})
    out = []
    ths = [threading.Thread(target=lambda: out.append(ipn(uid).json.get("raw"))) for _ in range(3)] + \
          [threading.Thread(target=lambda: pub("GET", co["redirect_url"], params={"data": "x"}))]
    [x.start() for x in ths]
    [x.join() for x in ths]
    t.check("booking paid once", bk.booking(b).get("txn_status") == 3, bk.booking(b).get("txn_status"))
    t.check("at most one IPN says SUCCESS, the rest ALREADY_SUCCESS", out.count("SUCCESS") <= 1 and all(o in ("SUCCESS", "ALREADY_SUCCESS") for o in out), out)
    t.check("exactly one ticket barcode exists", sql(f"SELECT count(*) FROM booking_barcode_details WHERE booking_master_id = '{b}'") == "1")


@case("Gateway failures: initiate error is undone, revoked token refreshed, unknown IPN, success with wrong amount")
def gateway_faults(t):
    b = new("01900000012", adults=3)
    mock("/mock/fail_initiate", {"value": True})
    try:
        r = pub("POST", "/initiate-payment", body={"booking_master_id": b}, encrypted=True)
    finally:
        mock("/mock/fail_initiate", {"value": False})
    t.check("failed initiate -> PAYMENT_GATEWAY_ERROR", r.error == "PAYMENT_GATEWAY_ERROR", r.json)
    t.check("...and 'pending' is undone", bk.booking(b).get("txn_status") is None, bk.booking(b).get("txn_status"))
    mock("/mock/revoke", {})
    r = pub("POST", "/initiate-payment", body={"booking_master_id": b}, encrypted=True)
    t.check("revoked gateway token is refreshed and the call retried", "webview_url" in r.data, r.json)
    r = ipn("DITF0000000000000abcdef", sig=ipn_sig("DITF0000000000000abcdef"))
    t.check("IPN for an unknown transaction -> UNKNOWN_TXN", r.status == 200 and r.json.get("raw") == "UNKNOWN_TXN", (r.status, r.json))
    uid = txn_of(b)
    mock("/mock/result", {"unique_txn_id": uid, "status_code": 3, "amount": "1.0"})
    co = mock("/mock/state")["checkouts"][uid]
    r = pub("GET", co["redirect_url"], params={"data": "x"})
    t.check("success reported with the wrong amount is NOT marked paid", bk.booking(b).get("txn_status") == 1, bk.booking(b).get("txn_status"))
    t.check("no signature mismatches seen by the mock gateway", not mock("/mock/state")["errors"], mock("/mock/state")["errors"])
    r = pub("GET", f"/payment/callback/unknown-txn-id", params={"data": "x"})
    t.check("callback for an unknown transaction does not crash (no 5xx)", r.status < 500, (r.status, r.json))


@case("Payment method is passed to the gateway; amount is the server's")
def method_and_amount(t):
    b = new("01900000013")
    uid, co, r = checkout(b, method="bkash")
    t.check("payment_method forwarded", co and co.get("payment_method") == "bkash", co)
    t.check("gateway asked for the server price", co and co.get("amount") == float(bk.booking(b).get("txn_amount")), (co, bk.booking(b).get("txn_amount")))
    t.check("ipn_redirect_url carries a signature for this transaction", co and co["ipn_redirect_url"].endswith(f"/payment/ipn/{uid}/{ipn_sig(uid)}"), co)
    t.check("initiate for an unknown booking is refused", bool(pub("POST", "/initiate-payment", body={"booking_master_id": "nope"}, encrypted=True).error))


@case("find-ticket: by payment reference, any phone format, lockout after 5 wrong guesses")
def find_ticket_edges(t):
    ph = unique_phone()  # limiter keys include the phone, so fixed numbers would stay locked across reruns
    b = new(ph)
    pay(b)
    wait(lambda: (bk.booking(b).get("trade_fair_ticket_booking_info") or {}).get("ticket_link"), 60)
    number = bk.booking(b).get("booking_number")
    ref = sql(f"SELECT txn_ref_no FROM booking_master WHERE id = '{b}'")
    find = lambda phone, **k: pub("POST", "/find-ticket", body={"phone_number": phone, **k}, encrypted=True)
    t.check("by payment ref, phone with +88 prefix, ref in lower case", find("+88" + ph, payment_ref=ref.lower()).data.get("booking_master_id") == b, find("+88" + ph, payment_ref=ref.lower()).json)
    t.check("wrong phone -> TICKET_NOT_FOUND", find(unique_phone(), ticket_number=number).error == "TICKET_NOT_FOUND")
    sql(f"UPDATE booking_master SET trade_fair_ticket_booking_info = trade_fair_ticket_booking_info - 'ticket_link' WHERE id = '{b}'")
    t.check("missing ticket PDF is regenerated on lookup", (find(ph, ticket_number=number).data.get("trade_fair_ticket_link") or "").startswith("http"), find(ph, ticket_number=number).json)
    misses = [find(unique_phone(), ticket_number=number).error for n in range(5)]  # the wrong phone above was already miss no. 1
    t.check("wrong phones for one ticket number: TICKET_NOT_FOUND, locked after 5 misses in total",
            misses[:4] == ["TICKET_NOT_FOUND"] * 4 and misses[4] == "TOO_MANY_ATTEMPTS", misses)
    t.check("then even the right phone is locked: TOO_MANY_ATTEMPTS", find(ph, ticket_number=number).error == "TOO_MANY_ATTEMPTS")
    t.check("neither phone nor reference -> error", bool(find(ph).error))


@case("Gate: used ticket cannot be looked up; 6 simultaneous scans admit exactly one; 12-digit form works")
def gate(t):
    t.need("tok_scanner")
    b = new("01900000015", adults=2)
    pay(b)
    wait(lambda: barcode_of(b), 20)
    code = barcode_of(b)
    scan = lambda c: adm("GET", "/scan-barcode", token=t.ctx["tok_scanner"], params={"requested_data": enc({"barcode_string": c})})
    out = []
    ths = [threading.Thread(target=lambda: out.append(scan(ean13(code)).json)) for _ in range(6)]
    [x.start() for x in ths]
    [x.join() for x in ths]
    admitted = [o for o in out if (o.get("data") or {}).get("message") == "Barcode verified successfully"]
    t.check("exactly one of 6 simultaneous scans admits", len(admitted) == 1 and sum(o.get("error") == ["Ticket already used"] for o in out) == 5, out)
    t.check("admission reports the head count", admitted and admitted[0]["data"].get("total_adult_quantity") == 2, admitted)
    t.check("find-ticket refuses a used ticket -> TICKET_ALREADY_USED",
            pub("POST", "/find-ticket", body={"phone_number": "01900000015", "ticket_number": bk.booking(b).get("booking_number")}, encrypted=True).error == "TICKET_ALREADY_USED")
    b2 = new("01900000016")
    pay(b2)
    wait(lambda: barcode_of(b2), 20)
    r = scan(barcode_of(b2))
    t.check("the 12-digit form (no check digit) is accepted", (r.data or {}).get("booking_master_id") == b2, r.json)
    t.check("a barcode of the wrong kind/prefix is refused", scan("1" + code[1:12]).error == "Invalid barcode string")
    r = pub("GET", "/scan-barcode", params={"requested_data": enc({"barcode_string": code})})
    t.check("public gate-scan endpoint without a scanner key -> 401", r.status == 401, (r.status, r.json))
    r = pub("GET", "/scan-barcode", params={"requested_data": enc({"barcode_string": code})}, headers={"X-Scanner-Key": "wrong-key"})
    t.check("...and with a wrong key -> 401", r.status == 401, r.status)


@case("Booking read/list edge cases and ticket report")
def booking_reads(t):
    t.need("paid_booking")
    t.check("unknown booking id is an error, not a 500", pub("GET", "/booking-master/does-not-exist").status < 500)
    t.check("the public API has no booking list (GET /booking-master -> 405)", pub("GET", "/booking-master", params={"requested_data": "garbage"}).status == 405)
    r = pub("POST", "/ticket-booking-report", body={"txn_id": "x", "booking_master_id": t.ctx["paid_booking"], "report_type": 1})
    t.check("ticket report for a paid booking answers without error", r.status == 200 and not r.error, r.json)
    t.check("report for unknown booking is refused", bool(pub("POST", "/ticket-booking-report", body={"txn_id": "x", "booking_master_id": "nope", "report_type": 1}).error))
    t.check("PUT /booking-master is gone", pub("PUT", "/booking-master", body={"id": "x", "txn_status": 3}).status in (404, 405))
    t.check("/transactions is gone", pub("GET", "/transactions").status == 404)
