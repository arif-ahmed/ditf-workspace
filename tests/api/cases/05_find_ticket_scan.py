"""Find-my-ticket (public API) and gate scanning (admin API, scanner login). Uses the booking paid in 04."""
import importlib

from client import adm, enc, pub, sql
from runner import case

b3 = importlib.import_module("cases.03_booking_public")


def ean13(d12):
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12))
    return d12 + str((10 - total % 10) % 10)


def scan(token, code):
    return adm("GET", "/scan-barcode", token=token, params={"requested_data": enc({"barcode_string": code})})


@case("find-ticket: phone + ticket number returns the ticket links")
def find_ok(t):
    t.need("paid_booking")
    number = b3.booking(t.ctx["paid_booking"]).get("booking_number")
    r = pub("POST", "/find-ticket", body={"phone_number": b3.PHONE, "ticket_number": number}, encrypted=True)
    t.check("booking found", r.data.get("booking_master_id") == t.ctx["paid_booking"], r.json)
    t.check("ticket link returned", bool(r.data.get("trade_fair_ticket_link")), r.data)


@case("find-ticket: bad input refused")
def find_bad(t):
    t.check("malformed phone -> INVALID_PHONE_NUMBER", pub("POST", "/find-ticket", body={"phone_number": "12345", "ticket_number": "1"}, encrypted=True).error == "INVALID_PHONE_NUMBER")
    t.need("unpaid_booking")
    number = b3.booking(t.ctx["unpaid_booking"]).get("booking_number")
    t.check("unpaid booking -> PAYMENT_NOT_COMPLETED", pub("POST", "/find-ticket", body={"phone_number": b3.PHONE, "ticket_number": number}, encrypted=True).error == "PAYMENT_NOT_COMPLETED")


@case("Gate scan: unpaid ticket refused")
def scan_unpaid(t):
    t.need("tok_scanner", "unpaid_booking")
    code = sql(f"SELECT trade_fair_ticket_barcode FROM booking_barcode_details WHERE booking_master_id = '{t.ctx['unpaid_booking']}' LIMIT 1")
    r = scan(t.ctx["tok_scanner"], ean13(code))
    t.check("'Ticket not paid'", r.error == "Ticket not paid", r.json)


@case("Gate scan: wrong check digit refused; paid ticket scans once only")
def scan_paid(t):
    t.need("tok_scanner", "paid_booking")
    code = ean13(sql(f"SELECT trade_fair_ticket_barcode FROM booking_barcode_details WHERE booking_master_id = '{t.ctx['paid_booking']}' LIMIT 1"))
    bad = code[:12] + str((int(code[12]) + 1) % 10)
    t.check("wrong check digit -> 'Invalid barcode string'", scan(t.ctx["tok_scanner"], bad).error == "Invalid barcode string")
    t.check("scan without a login -> 401", adm("GET", "/scan-barcode", params={"requested_data": enc({"barcode_string": code})}).status == 401)
    first, second = scan(t.ctx["tok_scanner"], code), scan(t.ctx["tok_scanner"], code)
    t.check("first scan succeeds", first.status == 200 and not first.error, first.json)
    t.check("second scan of the same ticket is refused", bool(second.error), second.json)
    t.check("ticket is marked used in the database",
            sql(f"SELECT trade_fair_ticket_barcode_valid FROM booking_barcode_details WHERE booking_master_id = '{t.ctx['paid_booking']}' LIMIT 1") == "t")
