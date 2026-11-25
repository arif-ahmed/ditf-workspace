"""Coupon admin: permissions, create validation, edit semantics, delete; and that bookings honour an edited coupon at once."""
import random, time

from client import adm, pub, sql
from helpers import b3
from runner import case

CODE = "AT" + str(random.randint(10000, 99999))


@case("Coupons: only admins edit; admin staff may read; generator may not")
def permissions(t):
    t.need("tok_staff", "tok_generator")
    body = {"code": "X" + CODE, "discount_type": 1, "discount_value": 5}
    t.check("admin staff (5) cannot create -> 403", adm("POST", "/coupons", token=t.ctx["tok_staff"], body=body).status == 403)
    t.check("admin staff (5) can list", adm("GET", "/coupons", token=t.ctx["tok_staff"], params={"limit": 5}).status == 200)
    t.check("generator (8) cannot list -> 403", adm("GET", "/coupons", token=t.ctx["tok_generator"]).status == 403)
    t.check("no token -> 401", adm("GET", "/coupons").status == 401)
    t.check("admin staff cannot delete -> 403", adm("DELETE", "/coupons/anything", token=t.ctx["tok_staff"]).status == 403)


@case("Coupon create: valid, then every validation error")
def create(t):
    t.need("admin_token")
    tok, now = t.ctx["admin_token"], int(time.time())
    r = adm("POST", "/coupons", token=tok, body={"code": f" {CODE} ", "description": "autotest", "discount_type": 1, "discount_value": 15,
                                                 "max_discount": 50, "min_amount": 0, "start_date": now - 60, "end_date": now + 86400})
    cid = r.data.get("id")
    t.check("created", r.data.get("message") == "COUPON_SAVED_SUCCESSFULLY" and cid, r.json)
    row = sql(f"SELECT code || '|' || coalesce(min_amount::text,'none') || '|' || max_discount || '|' || is_active FROM coupons WHERE id = '{cid}'")
    t.check("code trimmed, min_amount 0 stored as none, cap kept, active", row == f"{CODE}|none|50.00|t" or row.startswith(f"{CODE}|none|50"), row)
    t.ctx["coupon_id"] = cid
    bad = [("same code in another case", {"code": CODE.lower(), "discount_type": 2, "discount_value": 5}, "COUPON_CODE_ALREADY_EXISTS"),
           ("code with a space", {"code": "FAIR 15", "discount_type": 1, "discount_value": 5}, "INVALID_COUPON_CODE_FORMAT"),
           ("missing code", {"discount_type": 1, "discount_value": 5}, "INVALID_COUPON_CODE_FORMAT"),
           ("unknown discount type", {"code": "T3" + CODE, "discount_type": 3, "discount_value": 5}, "INVALID_DISCOUNT_TYPE"),
           ("percentage over 100", {"code": "T4" + CODE, "discount_type": 1, "discount_value": 101}, "INVALID_DISCOUNT_VALUE"),
           ("zero discount", {"code": "T5" + CODE, "discount_type": 2, "discount_value": 0}, "INVALID_DISCOUNT_VALUE"),
           ("negative cap", {"code": "T6" + CODE, "discount_type": 1, "discount_value": 5, "max_discount": -1}, "INVALID_MAX_DISCOUNT"),
           ("negative minimum", {"code": "T7" + CODE, "discount_type": 1, "discount_value": 5, "min_amount": -1}, "INVALID_MIN_AMOUNT"),
           ("end before start", {"code": "T8" + CODE, "discount_type": 1, "discount_value": 5, "start_date": now, "end_date": now - 1}, "INVALID_COUPON_DATES")]
    for name, body, err in bad:
        t.check(name + " -> " + err, adm("POST", "/coupons", token=tok, body=body).error == err)
    t.check("none of the rejected coupons were stored", sql(f"SELECT count(*) FROM coupons WHERE code LIKE 'T_{CODE}'") == "0")


@case("Coupon is honoured by the public API, including date window and on/off switch")
def usable(t):
    t.need("admin_token", "coupon_id", "adult")
    pr = lambda: pub("GET", "/check-coupon-code", params={"coupon_code": CODE.lower()})
    t.check("active coupon validates in any case", pr().data.get("is_coupon_code_valid") is True, pr().json)
    r = b3().new_booking(adults=2, coupon={"code": CODE})
    gross = 2 * t.ctx["adult"]
    t.check(f"booking price {gross} - min(15%, 50)", abs(b3().booking(r.data.get("booking_master_id")).get("txn_amount", -1) - (gross - min(gross * .15, 50))) < .01, r.json)
    adm("PUT", "/coupons", token=t.ctx["admin_token"], body={"id": t.ctx["coupon_id"], "code": CODE, "discount_type": 1, "discount_value": 15, "is_active": False})
    t.check("switched off -> INVALID_COUPON_CODE at check", pr().error == "INVALID_COUPON_CODE")
    t.check("switched off -> booking refused", b3().new_booking(coupon={"code": CODE}).error == "INVALID_COUPON_CODE")
    now = int(time.time())
    adm("PUT", "/coupons", token=t.ctx["admin_token"], body={"id": t.ctx["coupon_id"], "code": CODE, "discount_type": 1, "discount_value": 15, "start_date": now + 3600})
    t.check("not started yet -> refused", pr().error == "INVALID_COUPON_CODE")
    adm("PUT", "/coupons", token=t.ctx["admin_token"], body={"id": t.ctx["coupon_id"], "code": CODE, "discount_type": 1, "discount_value": 15, "end_date": now - 3600})
    t.check("already ended -> refused", pr().error == "INVALID_COUPON_CODE")
    adm("PUT", "/coupons", token=t.ctx["admin_token"], body={"id": t.ctx["coupon_id"], "code": CODE, "discount_type": 2, "discount_value": 20, "min_amount": 10 ** 6, "is_active": True})
    t.check("below minimum amount -> COUPON_MIN_AMOUNT_NOT_MET", b3().new_booking(coupon={"code": CODE}).error == "COUPON_MIN_AMOUNT_NOT_MET")


@case("Coupon edit replaces every field; keeps own code; refuses another's")
def edit(t):
    t.need("admin_token", "coupon_id")
    tok, cid = t.ctx["admin_token"], t.ctx["coupon_id"]
    r = adm("PUT", "/coupons", token=tok, body={"id": cid, "code": CODE + "B", "discount_type": 2, "discount_value": 20, "is_active": False})
    t.check("updated", r.data.get("message") == "COUPON_UPDATED_SUCCESSFULLY", r.json)
    row = sql(f"SELECT code || '|' || discount_type || '|' || coalesce(max_discount::text,'null') || '|' || coalesce(start_date::text,'null') || '|' || coalesce(description,'null') FROM coupons WHERE id = '{cid}'")
    t.check("omitted fields (cap, dates, description) are cleared", row == f"{CODE}B|2|null|null|null", row)
    t.check("another coupon's code refused", adm("PUT", "/coupons", token=tok, body={"id": cid, "code": "taka50", "discount_type": 1, "discount_value": 5}).error == "COUPON_CODE_ALREADY_EXISTS")
    t.check("own code in another case is fine", adm("PUT", "/coupons", token=tok, body={"id": cid, "code": (CODE + "B").lower(), "discount_type": 2, "discount_value": 20}).data.get("message") == "COUPON_UPDATED_SUCCESSFULLY")
    t.check("unknown id -> COUPON_NOT_FOUND", adm("PUT", "/coupons", token=tok, body={"id": "nope", "code": "ZZ" + CODE, "discount_type": 1, "discount_value": 5}).error == "COUPON_NOT_FOUND")


@case("Coupon read, search, paging and delete")
def read_delete(t):
    t.need("admin_token", "coupon_id", "tok_staff")
    tok, cid = t.ctx["admin_token"], t.ctx["coupon_id"]
    c = adm("GET", f"/coupons/{cid}", token=t.ctx["tok_staff"]).data.get("coupon") or {}
    t.check("by id", c.get("id") == cid and c.get("code", "").lower() == (CODE + "B").lower(), c)
    r = adm("GET", "/coupons", token=tok, params={"limit": 2, "skip": 0})
    t.check("paged: 2 rows and a total_count", len(r.data.get("coupons", [])) == 2 and r.data.get("total_count", 0) >= 3, r.json)
    r = adm("GET", "/coupons", token=tok, params={"search_keyword": CODE.lower()})
    t.check("search is case-insensitive", [x["id"] for x in r.data.get("coupons", [])] == [cid], r.json)
    r = adm("GET", "/coupons", token=tok, params={"is_active": "false", "search_keyword": CODE})
    t.check("is_active=false filter finds it", [x["id"] for x in r.data.get("coupons", [])] == [cid], r.json)
    r = adm("DELETE", f"/coupons/{cid}", token=tok)
    t.check("deleted", r.data.get("message") == "COUPON_DELETED_SUCCESSFULLY" and sql(f"SELECT count(*) FROM coupons WHERE id = '{cid}'") == "0", r.json)
    t.check("read after delete -> COUPON_NOT_FOUND", adm("GET", f"/coupons/{cid}", token=tok).error == "COUPON_NOT_FOUND")
    t.check("delete again -> not found", bool(adm("DELETE", f"/coupons/{cid}", token=tok).error))
