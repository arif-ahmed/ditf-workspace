"""Payment reconciliation background job (public API, @Scheduled). Dev defaults: every 120s, only bookings older than 180s
and younger than 24h, each rechecked at most every 600s. Set PAYMENT_RECONCILE_INTERVAL=off in scripts/dev.local.env to skip this case.
Bookings are aged through the database so the job picks them up on its next tick (up to ~2 min)."""
import os, time

from client import ROOT, mock, sql
from helpers import b3, checkout, wait
from runner import case


def interval_off():
    f = os.path.join(ROOT, "scripts", "dev.local.env")
    return os.path.exists(f) and any(l.replace(" ", "").strip().lower() == "payment_reconcile_interval=off" for l in open(f, encoding="utf-8"))


def aged(booking_id, seconds):
    sql(f"UPDATE booking_master SET payment_updated_date = extract(epoch FROM now())::bigint - {seconds}, payment_last_checked_date = NULL WHERE id = '{booking_id}'")


@case("Database maintenance job: daily partitions exist (yesterday .. a week ahead) and recent scans are not in the default partition", jobs=["DbSetup"])
def partitions(t):
    t.check("ticket_scans has >= 10 daily partitions", int(sql("SELECT count(*) FROM pg_inherits WHERE inhparent = 'ticket_scans'::regclass")) >= 10)
    t.check("staff_qr_scan_history has >= 10 daily partitions", int(sql("SELECT count(*) FROM pg_inherits WHERE inhparent = 'staff_qr_scan_history'::regclass")) >= 10)
    t.check("no recent scan fell into the default partition (old seed scans may legitimately be there)",
            sql("SELECT count(*) FROM ticket_scans_default WHERE scanned_date > extract(epoch FROM now())::bigint - 7200") == "0")
    today = sql("SELECT to_char(now() AT TIME ZONE 'Asia/Dhaka', 'YYYYMMDD')")
    t.check("today's (Dhaka) partition exists", sql(f"SELECT to_regclass('ticket_scans_{today}')") == f"ticket_scans_{today}")


@case("Reconciliation job: settles lost payments, issues missing tickets, leaves the rest alone", slow=True, jobs=["ReconciliationJob"])
def reconcile(t):
    from runner import Skip
    if interval_off():
        raise Skip("PAYMENT_RECONCILE_INTERVAL=off in scripts/dev.local.env")
    bk = b3()
    new = lambda phone: bk.new_booking(adults=1, phone=phone).data.get("booking_master_id")
    # A: paid at the gateway, but neither the browser return nor the IPN ever arrived -> job must settle it
    a = new("01500000001"); uid_a, co_a, _ = checkout(a); mock("/mock/result", {"unique_txn_id": uid_a, "status_code": 3}); aged(a, 300)
    # B: marked paid but no ticket was ever issued -> job must issue it
    b = new("01500000002"); sql(f"UPDATE booking_master SET txn_status = 3 WHERE id = '{b}'"); aged(b, 300)
    # C: still pending at the gateway -> checked, but stays pending
    c = new("01500000003"); checkout(c); aged(c, 300)
    # D: too young (inside the minimum age) -> not touched
    d = new("01500000004"); uid_d, _, _ = checkout(d); mock("/mock/result", {"unique_txn_id": uid_d, "status_code": 3}); aged(d, 5)
    # E: older than max age (24h) -> given up on, not touched
    e = new("01500000005"); uid_e, _, _ = checkout(e); mock("/mock/result", {"unique_txn_id": uid_e, "status_code": 3}); aged(e, 25 * 3600)
    st = lambda i: sql(f"SELECT txn_status || '|' || coalesce(payment_settled_by,'-') || '|' || (trade_fair_ticket_booking_info ->> 'ticket_link' IS NOT NULL) FROM booking_master WHERE id = '{i}'")
    done = wait(lambda: st(a).startswith("3|RECONCILE") and st(b).endswith("|true") and sql(f"SELECT payment_last_checked_date FROM booking_master WHERE id = '{c}'") != "", 200, every=3)
    t.check("A: lost payment settled by the job (payment_settled_by = RECONCILE)", st(a).startswith("3|RECONCILE"), st(a))
    wait(lambda: st(a).endswith("|true"), 60)
    t.check("A: ...and its ticket PDF was issued", st(a).endswith("|true"), st(a))
    t.check("B: paid-but-ticketless booking got its ticket", st(b).endswith("|true"), st(b))
    t.check("C: pending-at-gateway booking was checked (timestamp set) and is still pending", st(c).startswith("1|") and sql(f"SELECT payment_last_checked_date FROM booking_master WHERE id = '{c}'") != "", st(c))
    t.check("D: too-young booking was left alone", st(d).startswith("1|"), st(d))
    t.check("E: older than 24h was left alone", st(e).startswith("1|"), st(e))
    t.check("job finished within the wait window", bool(done))
    t.check("gateway signature errors: none", not mock("/mock/state")["errors"], mock("/mock/state")["errors"])
