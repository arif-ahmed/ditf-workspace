"""Referral codes: admin creates, public checks, leader board counts paid bookings per code."""
import random, time

from client import adm, pub, sql
from runner import case


def phone():
    return "017" + str(random.randint(10000000, 99999999))


@case("Referral codes: create gets the next sequential code; duplicates and bad input refused")
def create(t):
    t.need("admin_token")
    tok = t.ctx["admin_token"]
    ph = phone()
    r = adm("POST", "/user-referral-codes", token=tok, body={"first_name": "AUTOTEST", "phone_number": ph})
    rid = r.data.get("id")
    t.check("created", bool(rid), r.json)
    code = sql(f"SELECT referral_code FROM user_referral_codes WHERE id = '{rid}'")
    t.check("code is numeric, zero-padded", code.isdigit() and len(code) >= 3, code)
    r2 = adm("POST", "/user-referral-codes", token=tok, body={"first_name": "AUTOTEST", "phone_number": phone()})
    code2 = sql(f"SELECT referral_code FROM user_referral_codes WHERE id = '{r2.data.get('id')}'")
    t.check("next code is previous + 1", code2.isdigit() and int(code2) == int(code) + 1, (code, code2))
    t.check("missing phone refused", adm("POST", "/user-referral-codes", token=tok, body={"first_name": "x"}).status in (400, 200) and
            bool(adm("POST", "/user-referral-codes", token=tok, body={"first_name": "x"}).error))
    t.check("generator (8) cannot create -> 403", adm("POST", "/user-referral-codes", token=t.ctx["tok_generator"], body={"first_name": "x", "phone_number": phone()}).status == 403)
    t.ctx["ref_code"], t.ctx["ref_id"] = code, rid


@case("Referral lookup (admin) and check-referral-code (public)")
def lookup(t):
    t.need("admin_token", "ref_code")
    r = adm("GET", "/user-referral-codes", token=t.ctx["admin_token"], params={"user_referral_code": t.ctx["ref_code"]})
    t.check("lookup finds the owner", [x["first_name"] for x in r.data.get("user_referral_codes", [])] == ["AUTOTEST"], r.json)
    r = pub("GET", "/check-referral-code", params={"referral_code": t.ctx["ref_code"]})
    t.check("public check accepts a valid code", r.status == 200 and not r.error, r.json)
    t.check("public check without a code -> BAD_REQUEST", pub("GET", "/check-referral-code", params={"referral_code": ""}).error == "BAD_REQUEST")
    r = pub("GET", "/check-referral-code", params={"referral_code": "99999999"})
    t.check("unknown code is refused", bool(r.error) or r.data.get("is_referral_code_valid") is False, r.json)
    t.check("lookup of unknown code finds nothing", not adm("GET", "/user-referral-codes", token=t.ctx["admin_token"], params={"user_referral_code": "99999999"}).data.get("user_referral_codes"))


@case("Referral leader board counts paid bookings by code, highest first")
def board(t):
    t.need("tok_generator", "ref_code")
    code = t.ctx["ref_code"]
    now = int(time.time())
    sql(f"INSERT INTO booking_master (id, is_active, txn_status, user_referral_code, created_date) "
        f"SELECT 'atref{now}' || i, true, 3, '{code}', {now} FROM generate_series(1, 3) i")
    sql(f"INSERT INTO booking_master (id, is_active, txn_status, user_referral_code, created_date) VALUES ('atrefunpaid{now}', true, 1, '{code}', {now})")
    r = adm("POST", "/referral-details", token=t.ctx["tok_generator"], body={"start_date": now - 60, "end_date": now + 60})
    rows = r.data.get("referral_details") or []
    mine = [x for x in rows if x["referral_code"] == code]
    t.check("our code appears with 3 (the unpaid booking is not counted)", mine and str(mine[0]["total_referral_code_booking"]) == "3", rows)
    counts = [int(x["total_referral_code_booking"]) for x in rows]
    t.check("sorted highest first", counts == sorted(counts, reverse=True), counts)
    r = adm("POST", "/referral-details", token=t.ctx["tok_generator"], body={"start_date": now - 7200, "end_date": now - 3600})
    t.check("empty window finds nothing for our code", code not in str(r.data.get("referral_details")), r.json)
    t.check("no token -> 401", adm("POST", "/referral-details", body={"start_date": 1, "end_date": 2}).status == 401)
    sql(f"DELETE FROM booking_master WHERE id LIKE 'atref%{now}%' OR id = 'atrefunpaid{now}'")
