"""Ticket batch background job: activation guards and resume after failure/interruption.
The job state is forced through the database (as an interrupted run would leave it), because the API gives no way to break a run."""
import subprocess, time

from client import DB_CONTAINER, adm, sql
from helpers import wait
from runner import case


def start(t, n=3, ticket_type=2):
    r = adm("POST", "/user-ticket-generator", token=t.ctx["tok_generator"], body={"user_id": t.ctx["id_generator"], "total_no_of_tickets": n, "ticket_type": ticket_type})
    bid, job = r.data.get("id"), r.data.get("background_job_id")
    done = wait(lambda: sql(f"SELECT status FROM background_job WHERE id = '{job}'") == "2", 60)
    return bid, job, bool(done)


@case("Batch job: lifecycle, numbering, list agrees with single read", jobs=["ticket_batch"])
def lifecycle(t):
    t.need("tok_generator", "id_generator")
    bid, job, done = start(t, 3)
    t.check("job completed", done)
    t.ctx["batch"], t.ctx["job"] = bid, job
    j = adm("GET", f"/background-job/{job}", token=t.ctx["tok_generator"]).data.get("background_job") or {}
    t.check("job record: type ticket_batch, references the batch, status 2", j.get("job_type") == "ticket_batch" and j.get("reference_id") == bid and j.get("status") == 2, j)
    t.check("jobs live in background_job; no legacy kafka_queue_operation table", sql("SELECT to_regclass('kafka_queue_operation')") == "")
    t.check("unknown job -> BACKGROUND_JOB_NOT_FOUND", adm("GET", "/background-job/nope", token=t.ctx["tok_generator"]).error == "BACKGROUND_JOB_NOT_FOUND")
    t.check("old endpoint name is gone (404)", adm("GET", "/kafka_queue_operation", token=t.ctx["tok_generator"], params={"reference_id": bid}).status == 404)
    t.check("no token -> 401", adm("GET", f"/background-job/{job}").status == 401)
    t.check("3 unique inactive barcodes stored", sql(f"SELECT count(DISTINCT trade_fair_ticket_barcode) FROM booking_barcode_details WHERE user_ticket_generator_id = '{bid}' AND NOT is_active") == "3")
    single = (adm("GET", f"/user-ticket-generator/{bid}", token=t.ctx["tok_generator"]).data.get("user_ticket_generator") or {})
    listed = {x["id"]: x for x in adm("GET", "/user-ticket-generator", token=t.ctx["tok_generator"], params={"user_id": t.ctx["id_generator"]}).data.get("user_ticket_generator", [])}
    t.check("batch has a number like BT###, inactive, generation_status 2", str(single.get("batch_number", "")).startswith("BT") and single.get("is_active") is False and single.get("generation_status") == 2, single)
    t.check("list and single read agree on generation_status", listed.get(bid, {}).get("generation_status") == single.get("generation_status"), listed.get(bid))
    t.check("bad size/type refused", adm("POST", "/user-ticket-generator", token=t.ctx["tok_generator"], body={"total_no_of_tickets": 0, "ticket_type": 1}).error == "INVALID_TICKET_QUANTITY"
            and adm("POST", "/user-ticket-generator", token=t.ctx["tok_generator"], body={"total_no_of_tickets": 5, "ticket_type": 7}).error == "INVALID_TICKET_TYPE")
    t.check("scanner cannot start a batch -> 403", adm("POST", "/user-ticket-generator", token=t.ctx["tok_scanner"], body={"total_no_of_tickets": 1, "ticket_type": 1}).status == 403)


@case("Inactive batch tickets are refused at the gate; barcode list and lookup work")
def inactive_gate(t):
    t.need("batch", "tok_scanner", "tok_generator", "admin_token")
    from client import enc
    code = sql(f"SELECT trade_fair_ticket_barcode FROM booking_barcode_details WHERE user_ticket_generator_id = '{t.ctx['batch']}' LIMIT 1")
    r = adm("GET", "/scan-barcode", token=t.ctx["tok_scanner"], params={"requested_data": enc({"barcode_string": code})})
    t.check("'Ticket not activated'", r.error == "Ticket not activated", r.json)
    qr = sql(f"SELECT booking_qr_string FROM booking_barcode_details WHERE trade_fair_ticket_barcode = '{code}'")
    t.check("its receipt QR says the same", adm("POST", "/scan-qr", token=t.ctx["tok_scanner"], body={"qrcode_string": qr}).error == "Ticket not activated")
    r = adm("GET", "/booking-barcode-details", token=t.ctx["tok_generator"], params={"user_ticket_generator_id": t.ctx["batch"], "skip": 0, "limit": 2})
    t.check("barcode list of a batch is paged", len(r.data.get("ticket_barcode_details_list", [])) == 2, r.json)


@case("Activation is refused while generating or after a failed generation", jobs=["ticket_batch"])
def activation_guard(t):
    t.need("batch", "job", "tok_generator")
    act = lambda: adm("POST", "/user-ticket-status", token=t.ctx["tok_generator"], body={"_id": t.ctx["batch"], "is_active": True})
    sql(f"UPDATE background_job SET status = 1 WHERE id = '{t.ctx['job']}'")
    t.check("still generating -> TICKET_GENERATION_IN_PROGRESS", act().error == "TICKET_GENERATION_IN_PROGRESS")
    sql(f"UPDATE background_job SET status = 3 WHERE id = '{t.ctx['job']}'")
    t.check("failed -> TICKET_GENERATION_FAILED", act().error == "TICKET_GENERATION_FAILED")
    t.check("nothing was activated", sql(f"SELECT count(*) FROM booking_barcode_details WHERE user_ticket_generator_id = '{t.ctx['batch']}' AND is_active") == "0")
    sql(f"UPDATE background_job SET status = 2 WHERE id = '{t.ctx['job']}'")
    t.check("unknown batch -> USER_TICKET_GENERATOR_NOT_FOUND", adm("POST", "/user-ticket-status", token=t.ctx["tok_generator"], body={"_id": "nope", "is_active": True}).error == "USER_TICKET_GENERATOR_NOT_FOUND")


@case("Resume: completed batch refused; failed or interrupted batch regenerates only the missing tickets", jobs=["ticket_batch"])
def resume(t):
    t.need("batch", "job", "tok_generator")
    bid, job, tok = t.ctx["batch"], t.ctx["job"], t.ctx["tok_generator"]
    rs = lambda: adm("POST", f"/user-ticket-generator/{bid}/resume", token=tok, body={})
    kept_id, kept_bm = sql(f"SELECT id || '|' || booking_master_id FROM booking_barcode_details WHERE user_ticket_generator_id = '{bid}' ORDER BY id LIMIT 1").split("|")
    t.check("completed batch -> TICKET_GENERATION_ALREADY_COMPLETED", rs().error == "TICKET_GENERATION_ALREADY_COMPLETED")

    def cut(status):  # as if a run died after storing 1 of the 3 tickets
        sql(f"DELETE FROM booking_barcode_details WHERE user_ticket_generator_id = '{bid}' AND id <> '{kept_id}'")
        sql(f"DELETE FROM booking_master WHERE user_ticket_generator_id = '{bid}' AND id <> '{kept_bm}'")
        sql(f"UPDATE background_job SET status = {status} WHERE id = '{job}'")

    def resumed():
        r = rs()
        done = wait(lambda: sql(f"SELECT status FROM background_job WHERE id = '{job}'") == "2", 60)
        n = sql(f"SELECT count(*) FROM booking_barcode_details WHERE user_ticket_generator_id = '{bid}'")
        uniq = sql(f"SELECT count(DISTINCT trade_fair_ticket_barcode) FROM booking_barcode_details WHERE user_ticket_generator_id = '{bid}'")
        kept = sql(f"SELECT count(*) FROM booking_barcode_details WHERE id = '{kept_id}'")
        return r, done, n, uniq, kept

    cut(3)
    r, done, n, uniq, kept = resumed()
    t.check("failed batch: resume message and same job id", r.data.get("message") == "USER_TICKET_GENERATOR_PROCESS_RESUMED_SUCCESSFULLY" and r.data.get("background_job_id") == job, r.json)
    t.check("...job completes, 3 unique tickets, the stored one kept", done and (n, uniq, kept) == ("3", "3", "1"), (done, n, uniq, kept))
    cut(1)
    r, done, n, uniq, kept = resumed()
    t.check("a batch left 'running' by a restart can be resumed too", done and (n, uniq, kept) == ("3", "3", "1"), (r.json, n, uniq, kept))
    sql(f"UPDATE background_job SET status = 3 WHERE id = '{job}'")
    holder = subprocess.Popen(["docker", "exec", DB_CONTAINER, "psql", "-U", "ditf", "-d", "ditf", "-c",
                               f"SELECT pg_advisory_lock(hashtext('ticket-batch-generation:{bid}')); SELECT pg_sleep(30)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait(lambda: sql("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted") != "0", 15)
        t.check("no resume while another server holds the generation lock -> TICKET_GENERATION_IN_PROGRESS", rs().error == "TICKET_GENERATION_IN_PROGRESS")
    finally:
        holder.kill()
        sql("SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND pid <> pg_backend_pid()")
    time.sleep(1)
    r, done, n, uniq, kept = resumed()
    t.check("once the lock is free it resumes; nothing missing, nothing added", done and (n, uniq) == ("3", "3"), (r.json, n, uniq))
    sql(f"UPDATE user_ticket_generator SET is_active = true WHERE id = '{bid}'")
    sql(f"UPDATE background_job SET status = 3 WHERE id = '{job}'")
    t.check("an active batch must be deactivated first -> DEACTIVATE_BATCH_FIRST", rs().error == "DEACTIVATE_BATCH_FIRST")
    sql(f"UPDATE user_ticket_generator SET is_active = false WHERE id = '{bid}'")
    sql(f"UPDATE background_job SET status = 2 WHERE id = '{job}'")
    t.check("unknown batch -> USER_TICKET_GENERATOR_NOT_FOUND", adm("POST", "/user-ticket-generator/nope/resume", token=tok, body={}).error == "USER_TICKET_GENERATOR_NOT_FOUND")
    t.check("scanner cannot resume -> 403", adm("POST", f"/user-ticket-generator/{bid}/resume", token=t.ctx["tok_scanner"], body={}).status == 403)


@case("Batch activation makes its tickets scannable")
def activate(t):
    t.need("batch", "tok_generator", "tok_scanner", "admin_token")
    from client import enc
    r = adm("POST", "/user-ticket-status", token=t.ctx["tok_generator"], body={"_id": t.ctx["batch"], "is_active": True})
    t.check("activated", r.data.get("message") == "USER_TICKET_GENERATOR_UPDATED_SUCCESSFULLY", r.json)
    t.check("all its barcodes are now active", sql(f"SELECT count(*) FROM booking_barcode_details WHERE user_ticket_generator_id = '{t.ctx['batch']}' AND NOT is_active") == "0")
    code = sql(f"SELECT trade_fair_ticket_barcode FROM booking_barcode_details WHERE user_ticket_generator_id = '{t.ctx['batch']}' LIMIT 1")
    r = adm("GET", "/booking-barcode-details", token=t.ctx["admin_token"], params={"trade_fair_ticket_barcode": code})
    t.check("lookup by barcode number (activated tickets)", [x["trade_fair_ticket_barcode"] for x in r.data.get("ticket_barcode_details_list", [])] == [code], r.json)
    r = adm("GET", "/scan-barcode", token=t.ctx["tok_scanner"], params={"requested_data": enc({"barcode_string": code})})
    t.check("an activated batch ticket admits at the gate", r.status == 200 and not r.error, r.json)
    t.check("and only once", adm("GET", "/scan-barcode", token=t.ctx["tok_scanner"], params={"requested_data": enc({"barcode_string": code})}).error == "Ticket already used")
