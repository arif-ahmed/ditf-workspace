"""Operator app: an agent sells tickets from their wallet; scanners admit them; role scoping. Uses the agent from 06."""
import os

from client import adm, enc, login, sql
from helpers import barcode_of, ean13
from runner import case

MID = "1502418a38c547ed90d55e2028fe3fc4"


def sell(token, adults=1, phone="01811110000"):
    body = ({"platform": 3, "txn_status": 3, "txn_amount": 1, "payment_channel": 1, "booking_request_id": os.urandom(16).hex(), "coupon_info": {},
                "merchant_info": {"merchant_id": MID},
                "trade_fair_ticket_booking_info": {"total_adult_quantity": adults, "total_child_quantity": 0, "customer_phone_number": phone, "customer_dial_code": "+88"},
                "bus_ticket_booking_info": {"total_seat": 0}})
    return adm("POST", "/booking-master", token=token, body=body, encrypted=True)


@case("Agent logs in and reads prices")
def agent_login(t):
    t.need("agent_phone", "agent_pin")
    r = login(t.ctx["agent_phone"], t.ctx["agent_pin"])
    t.check("agent logs in", bool(r.data.get("token")), r.json)
    t.ctx["tok_agent"] = r.data.get("token")
    r = adm("GET", "/booking-config", token=t.ctx["tok_agent"], params={"requested_data": enc({})})
    t.check("agent reads the booking config", (r.data.get("booking_configs") or [{}])[0].get("adult_price") == t.ctx.get("adult"), r.json)
    t.check("agent cannot move money -> 403", adm("POST", "/update-user-balance", token=t.ctx["tok_agent"], body={"user_id": t.ctx["agent_id"], "type": 1, "amount": 5}).status == 403)


@case("Agent sale: server price, paid from wallet, ledger debit, scannable ticket")
def agent_sale(t):
    t.need("tok_agent", "agent_id", "adult")
    before = float(sql(f"SELECT balance FROM booking_user_master WHERE id = '{t.ctx['agent_id']}'"))
    r = sell(t.ctx["tok_agent"])
    sale, bid = r.data, r.data.get("booking_master_id")
    t.check("sale accepted", bool(bid), r.json)
    row = sql(f"SELECT txn_amount || '|' || txn_status || '|' || platform || '|' || payment_channel || '|' || booked_by FROM booking_master WHERE id = '{bid}'")
    amount, rest = row.split("|", 1)
    t.check(f"price is the server's {t.ctx['adult']} (not the 1 sent), paid, mPOS, cash, booked by the agent",
            abs(float(amount) - t.ctx["adult"]) < .01 and rest == f"3|3|1|{t.ctx['agent_id']}", row)
    after = float(sql(f"SELECT balance FROM booking_user_master WHERE id = '{t.ctx['agent_id']}'"))
    t.check("wallet debited by the ticket price", abs(before - after - t.ctx["adult"]) < .01, (before, after))
    t.check("response balance equals the new wallet", abs(sale.get("balance", -1) - after) < .01, sale)
    led = sql(f"SELECT txn_type || '|' || display_text FROM user_transaction_ledger WHERE id = '{sale.get('txn_ledger_id')}'")
    t.check("ledger debit row with display text", led == "2|You have successfully booked a ticket.", led)
    t.check("one active, unused barcode exists", sql(f"SELECT count(*) FROM booking_barcode_details WHERE booking_master_id = '{bid}' AND is_active AND NOT trade_fair_ticket_barcode_valid") == "1")
    t.ctx["sold_booking"] = bid


@case("Agent sale edge cases: insufficient balance, wrong role, scoping")
def agent_edges(t):
    t.need("tok_agent", "agent_id", "sold_booking", "tok_scanner")
    n = sql(f"SELECT count(*) FROM booking_master WHERE booked_by = '{t.ctx['agent_id']}'")
    bal = sql(f"SELECT balance FROM booking_user_master WHERE id = '{t.ctx['agent_id']}'")
    r = sell(t.ctx["tok_agent"], adults=9)
    t.check("a sale the wallet can't cover -> 'Insufficient balance.'", r.error == "Insufficient balance.", r.json)
    t.check("...leaves no booking behind and the wallet untouched",
            sql(f"SELECT count(*) FROM booking_master WHERE booked_by = '{t.ctx['agent_id']}'") == n and sql(f"SELECT balance FROM booking_user_master WHERE id = '{t.ctx['agent_id']}'") == bal)
    t.check("scanners cannot sell -> 403", sell(t.ctx["tok_scanner"]).status == 403)
    t.check("agent reads their own sale", (adm("GET", f"/booking-master/{t.ctx['sold_booking']}", token=t.ctx["tok_agent"]).data.get("booking_master") or {}).get("id") == t.ctx["sold_booking"])
    other = sql("SELECT id FROM booking_master WHERE booked_by IS NULL OR booked_by <> '" + t.ctx["agent_id"] + "' ORDER BY created_date DESC LIMIT 1")
    t.check("...but not someone else's booking", adm("GET", f"/booking-master/{other}", token=t.ctx["tok_agent"]).error == "Booking master data not found")
    r = adm("GET", "/user-transaction-ledger", token=t.ctx["tok_agent"], params={"user_id": "someone-else"})
    t.check("ledger always shows the agent's own rows", {x["user_id"] for x in r.data.get("user_transaction_ledger", [])} <= {t.ctx["agent_id"]}, r.json)
    r = adm("GET", "/booking-master", token=t.ctx["tok_agent"], params={"requested_data": enc({"booked_by": "someone-else"})})
    t.check("booking history is always the agent's own", all(x.get("booked_by") == t.ctx["agent_id"] for x in r.data.get("booking_master", [])), r.json)
    t.check("agent reads own barcode (receipt)", adm("GET", "/booking-barcode-details", token=t.ctx["tok_agent"], params={"booking_master_id": t.ctx["sold_booking"]}).status == 200)
    t.check("...but no barcode lists -> 403", adm("GET", "/booking-barcode-details", token=t.ctx["tok_agent"]).status == 403)
    t.check("...nor other tickets", bool(adm("GET", "/booking-barcode-details", token=t.ctx["tok_agent"], params={"booking_master_id": other}).error))


@case("Scanner admits the agent's ticket once; receipt QR; scanner-scoped views")
def scanner(t):
    t.need("sold_booking", "tok_scanner", "tok_agent")
    bid, tok = t.ctx["sold_booking"], t.ctx["tok_scanner"]
    code = barcode_of(bid)
    req = lambda c, **k: adm("GET", "/scan-barcode", token=tok, params={"requested_data": enc({"barcode_string": c, **k})})
    r = req(code, scanned_by="someone-else")
    t.check("first scan admits the sold ticket", r.data.get("booking_master_id") == bid, r.json)
    row = sql(f"SELECT scanned_by || '|' || scanned_device FROM booking_barcode_details WHERE booking_master_id = '{bid}'")
    t.check("recorded under the logged-in scanner (not the name sent), device 'app'", row.endswith("|app") and "someone-else" not in row, row)
    t.check("scan logged once in ticket_scans", sql(f"SELECT count(*) FROM ticket_scans WHERE booking_master_id = '{bid}'") == "1")
    t.check("second scan -> 'Ticket already used'", req(code).error == "Ticket already used")
    t.check("12-digit and 13-digit forms are the same ticket", req(ean13(code)).error == "Ticket already used")
    t.check("agent cannot scan -> 403", adm("GET", "/scan-barcode", token=t.ctx["tok_agent"], params={"requested_data": enc({"barcode_string": code})}).status == 403)
    qr = sql(f"SELECT booking_qr_string FROM booking_barcode_details WHERE booking_master_id = '{bid}'")
    t.check("receipt QR resolves to the booking", adm("POST", "/scan-qr", token=tok, body={"qrcode_string": qr}).data.get("booking_master_id") == bid)
    t.check("unknown QR -> 'Invalid QR code.'", adm("POST", "/scan-qr", token=tok, body={"qrcode_string": "nope"}).error == "Invalid QR code.")
    t.check("scan-qr without login -> 401", adm("POST", "/scan-qr", body={"qrcode_string": qr}).status == 401)
    r = adm("POST", "/total-records", token=tok, body={"collection_name": "booking_barcode_details", "search_filter": {}, "date_filter": {},
                                                          "dropdown_filter": {"trade_fair_ticket_barcode_valid": True, "scanned_by": "anyone"}})
    mine = sql("SELECT count(*) FROM booking_barcode_details WHERE trade_fair_ticket_barcode_valid AND scanned_by = (SELECT id FROM booking_user_master WHERE phone_number = '1900007001')")
    t.check("scanner's counts only include their own scans", str(r.data.get("total_count")) == mine, (r.json, mine))
    r = adm("GET", "/booking-barcode-details", token=tok, params={"scanned_by": "anyone"})
    t.check("scanner scan history only their own", len({x["scanned_by"] for x in r.data.get("ticket_barcode_details_list", [])}) <= 1, r.json)
    t.check("scanner cannot list bookings -> 403", adm("GET", "/booking-master", token=tok, params={"requested_data": enc({})}).status == 403)
    r = adm("GET", "/booking-master", token=tok, params={"requested_data": enc({"id_filter": [bid]})})
    t.check("...but may read a booking by id", [x["id"] for x in r.data.get("booking_master", [])] == [bid], r.json)
