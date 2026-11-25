"""Admin back office: users, agent wallet, stalls, ticket batches, dashboard. Creates AUTOTEST-tagged records with random phones."""
import random, time

from client import adm
from runner import case


def phone():
    return "017" + "".join(random.choice("0123456789") for _ in range(8))


@case("Admin creates an agent; duplicates and bad requests refused")
def create_agent(t):
    t.need("admin_token")
    tok, ph = t.ctx["admin_token"], phone()
    agent = {"first_name": "AUTOTEST", "last_name": "Agent", "dial_code": "+880", "phone_number": ph, "login_pin": "4321", "user_role": 1, "printer_type": 1}
    r = adm("POST", "/save-users-details", token=tok, body={"user_details": [agent]})
    t.check("created", r.data.get("message") == "User Details Save Successfully", r.json)
    t.check("duplicate phone -> PHONE_NUMBER_ALREADY_EXISTS", adm("POST", "/save-users-details", token=tok, body={"user_details": [agent]}).error == "PHONE_NUMBER_ALREADY_EXISTS")
    t.check("missing user_details -> 400", adm("POST", "/save-users-details", token=tok, body={}).status == 400)
    r = adm("GET", "/booking-user-master", token=tok, params={"search_keyword": ph, "skip": 0, "limit": 10})
    rows = (r.data.get("booking_user_master") or {}).get("content") or []
    t.check("agent found by phone search, PIN not exposed", len(rows) == 1 and "login_pin" not in str(r.json), r.json)
    t.check("regex keyword is treated literally (no match)", adm("GET", "/booking-user-master", token=tok, params={"search_keyword": ".*"}).error == "Booking users data not found")
    if rows:
        t.ctx["agent_id"], t.ctx["agent_phone"], t.ctx["agent_pin"] = rows[0]["id"], ph, "4321"


@case("Agent wallet: top-up, overdraw, invalid amounts, ledger")
def wallet(t):
    t.need("admin_token", "agent_id")
    tok, uid = t.ctx["admin_token"], t.ctx["agent_id"]
    bal = lambda ty, amt: adm("POST", "/update-user-balance", token=tok, body={"user_id": uid, "type": ty, "amount": amt})
    t.check("top-up 500", bal(1, 500).data.get("message") == "User balance updated successfully")
    t.check("withdraw more than balance -> 'Insufficient balance.'", bal(2, 600).error == "Insufficient balance.")
    t.check("negative amount refused", bal(1, -100).error == "Amount must be greater than 0.")
    t.check("zero amount refused", bal(1, 0).error == "Amount must be greater than 0.")
    t.check("type 3 (sales) not allowed from admin API", (bal(3, 10).error or "").startswith("Invalid operation type"))
    t.check("withdraw 200.255 (rounded to 2 decimals)", bal(2, 200.255).data.get("message") == "User balance updated successfully")
    rows = adm("GET", "/user-transaction-ledger", token=tok, params={"user_id": uid}).data.get("user_transaction_ledger") or []
    t.check("ledger has the 2 successful movements", sorted(x["amount"] for x in rows) == [200.26, 500], rows)
    r = adm("POST", "/booking-agent-balance-count", token=tok, body={})
    t.check("agent balance summary endpoint answers", r.status == 200, r.json)


@case("Stalls: create, search, edit")
def stalls(t):
    t.need("admin_token")
    tok = t.ctx["admin_token"]
    r = adm("POST", "/merchant-stall-master", token=tok, body={"stall_name": "AUTOTEST Tea", "stall_number": "T-" + str(random.randint(100, 999))})
    sid = r.data.get("merchant_stall_master_id")
    t.check("stall created", r.data.get("message") == "MERCHANT_STALL_MASTER_SAVED_SUCCESSFULLY" and sid, r.json)
    r = adm("GET", "/merchant-stall-master", token=t.ctx.get("tok_qr") or tok, params={"search_keyword": "AUTOTEST"})
    t.check("found by search, by _id", sid in [s.get("_id") for s in r.data.get("merchant_stall_master", [])], r.json)
    r = adm("PUT", "/merchant-stall-master", token=tok, body={"id": sid, "stall_name": "AUTOTEST Tea 2"})
    t.check("stall edited", r.data.get("message") == "MERCHANT_STALL_MASTER_UPDATED_SUCCESSFULLY", r.json)


@case("Ticket batch: generate, job completes, inactive until activated", jobs=["ticket_batch"])
def batch(t):
    t.need("tok_generator", "id_generator")
    tok = t.ctx["tok_generator"]
    r = adm("POST", "/user-ticket-generator", token=tok, body={"user_id": t.ctx["id_generator"], "total_no_of_tickets": 5, "ticket_type": 1})
    bid, job = r.data.get("id"), r.data.get("background_job_id")
    t.check("batch started", r.data.get("message") == "USER_TICKET_GENERATOR_PROCESS_STARTED_SUCCESSFULLY" and bid and job, r.json)
    status = None
    for _ in range(60):
        status = (adm("GET", f"/background-job/{job}", token=tok).data.get("background_job") or {}).get("status")
        if status == 2:
            break
        time.sleep(1)
    t.check("background job reaches status 2 (done)", status == 2, status)
    b = adm("GET", f"/user-ticket-generator/{bid}", token=tok).data.get("user_ticket_generator") or {}
    t.check("batch inactive, generation_status 2", b.get("is_active") is False and b.get("generation_status") == 2, b)
    t.check("invalid size -> INVALID_TICKET_QUANTITY", adm("POST", "/user-ticket-generator", token=tok, body={"total_no_of_tickets": 0, "ticket_type": 1}).error == "INVALID_TICKET_QUANTITY")
    t.check("invalid type -> INVALID_TICKET_TYPE", adm("POST", "/user-ticket-generator", token=tok, body={"total_no_of_tickets": 5, "ticket_type": 7}).error == "INVALID_TICKET_TYPE")
    r = adm("POST", "/user-ticket-status", token=tok, body={"_id": bid, "is_active": True})
    t.check("activate the batch", r.data.get("message") == "USER_TICKET_GENERATOR_UPDATED_SUCCESSFULLY", r.json)


@case("Dashboard endpoints and total_records whitelist")
def dashboard(t):
    t.need("admin_token")
    tok = t.ctx["admin_token"]
    for ep in ("/total-generated-ticket", "/manual-ticket-total-count", "/manual-ticket-scanned-count"):
        t.check(f"{ep} answers 200", adm("POST", ep, token=tok, body={}).status == 200)
    rec = lambda coll, f: adm("POST", "/total-records", token=tok, body={"collection_name": coll, "dropdown_filter": f, "search_filter": {}, "date_filter": {}})
    t.check("agents counted", isinstance(rec("booking_user_master", {"user_role": 1}).data.get("total_count"), int))
    t.check("unknown collection refused", rec("user_transaction_ledger", {}).error == "BAD_REQUEST")
    t.check("PIN can't be probed", rec("booking_user_master", {"login_pin": "1234"}).error == "BAD_REQUEST")
    t.check("total_adults_children needs dates", adm("POST", "/total-adults-children", token=tok, body={}).error == "BAD_REQUEST")
