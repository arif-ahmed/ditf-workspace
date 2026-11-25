"""User administration edge cases: who may create/edit/delete whom, and what a deleted user can still do."""
from client import adm, login, sql
from helpers import unique_phone
from runner import case


def mk(tok, role, **extra):
    ph = unique_phone()
    u = {"first_name": "AUTOTEST", "last_name": f"R{role}", "dial_code": "+880", "phone_number": ph, "user_role": role, **extra}
    r = adm("POST", "/save-users-details", token=tok, body={"user_details": [u]})
    uid = sql(f"SELECT id FROM booking_user_master WHERE phone_number = '{ph}'")
    return r, ph, uid


@case("User creation: admin staff cannot create admins; merchant staff get a QR string")
def create_rules(t):
    t.need("admin_token", "tok_staff")
    r, ph, uid = mk(t.ctx["tok_staff"], 3, login_pin="1111")
    t.check("admin staff (5) creating an admin -> 403", r.status == 403, r.json)
    t.check("...and nothing was created", uid == "", uid)
    r, ph, uid = mk(t.ctx["admin_token"], 4)
    qr = sql(f"SELECT staff_qr_string FROM booking_user_master WHERE phone_number = '{ph}'")
    t.check("merchant staff (4) created without a PIN", r.data.get("message") == "User Details Save Successfully", r.json)
    t.check("...and gets a staff_qr_string starting with the phone", qr.startswith(ph + "-"), qr)
    r, ph, uid = mk(t.ctx["admin_token"], 1, login_pin="2222")
    t.check("admin creates an agent", bool(uid), r.json)
    t.ctx["tmp_user"], t.ctx["tmp_phone"] = uid, ph


@case("User edit: PUT changes fields but never the balance")
def edit_user(t):
    t.need("admin_token", "tmp_user")
    r = adm("PUT", "/save-users-details", token=t.ctx["admin_token"],
            body={"user_details": [{"id": t.ctx["tmp_user"], "first_name": "AUTOTEST2", "login_pin": "5555", "user_role": 1, "balance": 999999}]})
    t.check("update message", r.data.get("message") == "User Details Updated Successfully", r.json)
    row = sql(f"SELECT first_name || '|' || login_pin || '|' || balance::numeric(12,0) FROM booking_user_master WHERE id = '{t.ctx['tmp_user']}'")
    t.check("name and PIN changed, balance still 0 (client can't set it)", row == "AUTOTEST2|5555|0", row)
    t.check("the new PIN works at login", bool(login(t.ctx["tmp_phone"], "5555").data.get("token")))
    t.check("the old PIN does not", login(t.ctx["tmp_phone"], "2222").error == "Login pin verification failed")


@case("User read: by id, own record only for non-admins, list filters")
def read_user(t):
    t.need("admin_token", "tok_generator", "id_generator", "tmp_user")
    tok = t.ctx["admin_token"]
    r = adm("GET", f"/booking-user-master/{t.ctx['tmp_user']}", token=tok)
    t.check("admin reads any user", (r.data.get("booking_user_master") or {}).get("id") == t.ctx["tmp_user"], r.json)
    t.check("no PIN in the single-user read", "login_pin" not in str(r.json))
    t.check("generator reads their own record", adm("GET", f"/booking-user-master/{t.ctx['id_generator']}", token=t.ctx["tok_generator"]).status == 200)
    t.check("...but not someone else's -> 403", adm("GET", f"/booking-user-master/{t.ctx['tmp_user']}", token=t.ctx["tok_generator"]).status == 403)
    r = adm("GET", "/booking-user-master", token=tok, params={"user_role": 1, "skip": 0, "limit": 5})
    page = r.data.get("booking_user_master") or {}
    t.check("paged list shape: content + totalElements", isinstance(page.get("content"), list) and isinstance(page.get("totalElements"), int) and len(page["content"]) <= 5, r.json)
    t.check("deactivated seed agent is not listed", "1900001099" not in str(r.json) and "1900003099" not in str(adm("GET", "/booking-user-master", token=tok, params={"user_role": 3}).json))


@case("User delete: deactivates, token dies at once, cannot log in, cannot delete self")
def delete_user(t):
    t.need("admin_token", "tmp_user", "tmp_phone")
    tok = t.ctx["admin_token"]
    tmp_tok = login(t.ctx["tmp_phone"], "5555").data.get("token")
    t.check("temp user has a working token first", adm("GET", f"/booking-user-master/{t.ctx['tmp_user']}", token=tmp_tok).status == 200)
    r = adm("DELETE", f"/booking-user-master/{t.ctx['tmp_user']}", token=tok)
    t.check("delete message", r.data.get("message") == "Booking user data deleted successfully", r.json)
    t.check("row kept, is_active false (history preserved)", sql(f"SELECT is_active FROM booking_user_master WHERE id = '{t.ctx['tmp_user']}'") == "f")
    t.check("their token stops working immediately -> 401", adm("GET", f"/booking-user-master/{t.ctx['tmp_user']}", token=tmp_tok).status == 401)
    t.check("they can no longer log in", login(t.ctx["tmp_phone"], "5555").error == "Login pin verification failed")
    admin_id = sql("SELECT id FROM booking_user_master WHERE phone_number = '1900003001'")
    t.check("an admin cannot delete themselves -> 403", adm("DELETE", f"/booking-user-master/{admin_id}", token=tok).status == 403)
    t.check("generator cannot delete users -> 403", adm("DELETE", f"/booking-user-master/{t.ctx['tmp_user']}", token=t.ctx["tok_generator"]).status == 403)


@case("Login throttling: wrong PIN refused; 5 wrong PINs lock the account (throwaway users, so reruns stay clean)")
def login_lock(t):
    t.need("admin_token")
    r, ph, uid = mk(t.ctx["admin_token"], 1, login_pin="3333")
    t.check("wrong PIN -> 'Login pin verification failed'", login(ph, "9999").error == "Login pin verification failed")
    t.check("right PIN still works after one miss", bool(login(ph, "3333").data.get("token")))
    last = [login(ph, "0000").error for _ in range(6)]
    t.check("repeated wrong PINs end in TOO_MANY_ATTEMPTS", last[-1] == "TOO_MANY_ATTEMPTS", last)
    t.check("...and then even the right PIN is refused for a while", login(ph, "3333").error == "TOO_MANY_ATTEMPTS")
    t.check("an unknown phone is refused without leaking that it is unknown", login(unique_phone(), "1234").error == "Login pin verification failed")
