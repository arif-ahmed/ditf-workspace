"""Merchant stalls, QR collectors, staff QR cards (generate, assign, daily scan limit, history)."""
import random

from client import adm, sql
from runner import case


@case("Stall lifecycle: create, read by id, edit ignores tenant fields, delete")
def stall(t):
    t.need("admin_token", "tok_qr")
    tok = t.ctx["admin_token"]
    r = adm("POST", "/merchant-stall-master", token=tok, body={"stall_name": "AUTOTEST Stall", "stall_number": f"S-{random.randint(1000, 9999)}"})
    sid = r.data.get("merchant_stall_master_id")
    t.check("created", bool(sid), r.json)
    t.ctx["stall_id"] = sid
    t.check("QR staff (6) can read by id", adm("GET", f"/merchant-stall-master/{sid}", token=t.ctx["tok_qr"]).status == 200)
    r = adm("PUT", "/merchant-stall-master", token=tok, body={"id": sid, "stall_name": "AUTOTEST Stall 2", "company_id": "evil"})
    t.check("edited", r.data.get("message") == "MERCHANT_STALL_MASTER_UPDATED_SUCCESSFULLY", r.json)
    t.check("unexpected company_id not stored", "company_id" not in sql(f"SELECT row_to_json(t)::text FROM merchant_stall_master t WHERE id = '{sid}'"))
    t.check("unknown stall id -> error", bool(adm("GET", "/merchant-stall-master/nope", token=tok).error))
    t.check("QR staff cannot delete -> 403", adm("DELETE", f"/merchant-stall-master/{sid}", token=t.ctx["tok_qr"]).status == 403)
    t.check("delete unknown -> error", bool(adm("DELETE", "/merchant-stall-master/nope", token=tok).error))


@case("QR collectors: create (QR staff), list/filter, edit, read by scanner")
def collectors(t):
    t.need("tok_qr", "stall_id", "admin_token", "tok_scanner")
    ph = "017" + str(random.randint(10000000, 99999999))
    r = adm("POST", "/qr-codes-collector", token=t.ctx["tok_qr"], body={"first_name": "AUTOTEST", "phone_number": ph, "dial_code": "+880",
                                                                       "merchant_stall_master_id": t.ctx["stall_id"], "assigned_count": 1})
    c1 = r.data.get("qr_codes_collector_id")
    c2 = adm("POST", "/qr-codes-collector", token=t.ctx["tok_qr"], body={"first_name": "AUTOTEST2", "merchant_stall_master_id": t.ctx["stall_id"]}).data.get("qr_codes_collector_id")
    t.check("two collectors created", bool(c1 and c2), r.json)
    t.ctx["collector1"], t.ctx["collector2"] = c1, c2
    r = adm("GET", "/qr-codes-collector", token=t.ctx["tok_qr"], params={"merchant_stall_master_id": t.ctx["stall_id"]})
    t.check("list filtered by stall returns exactly those two", sorted(x.get("id") or x.get("_id") for x in (r.data.get("qr_codes_collector") or r.data.get("qr_codes_collectors") or [])) == sorted([c1, c2]), r.json)
    t.check("scanner can read a collector (card owner)", adm("GET", f"/qr-codes-collector/{c1}", token=t.ctx["tok_scanner"]).status == 200)
    r = adm("PUT", "/qr-codes-collector", token=t.ctx["tok_qr"], body={"id": c1, "first_name": "AUTOTEST-EDITED", "phone_number": ph, "merchant_stall_master_id": t.ctx["stall_id"]})
    t.check("collector edited", r.status == 200 and not r.error, r.json)
    t.check("generator cannot create collectors -> 403", adm("POST", "/qr-codes-collector", token=t.ctx["tok_generator"], body={"first_name": "x"}).status == 403)
    t.check("unknown collector id -> error", bool(adm("GET", "/qr-codes-collector/nope", token=t.ctx["tok_qr"]).error))


@case("Staff QR cards: generate (limits), list unassigned, assign, double-assign refused")
def cards(t):
    t.need("admin_token", "tok_qr", "collector1", "collector2", "stall_id")
    tok = t.ctx["admin_token"]
    r = adm("POST", "/generate-qr-codes", token=tok, body={"qr_count": 5, "scan_limit": 2, "qr_label": "AUTOTEST"})
    gid = r.data.get("id")
    t.check("5 cards generated", r.data.get("message") == "Staff QR Generator Details Save Successfully!" and sql(f"SELECT count(*) FROM staff_qr_codes WHERE staff_qr_generator_id = '{gid}'") == "5", r.json)
    t.check("card numbers are 11 digits", sql(f"SELECT count(*) FROM staff_qr_codes WHERE staff_qr_generator_id = '{gid}' AND length(staff_qr_code_number) = 11") == "5")
    t.check("qr_count 5000 -> 400", adm("POST", "/generate-qr-codes", token=tok, body={"qr_count": 5000, "scan_limit": 2, "qr_label": "x"}).status == 400)
    t.check("qr_count 0 -> 400", adm("POST", "/generate-qr-codes", token=tok, body={"qr_count": 0, "scan_limit": 2, "qr_label": "x"}).status == 400)
    t.check("generator role cannot generate -> 403", adm("POST", "/generate-qr-codes", token=t.ctx["tok_generator"], body={"qr_count": 1, "scan_limit": 1, "qr_label": "x"}).status == 403)
    r = adm("GET", "/staff-qr-generator", token=tok, params={"qr_count": 5, "scan_limit": 2})
    t.check("generator batches listable", r.status == 200 and gid in str(r.json), r.json)
    cid, cstr = sql(f"SELECT id || '|' || staff_qr_string FROM staff_qr_codes WHERE staff_qr_generator_id = '{gid}' LIMIT 1").split("|")
    t.check("unassigned filter lists cards", adm("GET", "/staff-qr-codes", token=t.ctx["tok_qr"], params={"is_assigned": "false"}).status == 200)
    r = adm("PUT", "/staff-qr-codes", token=t.ctx["tok_qr"], body={"id": cid, "is_assigned": True, "qr_codes_collector_id": t.ctx["collector1"], "merchant_stall_master_id": t.ctx["stall_id"]})
    t.check("card assigned", r.data.get("message") == "Staff QR Code data updated successfully", r.json)
    t.check("another collector can't take a held card", adm("PUT", "/staff-qr-codes", token=t.ctx["tok_qr"], body={"id": cid, "is_assigned": True, "qr_codes_collector_id": t.ctx["collector2"]}).error == "STAFF_QR_CODE_ALREADY_ASSIGNED")
    t.ctx["card_id"], t.ctx["card_str"] = cid, cstr


@case("Staff card scan: daily limit enforced, history logged, role rules")
def card_scan(t):
    t.need("card_id", "card_str", "tok_scanner", "admin_token")
    scan = lambda tok, s=None: adm("POST", "/scan-staff-qrcode", token=tok, body={"staff_qrcode_string": s or t.ctx["card_str"], "scanned_by": "autotest-scanner"})
    a, b, c = scan(t.ctx["tok_scanner"]), scan(t.ctx["tok_scanner"]), scan(t.ctx["tok_scanner"])
    t.check("limit 2: first scan leaves 1", a.data.get("remaining_limit") == 1, a.json)
    t.check("second scan leaves 0", b.data.get("remaining_limit") == 0, b.json)
    t.check("third refused: 'Maximum scan limit for today reached.'", c.data.get("message") == "Maximum scan limit for today reached.", c.json)
    t.check("only 2 history rows stored", sql(f"SELECT count(*) FROM staff_qr_scan_history WHERE staff_qr_codes_id = '{t.ctx['card_id']}'") == "2")
    t.check("unknown card -> 'Invalid QR code.'", scan(t.ctx["tok_scanner"], "nope").error == "Invalid QR code.")
    t.check("generator role cannot scan cards -> 403", scan(t.ctx["tok_generator"]).status == 403)
    t.check("no token -> 401", adm("POST", "/scan-staff-qrcode", body={"staff_qrcode_string": "x"}).status == 401)
    r = adm("GET", "/staff-qr-scan-history", token=t.ctx["admin_token"], params={"staff_qr_codes_id": t.ctx["card_id"]})
    t.check("history lists both scans", [h["scanned_by"] for h in r.data.get("staff_qr_scan_history_data", [])] == ["autotest-scanner"] * 2, r.json)


@case("Stall delete (admin)")
def stall_delete(t):
    t.need("stall_id", "admin_token")
    r = adm("DELETE", f"/merchant-stall-master/{t.ctx['stall_id']}", token=t.ctx["admin_token"])
    t.check("deleted", r.data.get("message") == "MERCHANT_STALL_MASTER_DELETED_SUCCESSFULLY", r.json)
    t.check("gone", bool(adm("GET", f"/merchant-stall-master/{t.ctx['stall_id']}", token=t.ctx["admin_token"]).error))
