"""Seeded users (scripts/seed/seed.sql): phone 190000 + role + 3-digit index, PIN 1234. 1900003099 is deactivated."""
from client import adm, login
from runner import case

ADMIN, STAFF, QR_STAFF, SCANNER, GENERATOR = "1900003001", "1900005001", "1900006001", "1900007001", "1900008001"


@case("Admin logs in and gets a token (PIN never returned)")
def login_ok(t):
    r = login(ADMIN)
    u = r.data.get("booking_user_master") or {}
    t.check("200 with success message", r.status == 200 and r.data.get("message") == "Login pin verified successfully", r.json)
    t.check("user role is 3 (admin)", u.get("user_role") == 3, u)
    t.check("token present", bool(r.data.get("token")))
    t.check("response never contains the PIN", "login_pin" not in str(r.json))
    t.ctx["admin_token"] = r.data.get("token")


@case("Login is refused for bad credentials")
def login_bad(t):
    t.check("deactivated user cannot log in", login("1900003099").data.get("token") is None)
    t.check("empty PIN -> 400", login(STAFF, "").status == 400)


@case("Every seeded portal role can log in")
def all_roles(t):
    for key, name, phone in (("staff", "admin staff", STAFF), ("qr", "QR staff", QR_STAFF), ("scanner", "scanner", SCANNER), ("generator", "ticket generator", GENERATOR)):
        r = login(phone)
        tok = r.data.get("token")
        t.check(f"{name} gets a token", bool(tok))
        t.ctx["tok_" + key] = tok
        t.ctx["id_" + key] = (r.data.get("booking_user_master") or {}).get("id")


@case("Token checks: missing, garbage, wrong scheme")
def token_checks(t):
    t.need("admin_token")
    t.check("no token -> 401 UNAUTHORIZED", adm("GET", "/booking-user-master", params={"user_role": 1}).status == 401)
    t.check("garbage token -> 401", adm("GET", "/booking-user-master", token="abc.def").status == 401)
    t.check("Bearer scheme not accepted -> 401", adm("GET", "/booking-user-master", headers={"Authorization": "Bearer " + t.ctx["admin_token"]}).status == 401)


@case("Role checks: lower roles are forbidden from admin-only actions")
def roles(t):
    t.need("tok_generator", "tok_staff", "tok_qr")
    t.check("generator (8) can't list users -> 403", adm("GET", "/booking-user-master", token=t.ctx["tok_generator"]).status == 403)
    t.check("admin staff (5) can't move money -> 403",
            adm("POST", "/update-user-balance", token=t.ctx["tok_staff"], body={"user_id": "x", "type": 1, "amount": 5}).status == 403)
    t.check("QR staff (6) can't create stalls -> 403",
            adm("POST", "/merchant-stall-master", token=t.ctx["tok_qr"], body={"stall_name": "X"}).status == 403)
