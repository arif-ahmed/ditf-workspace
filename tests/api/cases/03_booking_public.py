"""Public booking: config, coupons, server-side pricing. Prices come from the live booking config, not hard-coded."""
import uuid

from client import MERCHANT_ID, enc, pub
from runner import case

PHONE = "01700000000"


def new_booking(adults=1, children=0, coupon=None, phone=PHONE):
    body = {"txn_amount": 1.0, "booking_request_id": str(uuid.uuid4()), "platform": 2,
            "trade_fair_ticket_booking_info": {"total_adult_quantity": adults, "total_child_quantity": children,
                                               "customer_phone_number": phone, "customer_dial_code": "+88"},
            "bus_ticket_booking_info": {"total_seat": 0, "pickup_point": "DITF", "drop_point": "Gulshan",
                                        "customer_phone_number": phone, "customer_dial_code": "+88"},
            "coupon_info": coupon or {}, "merchant_info": {"merchant_id": MERCHANT_ID, "merchant_name": "DITF"}}
    return pub("POST", "/booking-master", body=body, encrypted=True)


def booking(booking_id):
    return pub("GET", f"/booking-master/{booking_id}").data.get("booking_master") or {}


@case("Booking config returns prices and no gateway credentials")
def config(t):
    r = pub("GET", "/booking-config", params={"requested_data": enc({"merchant_id": MERCHANT_ID})})
    cfg = (r.data.get("booking_configs") or [{}])[0]
    t.check("200 with an adult and child price", r.status == 200 and cfg.get("adult_price") and cfg.get("child_price"), r.json)
    t.check("no DGePay credentials leaked", not ({"client_id", "client_secret_key", "client_api_key", "token"} & set(cfg.get("merchant_info", {}))), cfg.get("merchant_info"))
    t.check("coupon codes are not listed", "coupon_codes" not in cfg)
    t.ctx["adult"], t.ctx["child"] = cfg.get("adult_price"), cfg.get("child_price")


@case("check-coupon-code: valid, wrong-case, unknown, empty")
def coupon_check(t):
    r = pub("GET", "/check-coupon-code", params={"coupon_code": "dgepay10"})
    c = r.data.get("coupon") or {}
    t.check("DgePay10 valid in any case", r.data.get("is_coupon_code_valid") is True and c.get("discount_value") == 10, r.json)
    t.check("rules returned (10%, max 15)", c.get("discount_type") == 1 and c.get("max_discount") == 15, c)
    t.check("unknown code -> INVALID_COUPON_CODE", pub("GET", "/check-coupon-code", params={"coupon_code": "NOPE"}).error == "INVALID_COUPON_CODE")
    t.check("empty code -> BAD_REQUEST", pub("GET", "/check-coupon-code", params={"coupon_code": " "}).error == "BAD_REQUEST")


@case("Server prices the booking itself (client sent 1.0)")
def pricing(t):
    t.need("adult", "child")
    r = new_booking(adults=2, children=1)
    bid = r.data.get("booking_master_id")
    t.check("booking created", bool(bid), r.json)
    b = booking(bid)
    expected = 2 * t.ctx["adult"] + t.ctx["child"]
    t.check(f"2 adults + 1 child = {expected}", b.get("txn_amount") == expected, b.get("txn_amount"))
    t.check("merchant_info stored without credentials", "client_secret_key" not in str(b.get("merchant_info")), b.get("merchant_info"))
    t.check("client cannot set txn_status", b.get("txn_status") in (None, 0, 1), b.get("txn_status"))


@case("Percentage coupon applies, capped at its maximum")
def coupon_pricing(t):
    t.need("adult", "child")
    gross = 2 * t.ctx["adult"] + t.ctx["child"]
    r = new_booking(adults=2, children=1, coupon={"code": "DgePay10", "discount_type": 1, "discount_value": 10, "max_discount": 15})
    b = booking(r.data.get("booking_master_id"))
    t.check(f"{gross} - min(10%, 15) = {gross - min(gross * 0.1, 15)}", abs(b.get("txn_amount", 0) - (gross - min(gross * 0.1, 15))) < 0.01, b.get("txn_amount"))
    t.check("coupon discount recorded", (b.get("coupon_info") or {}).get("discount_availed") == min(gross * 0.1, 15), b.get("coupon_info"))
    r = new_booking(adults=1, coupon={"code": "  taka50 "})
    t.check("flat coupon: code matched case-insensitively, spaces trimmed", abs(booking(r.data.get("booking_master_id")).get("txn_amount", -1) - max(t.ctx["adult"] - 50, 0)) < 0.01, r.json)


@case("Invalid bookings are rejected")
def rejects(t):
    t.check("unknown coupon -> INVALID_COUPON_CODE", new_booking(coupon={"code": "NOPE"}).error == "INVALID_COUPON_CODE")
    t.check("no adult/child -> SELECT_AT_LEAST_ONE_ADULT_OR_CHILD", new_booking(adults=0, children=0).error == "SELECT_AT_LEAST_ONE_ADULT_OR_CHILD")
    t.check("negative quantity -> INVALID_TICKET_QUANTITY", new_booking(adults=-1, children=2).error == "INVALID_TICKET_QUANTITY")
    t.check("fractional quantity -> INVALID_TICKET_QUANTITY", new_booking(adults=1.5).error == "INVALID_TICKET_QUANTITY")


@case("Unpaid booking: ticket PDF refused")
def unpaid(t):
    bid = new_booking().data.get("booking_master_id")
    r = pub("POST", "/ticket-booking-report", body={"txn_id": "x", "booking_master_id": bid, "report_type": 1})
    t.check("PAYMENT_NOT_COMPLETED", r.error == "PAYMENT_NOT_COMPLETED", r.json)
    t.ctx["unpaid_booking"] = bid
