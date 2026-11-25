"""Remaining backend areas: version filter, request/crypto edge cases, bus seats + bus PDF, token tampering, dashboard numbers
cross-checked against the database, DB invariants, and the public gate scan with real scanner keys."""
import base64, os, re, shutil, subprocess, tempfile, threading, uuid

from client import ADMIN, MERCHANT_ID, PUBLIC, adm, call, enc, login, pub, sql
from helpers import b3, barcode_of, checkout, ean13, pay, unique_phone, wait
from runner import Skip, case

bk = b3()
GATE_KEYS = {}  # device name -> key, from scripts/dev.local.env (SCANNER_KEYS=gate-1:<key>,gate-2:<key>)
_env = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev.local.env")
if os.path.exists(_env):
    for line in open(_env, encoding="utf-8"):
        if line.strip().startswith("SCANNER_KEYS="):
            for part in line.split("=", 1)[1].strip().split(","):
                if ":" in part:
                    name, key = part.split(":", 1)
                    GATE_KEYS[name.strip()] = key.strip()


def booking(adults=1, seats=0, pick="DITF", drop="Gulshan", rid=None, phone=None, children=0):
    ph = phone or unique_phone()
    return pub("POST", "/booking-master", encrypted=True, body={
        "txn_amount": 1, "booking_request_id": rid or str(uuid.uuid4()), "platform": 2,
        "trade_fair_ticket_booking_info": {"total_adult_quantity": adults, "total_child_quantity": children, "customer_phone_number": ph, "customer_dial_code": "+88"},
        "bus_ticket_booking_info": {"total_seat": seats, "pickup_point": pick, "drop_point": drop, "customer_phone_number": ph, "customer_dial_code": "+88"},
        "coupon_info": {}, "merchant_info": {"merchant_id": MERCHANT_ID}})


def config():
    return pub("GET", "/booking-config", params={"requested_data": enc({"merchant_id": MERCHANT_ID})}).data["booking_configs"][0]


# ------------------------------------------------------------------------------------------------ request handling
@case("App version filter: older 'version' header -> 406 on both APIs; missing, current or non-numeric is fine")
def version_filter(t):
    for name, base in (("public", PUBLIC), ("admin", ADMIN)):
        r = call(base, "GET", "/health", headers={"version": "0"})
        t.check(f"{name}: version 0 -> 406 NOT_ACCEPTABLE", r.status == 406 and r.json.get("status") == "NOT_ACCEPTABLE", (r.status, r.json))
        t.check(f"{name}: version 1 accepted", call(base, "GET", "/health", headers={"version": "1"}).status == 200)
        t.check(f"{name}: non-numeric version ignored", call(base, "GET", "/health", headers={"version": "abc"}).status == 200)
        t.check(f"{name}: no header accepted", call(base, "GET", "/health").status == 200)
    t.check("the filter applies to business endpoints too (login with version 0 -> 406)", call(ADMIN, "POST", "/verify-login-pin", body={"phone_number": "1", "login_pin": "1"}, headers={"version": "0"}).status == 406)


@case("Booking request ids are unique; undecryptable bodies are a clean 400")
def request_edges(t):
    rid = str(uuid.uuid4())
    t.check("first booking with a request id is accepted", bool(booking(rid=rid).data.get("booking_master_id")))
    r = booking(rid=rid)
    t.check("same request id again -> 'Booking request id already exists'", r.error == "Booking request id already exists", r.json)
    t.check("one booking row for that request id", sql(f"SELECT count(*) FROM booking_master WHERE booking_request_id = '{rid}'") == "1")
    r = pub("POST", "/initiate-payment", body="not-valid-base64!!", headers={"Content-Type": "text/plain"})
    t.check("garbage encrypted body -> 400 (not 5xx)", r.status == 400, (r.status, r.json))
    t.check("valid base64 but not our ciphertext -> 400", call(PUBLIC, "POST", "/initiate-payment", body=base64.b64encode(b"x" * 32).decode(), headers={"Content-Type": "text/plain"}).status == 400)
    t.check("empty body -> 4xx", 400 <= pub("POST", "/initiate-payment", body={}).status < 500)
    t.check("garbage requested_data on an admin list -> 400", adm("GET", "/booking-master", token=login("1900003001").data["token"], params={"requested_data": "garbage"}).status == 400)


@case("Admin tokens: tampered signature, swapped user id and truncated token are refused")
def token_tamper(t):
    t.need("admin_token", "tok_generator")
    tok = t.ctx["admin_token"]
    payload, sig = tok.split(".")
    get = lambda token: adm("GET", "/booking-user-master", token=token, params={"user_role": 1}).status
    t.check("valid token works (200)", get(tok) == 200)
    t.check("reversed signature -> 401", get(payload + "." + sig[::-1]) == 401)
    t.check("signature of another user's token -> 401", get(payload + "." + t.ctx["tok_generator"].split(".")[1]) == 401)
    body = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    swapped = base64.urlsafe_b64encode(b"someone-else." + body.split(b".", 1)[1]).decode().rstrip("=")
    t.check("payload with another user id but the old signature -> 401", get(swapped + "." + sig) == 401)
    t.check("payload only (no signature) -> 401", get(payload) == 401)
    t.check("empty token -> 401", get("") == 401)


# ------------------------------------------------------------------------------------------------ bus tickets
@case("Bus seats: price from the route matrix, unknown route and unconfigured combos refused")
def bus_pricing(t):
    cfg = config()
    matrix, adult = cfg["seat_price_matrix"], cfg["adult_price"]
    price = matrix["DITF"]["Gulshan"]
    r = booking(adults=1, seats=2)
    b = bk.booking(r.data.get("booking_master_id"))
    t.check(f"1 adult + 2 seats DITF->Gulshan = {adult} + 2x{price}", abs(b.get("txn_amount", -1) - (adult + 2 * price)) < .01, b.get("txn_amount"))
    r = booking(adults=1, seats=1, pick="Mirpur", drop="Uttara")
    t.check(f"non-DITF route uses its own matrix price ({matrix['Mirpur']['Uttara']})", abs(bk.booking(r.data.get("booking_master_id")).get("txn_amount", -1) - (adult + matrix["Mirpur"]["Uttara"])) < .01, r.json)
    t.check("unknown stop -> INVALID_BUS_ROUTE", booking(seats=1, pick="Mars", drop="DITF").error == "INVALID_BUS_ROUTE")
    t.check("same pickup and drop -> INVALID_BUS_ROUTE", booking(seats=1, pick="DITF", drop="DITF").error == "INVALID_BUS_ROUTE")
    t.check("zero seats ignores the route entirely (fair ticket only)", abs(bk.booking(booking(adults=1, seats=0, pick="Mars", drop="Venus").data.get("booking_master_id")).get("txn_amount", -1) - adult) < .01)
    t.check("negative seats refused", bool(booking(seats=-1).error))


@case("Bus + fair booking paid: gateway charged the combined price, both PDFs issued and readable")
def bus_paid(t):
    cfg = config()
    price = cfg["seat_price_matrix"]["DITF"]["Gulshan"]
    ph = unique_phone()
    bid = booking(adults=1, seats=1, phone=ph).data.get("booking_master_id")
    uid, co, _ = checkout(bid)
    t.check("gateway asked for fair + bus amount", co and abs(co["amount"] - (cfg["adult_price"] + price)) < .01, co)
    from helpers import mock
    mock("/mock/result", {"unique_txn_id": uid, "status_code": 3})
    pub("GET", co["redirect_url"], params={"data": "x"})
    both = wait(lambda: (lambda b: b if (b.get("trade_fair_ticket_booking_info") or {}).get("ticket_link") and (b.get("bus_ticket_booking_info") or {}).get("ticket_link") else None)(bk.booking(bid)), 60)
    t.check("both ticket links stored", bool(both), bk.booking(bid))
    if not both:
        return
    fair, bus = both["trade_fair_ticket_booking_info"]["ticket_link"], both["bus_ticket_booking_info"]["ticket_link"]
    t.check("links are unguessable (random UUID in the file name)", all(len(os.path.basename(x)) > 40 for x in (fair, bus)), (fair, bus))
    t.check("both are different files", fair != bus)
    pdftotext = shutil.which("pdftotext")
    uploads = os.path.join(tempfile.gettempdir(), "ditf-mock-uploads")
    if not pdftotext or not os.path.isdir(uploads):
        t.check("PDF text check skipped: pdftotext or the mock upload folder not available", True)
        return
    text = lambda link: subprocess.run([pdftotext, "-layout", os.path.join(uploads, os.path.basename(link)), "-"], capture_output=True, text=True).stdout
    number = bk.booking(bid).get("booking_number")
    ft, bt = text(fair), text(bus)
    t.check("fair PDF carries the ticket number", number in ft, ft[:300])
    t.check("bus PDF carries the ticket number and both stops", number in bt and "DITF" in bt and "Gulshan" in bt, bt[:300])


@case("Server enforces max_ticket_quantity and max_seat_count from the booking config", known_issue="the limits (10 tickets, 4 seats) are only sent to the client; the server accepts 11 adults and 5 seats")
def booking_limits(t):
    cfg = config()
    over_t, over_s = cfg["max_ticket_quantity"] + 1, cfg["max_seat_count"] + 1
    t.check(f"{over_t} adults is refused", bool(booking(adults=over_t).error))
    t.check(f"{over_s} seats is refused", bool(booking(adults=1, seats=over_s).error))
    t.check("the maximum itself is accepted", not booking(adults=cfg["max_ticket_quantity"]).error)


# ------------------------------------------------------------------------------------------------ dashboard numbers vs database
@case("Dashboard numbers equal what the database says")
def dashboard_vs_db(t):
    t.need("admin_token")
    tok = t.ctx["admin_token"]
    d = adm("POST", "/manual-ticket-total-count", token=tok, body={}).data
    exp = sql("SELECT coalesce(sum(total_no_of_tickets),0) || '|' || coalesce(sum(total_no_of_tickets) FILTER (WHERE is_active),0) || '|' || coalesce(sum(total_no_of_tickets) FILTER (WHERE is_active AND ticket_type=1),0)"
              " || '|' || coalesce(sum(total_no_of_tickets) FILTER (WHERE is_active AND ticket_type=2),0) || '|' || coalesce(sum(total_no_of_tickets) FILTER (WHERE NOT is_active),0) FROM user_ticket_generator")
    got = "|".join(str(int(d.get(k, -1))) for k in ("total_tickets", "total_enabled_tickets", "total_enabled_adults_tickets", "total_enabled_children_tickets", "total_disabled_tickets"))
    t.check("manual_ticket_total_count = sums over user_ticket_generator", got == exp, (got, exp))
    t.check("enabled + disabled = total", d["total_enabled_tickets"] + d["total_disabled_tickets"] == d["total_tickets"], d)
    t.check("total_generated_ticket = bulk barcodes stored", adm("POST", "/total-generated-ticket", token=tok, body={}).data.get("total_records") == int(sql("SELECT count(*) FROM booking_barcode_details WHERE user_ticket_generator_id IS NOT NULL")))
    b = adm("POST", "/booking-agent-balance-count", token=tok, body={}).data
    t.check("agent balance total = sum of active agents' balances", abs(float(b.get("total_balance")) - float(sql("SELECT coalesce(sum(balance),0) FROM booking_user_master WHERE user_role = 1 AND is_active"))) < .01, b)
    t.check("agent credited total = sum of top-ups in the ledger", abs(float(b.get("total_credited_amount")) - float(sql("SELECT coalesce(sum(amount),0) FROM user_transaction_ledger WHERE txn_type = 1"))) < .01, b)
    cnt = lambda coll, f: adm("POST", "/total-records", token=tok, body={"collection_name": coll, "dropdown_filter": f, "search_filter": {}, "date_filter": {}}).data.get("total_count")
    t.check("total_records(users, role 1) = active agents", cnt("booking_user_master", {"user_role": 1}) == int(sql("SELECT count(*) FROM booking_user_master WHERE user_role = 1 AND is_active")))
    t.check("total_records(role list [1,4]) counts both roles", cnt("booking_user_master", {"user_role": [1, 4]}) == int(sql("SELECT count(*) FROM booking_user_master WHERE user_role IN (1,4) AND is_active")))
    t.check("total_records(scanned tickets) = barcodes marked used", cnt("booking_barcode_details", {"trade_fair_ticket_barcode_valid": True}) == int(sql("SELECT count(*) FROM booking_barcode_details WHERE trade_fair_ticket_barcode_valid")))
    t.check("number filters accept text ('1' = 1)", cnt("booking_user_master", {"user_role": "1"}) == cnt("booking_user_master", {"user_role": 1}))


# ------------------------------------------------------------------------------------------------ database invariants
@case("Database invariants: schema version, unique barcodes and indexes, partition pruning, no orphans")
def db_invariants(t):
    t.check("schema_version holds exactly version 2", sql("SELECT string_agg(version::text, ',') FROM schema_version") == "2")
    t.check("no duplicate barcode numbers", sql("SELECT count(*) - count(DISTINCT trade_fair_ticket_barcode) FROM booking_barcode_details") == "0")
    t.check("unique barcode index exists", sql("SELECT count(*) FROM pg_indexes WHERE indexname = 'booking_barcode_fair_uq'") == "1")
    plan = sql("SET enable_seqscan = off; EXPLAIN SELECT * FROM booking_barcode_details WHERE trade_fair_ticket_barcode = '200000000000' AND is_active")
    t.check("gate lookup can use that index", "booking_barcode_fair_uq" in plan, plan)
    today = sql("SELECT to_char(now() AT TIME ZONE 'Asia/Dhaka', 'YYYYMMDD')")
    plan = sql("EXPLAIN SELECT count(*) FROM ticket_scans WHERE scanned_date BETWEEN extract(epoch FROM now())::bigint - 60 AND extract(epoch FROM now())::bigint")
    t.check("a one-minute scan total only reads today's (Dhaka) partition",
            set(re.findall(r"on (ticket_scans_\w+)", plan)) == {"ticket_scans_" + today} or "ticket_scans_" + today not in plan and not plan, plan)
    t.check("no user has a negative wallet balance", sql("SELECT count(*) FROM booking_user_master WHERE balance < 0") == "0")
    t.check("ledger debits never exceed what was credited, per agent", sql("SELECT count(*) FROM (SELECT user_id, sum(CASE WHEN txn_type = 1 THEN amount ELSE -amount END) s FROM user_transaction_ledger GROUP BY user_id HAVING sum(CASE WHEN txn_type = 1 THEN amount ELSE -amount END) < -0.01) x") == "0")


# ------------------------------------------------------------------------------------------------ public gate scan with scanner keys
def _gate(t):
    if len(GATE_KEYS) < 2:
        raise Skip("no SCANNER_KEYS (gate-1:<key>,gate-2:<key>) in scripts/dev.local.env, or the public API was not started with them")


def gscan(code, key, operator="Rahim"):
    return pub("GET", "/scan-barcode", params={"requested_data": enc({"barcode_string": code, "scanned_by": operator})}, headers={"X-Scanner-Key": key} if key else None)


@case("Public gate scan with a device key: admits once, records device and operator, refuses everything else")
def gate_keys(t):
    _gate(t)
    (n1, k1), (n2, k2) = list(GATE_KEYS.items())[:2]
    unpaid = bk.new_booking(adults=1).data.get("booking_master_id")
    t.check("unpaid ticket -> 'Ticket not paid'", gscan(ean13(barcode_of(unpaid)), k1).error == "Ticket not paid")
    b = bk.new_booking(adults=2, phone=unique_phone()).data.get("booking_master_id")
    pay(b)
    code = ean13(barcode_of(b))
    t.check("no key -> 401", gscan(code, None).status == 401)
    t.check("wrong key -> 401", gscan(code, "x" * 40).status == 401)
    t.check("a key one character off -> 401", gscan(code, k1[:-1] + ("0" if k1[-1] != "0" else "1")).status == 401)
    r = gscan(code, k1, operator="Rahim")
    t.check("first scan admits with the head count", r.data.get("message") == "Barcode verified successfully" and r.data.get("total_adult_quantity") == 2, r.json)
    row = sql(f"SELECT scanned_by || '|' || scanned_device || '|' || trade_fair_ticket_barcode_valid FROM booking_barcode_details WHERE booking_master_id = '{b}'")
    t.check(f"recorded under operator 'Rahim' and device '{n1}'", row == f"Rahim|{n1}|true", row)
    t.check("one scan logged with adults=2", sql(f"SELECT count(*) || '|' || max(adults) FROM ticket_scans WHERE booking_master_id = '{b}'") == "1|2")
    t.check("second scan (other device key) -> 'Ticket already used'", gscan(code, k2).error == "Ticket already used")
    b2 = bk.new_booking(adults=1, phone=unique_phone()).data.get("booking_master_id")
    pay(b2)
    r = gscan(barcode_of(b2), k2, operator="")
    t.check(f"12-digit form from the second device ({n2}) admits; empty operator falls back to the device name", r.data.get("booking_master_id") == b2
            and sql(f"SELECT scanned_by || '|' || scanned_device FROM booking_barcode_details WHERE booking_master_id = '{b2}'") == f"{n2}|{n2}", r.json)
    t.check("wrong check digit -> 'Invalid barcode string'", gscan(code[:12] + str((int(code[12]) + 1) % 10), k1).error == "Invalid barcode string")


@case("Public gate scan: 6 simultaneous scans of one ticket admit exactly one")
def gate_keys_concurrent(t):
    _gate(t)
    k1 = list(GATE_KEYS.values())[0]
    b = bk.new_booking(adults=1, phone=unique_phone()).data.get("booking_master_id")
    pay(b)
    code = ean13(barcode_of(b))
    out = []
    ths = [threading.Thread(target=lambda n=n: out.append(gscan(code, k1, operator=f"gate{n}").json)) for n in range(6)]
    [x.start() for x in ths]
    [x.join() for x in ths]
    admitted = [o for o in out if (o.get("data") or {}).get("message") == "Barcode verified successfully"]
    t.check("exactly one admitted, five 'Ticket already used'", len(admitted) == 1 and sum(o.get("error") == ["Ticket already used"] for o in out) == 5, out)
    t.check("one ticket_scans row", sql(f"SELECT count(*) FROM ticket_scans WHERE booking_master_id = '{b}'") == "1")
