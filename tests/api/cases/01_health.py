from client import adm, pub
from runner import case


@case("Both APIs answer /health")
def health(t):
    t.check("public API health is 200", pub("GET", "/health").status == 200)
    t.check("admin API health is 200", adm("GET", "/health").status == 200)


@case("Each build exposes only its own endpoints")
def build_split(t):
    t.check("public build has no admin login (404)", pub("POST", "/verify-login-pin", body={"phone_number": "1", "login_pin": "1"}).status == 404)
    t.check("public build has no user list (404)", pub("GET", "/booking-user-master").status == 404)
    t.check("admin build has no initiate-payment (404)", adm("POST", "/initiate-payment", body={}).status == 404)
    t.check("admin build has no find-ticket (404)", adm("POST", "/find-ticket", body={}).status == 404)
