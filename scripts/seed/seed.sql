-- =====================================================================================================================
-- DITF dev seed data. Idempotent: removes its own rows and inserts them again. Dev databases only.
-- Needs the schema (seed.ps1 applies dg-tms-api/src/main/resources/db/schema.sql when it is missing).
-- Run it with scripts/seed/seed.ps1. Every seeded login PIN is 1234 (merchant staff, role 4, have no PIN).
--
-- The data is meant to look real: ids are 32-hex like the app's own. The script recognises its rows by the id prefix
-- 5eed5eed (pg_temp.sid below); a real random id collides with that with probability 2^-32. Rows from the first
-- version of this seed used ids starting 'seed-'; they are removed too.
-- Deterministic: no random(); the same file always gives the same rows (dates are relative to "now").
-- =====================================================================================================================
\set ON_ERROR_STOP on
BEGIN;

CREATE FUNCTION pg_temp.sid(k text) RETURNS text LANGUAGE sql IMMUTABLE AS
$$ SELECT '5eed5eed' || substr(md5(k), 1, 24) $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- Clean previous seed rows
-- ---------------------------------------------------------------------------------------------------------------------
DELETE FROM ticket_scans            WHERE barcode_id LIKE '5eed5eed%' OR barcode_id LIKE 'seed-%';
DELETE FROM staff_qr_scan_history   WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM staff_qr_codes          WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM staff_qr_generator      WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM qr_codes_collector      WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM merchant_stall_master   WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM background_job          WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM user_ticket_generator   WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM user_transaction_ledger WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM booking_barcode_details WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM booking_master          WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM user_referral_codes     WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM report_export_files     WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM booking_user_master     WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';
DELETE FROM booking_configs         WHERE id LIKE '5eed5eed%' OR id LIKE 'seed-%';

CREATE TEMP TABLE seed_ctx ON COMMIT DROP AS SELECT extract(epoch FROM now())::bigint AS ts;

-- ---------------------------------------------------------------------------------------------------------------------
-- Booking config: prices, bus routes (DITF is the fixed stop), coupons. The newest active row wins.
-- ---------------------------------------------------------------------------------------------------------------------
INSERT INTO booking_configs (id, adult_price, child_price, max_ticket_quantity, pickup_points, drop_points,
                             seat_price_matrix, max_seat_count, coupon_codes, merchant_info,
                             is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('cfg-' || v.k), v.adult, v.child, 10, to_jsonb(p.pts), to_jsonb(p.pts),
       (SELECT jsonb_object_agg(x.a, (SELECT jsonb_object_agg(y.b, 100 + 30 * abs(x.i - y.j))
                                      FROM unnest(p.pts) WITH ORDINALITY y(b, j) WHERE y.j <> x.i))
        FROM unnest(p.pts) WITH ORDINALITY x(a, i)),
       4,
       '[{"code":"DgePay10","discount_type":1,"discount_value":10,"max_discount":15},
         {"code":"TAKA50","discount_type":2,"discount_value":50,"max_discount":50}]'::jsonb,
       '{"merchant_id":"1502418a38c547ed90d55e2028fe3fc4","merchant_name":"Dhaka International Trade Fair"}'::jsonb,
       v.active, c.ts - v.age, pg_temp.sid('user-3-1'), c.ts - v.age, pg_temp.sid('user-3-1')
FROM (VALUES ('1', 200, 100, true, 60), ('old', 150, 80, false, 90 * 86400)) v(k, adult, child, active, age)
CROSS JOIN seed_ctx c
CROSS JOIN (SELECT ARRAY['Uttara','Mirpur','Gulshan','Mohakhali','Farmgate','Motijheel','DITF'] AS pts) p;

-- ---------------------------------------------------------------------------------------------------------------------
-- Users: phone = 0190000 + role + 3-digit index, e.g. admin 01900003001, agent 3 = 01900001003. PIN 1234.
-- ---------------------------------------------------------------------------------------------------------------------
INSERT INTO booking_user_master (id, first_name, last_name, dial_code, phone_number, login_pin, user_role, balance,
                                 printer_type, staff_qr_string, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('user-' || t.r || '-' || i),
       (ARRAY['Rahim','Karim','Abdul','Mohammad','Shahidul','Nusrat','Salma','Farhana','Jannat','Tanvir',
              'Sakib','Imran','Mitu','Rubel','Sumon','Nasrin','Tasnim','Arif','Mehedi','Sadia'])[1 + (i * 7 + t.r * 3) % 20],
       (ARRAY['Hossain','Ahmed','Rahman','Islam','Chowdhury','Uddin','Khan','Akter','Begum','Sarker',
              'Mia','Sheikh','Talukder','Mollah','Biswas','Das','Roy','Haque','Alam','Siddique'])[1 + (i * 11 + t.r * 5) % 20],
       '+88', '0190000' || t.r || lpad(i::text, 3, '0'),
       CASE WHEN t.r = 4 THEN NULL ELSE '1234' END, t.r, 0,
       CASE WHEN t.r IN (1, 2, 7) THEN 1 + i % 2 END,
       CASE WHEN t.r = 4 THEN md5('staffqr-' || i) END,
       true, c.ts - 20 * 86400, pg_temp.sid('user-3-1'), c.ts - 20 * 86400, pg_temp.sid('user-3-1')
FROM (VALUES (3, 1), (5, 3), (6, 2), (7, 4), (8, 2), (2, 6), (1, 10), (4, 10)) t(r, cnt),
     generate_series(1, t.cnt) i
CROSS JOIN seed_ctx c;

-- One deactivated (soft-deleted) user per role: they must not be able to log in and must not appear in lists.
INSERT INTO booking_user_master (id, first_name, last_name, dial_code, phone_number, login_pin, user_role, balance,
                                 printer_type, staff_qr_string, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('user-' || r || '-99'),
       (ARRAY['Jashim','Kabir','Lutfur','Monir','Nazrul','Parvez','Shafiq','Zahid'])[r],
       (ARRAY['Bhuiyan','Mondal','Patwary','Khondokar','Majumder','Sikder','Dewan','Gazi'])[r],
       '+88', '0190000' || r || '099',
       CASE WHEN r = 4 THEN NULL ELSE '1234' END, r, 0, NULL, CASE WHEN r = 4 THEN md5('staffqr-99') END,
       false, c.ts - 30 * 86400, pg_temp.sid('user-3-1'), c.ts - 3 * 86400, pg_temp.sid('user-3-1')
FROM generate_series(1, 8) r CROSS JOIN seed_ctx c;

-- ---------------------------------------------------------------------------------------------------------------------
-- Referral users (the last one is deactivated and unused)
-- ---------------------------------------------------------------------------------------------------------------------
INSERT INTO user_referral_codes (id, first_name, last_name, phone_number, referral_code, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('ref-' || i),
       (ARRAY['Mahmud','Shirin','Rafiq','Laila','Habib','Rumana','Kamal','Dilara','Obaid'])[i],
       (ARRAY['Ali','Begum','Uddin','Khatun','Mia','Parvin','Hasan','Sultana','Rahman'])[i],
       '01880000' || lpad(i::text, 3, '0'), lpad(i::text, 3, '0'),
       i <> 9, c.ts - 25 * 86400, pg_temp.sid('user-3-1'), c.ts - 25 * 86400, pg_temp.sid('user-3-1')
FROM generate_series(1, 9) i CROSS JOIN seed_ctx c;

-- ---------------------------------------------------------------------------------------------------------------------
-- Bulk ticket batches (1, 2 active; 3 generated but inactive, ready to activate; 4 still running; 5 failed)
-- ---------------------------------------------------------------------------------------------------------------------
INSERT INTO user_ticket_generator (id, user_id, total_no_of_tickets, ticket_type, last_activated_date, batch_number,
                                   is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('batch-' || v.k), pg_temp.sid('user-8-' || (1 + v.k % 2)), v.total, v.ttype,
       CASE WHEN v.active THEN c.ts - (5 - v.k) * 86400 + 3600 END, 'BT00' || v.k,
       v.active, c.ts - (6 - v.k) * 86400, pg_temp.sid('user-8-1'), c.ts - (6 - v.k) * 86400, pg_temp.sid('user-8-1')
FROM (VALUES (1, 25, 1, true), (2, 25, 2, true), (3, 25, 1, false), (4, 25, 2, false), (5, 25, 1, false)) v(k, total, ttype, active)
CROSS JOIN seed_ctx c;

INSERT INTO background_job (id, job_type, status, reference_id, message, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('job-' || v.k), 'ticket_batch', v.status, pg_temp.sid('batch-' || v.k), v.msg,
       true, c.ts - (6 - v.k) * 86400, pg_temp.sid('user-8-1'), c.ts - (6 - v.k) * 86400 + 60, pg_temp.sid('user-8-1')
FROM (VALUES (1, 2, 'User Tickets Generated Successfully'),
             (2, 2, 'User Tickets Generated Successfully'),
             (3, 2, 'User Tickets Generated Successfully'),
             (4, 1, 'Tickets Generation Process has been Started..'),
             (5, 3, 'Ticket generation failed')) v(k, status, msg)
CROSS JOIN seed_ctx c;

-- ---------------------------------------------------------------------------------------------------------------------
-- Bookings (one working table, then split into booking_master / barcodes / scans / ledger).
--   n 1-5 are "golden" web bookings: 1 paid+unscanned, 2 pending, 3 failed, 4 paid+already scanned, 5 never initiated.
--   Others: ~60% web (platform 1 and 2, online), ~40% agent sales (platform 3, cash, wallet debit). Then bulk (platform 4).
-- ---------------------------------------------------------------------------------------------------------------------
CREATE TEMP TABLE seed_b ON COMMIT DROP AS
WITH w AS (
    SELECT n, c.ts,
           CASE WHEN n % 10 < 4 THEN 1 WHEN n % 10 < 6 THEN 2 ELSE 3 END AS platform
    FROM generate_series(1, 300) n CROSS JOIN seed_ctx c
), s AS (
    SELECT w.*,
           CASE WHEN platform = 3 THEN 3
                WHEN n = 1 THEN 3 WHEN n = 2 THEN 1 WHEN n = 3 THEN 4 WHEN n = 4 THEN 3 WHEN n = 5 THEN NULL
                WHEN n % 53 = 0 THEN 6
                ELSE CASE (n / 3) % 20 WHEN 13 THEN 1 WHEN 14 THEN 1 WHEN 15 THEN 2 WHEN 16 THEN 4 WHEN 17 THEN 4
                                 WHEN 18 THEN 5 WHEN 19 THEN NULL ELSE 3 END
           END AS status,
           -- n > 5 keeps the golden bookings ordinary; every 21st is bus-only, every 11th child-only
           CASE WHEN n > 5 AND n % 21 = 0 THEN 0 WHEN n > 5 AND n % 11 = 0 THEN 0 ELSE 1 + n % 4 END AS adults,
           CASE WHEN n > 5 AND n % 21 = 0 THEN 0 WHEN n > 5 AND n % 11 = 0 THEN 1 + n % 2 ELSE n % 3 END AS children,
           CASE WHEN n % 3 = 0 THEN 1 + (n / 3) % 3 ELSE 0 END AS seats,
           1 + n % 6 AS pi
    FROM w
), t AS (
    SELECT s.*,
           CASE WHEN n % 2 = 0 THEN (ARRAY['Uttara','Mirpur','Gulshan','Mohakhali','Farmgate','Motijheel'])[pi] ELSE 'DITF' END AS pickup,
           CASE WHEN n % 2 = 0 THEN 'DITF' ELSE (ARRAY['Uttara','Mirpur','Gulshan','Mohakhali','Farmgate','Motijheel'])[pi] END AS dropp,
           (100 + 30 * pi) AS bus_price
    FROM s
), u AS (
    SELECT t.*, adults * 200 + children * 100 AS fair_amt, seats * bus_price AS bus_amt,
           CASE WHEN platform = 3 THEN 0 WHEN n % 9 = 0 THEN 1 WHEN n % 13 = 0 THEN 2 ELSE 0 END AS cpn   -- 1 = 10%, 2 = 50 taka
    FROM t
)
SELECT pg_temp.sid('bk-' || n) AS id, n, platform::smallint AS platform,
       (CASE WHEN platform = 3 THEN 1 ELSE 2 END)::smallint AS channel, status::smallint AS status,
       ts - (n % 14) * 86400 - (n * 3137) % 80000 AS created,
       adults, children, seats, CASE WHEN seats > 0 THEN pickup END AS pickup, CASE WHEN seats > 0 THEN dropp END AS dropp,
       fair_amt::numeric AS fair_amt, bus_amt::numeric AS bus_amt,
       (CASE cpn WHEN 1 THEN LEAST(15, round((fair_amt + bus_amt) * 0.10, 2)) WHEN 2 THEN 50 ELSE 0 END)::numeric AS coupon_amt,
       (fair_amt + bus_amt - CASE cpn WHEN 1 THEN LEAST(15, round((fair_amt + bus_amt) * 0.10, 2)) WHEN 2 THEN 50 ELSE 0 END)::numeric AS amount,
       CASE WHEN n % 5 = 0 THEN lpad((1 + n % 8)::text, 3, '0') END AS ref,
       CASE WHEN platform = 3 THEN pg_temp.sid('user-1-' || (1 + n % 9)) END AS booked_by,   -- agent 10 never sells: zero balance
       NULL::text AS batch,
       CASE WHEN n <= 5 THEN '0171100000' || n
            WHEN platform = 3 AND n % 2 = 1 THEN NULL
            ELSE '01' || (3 + n % 7) || lpad(((n * 104729) % 100000000)::text, 8, '0') END AS phone,
       COALESCE(status = 3 AND CASE WHEN n = 4 THEN true WHEN n = 1 THEN false ELSE n % 5 IN (0, 1) END, false) AS scanned,
       true AS bc_active,
       '77' || lpad(n::text, 8, '0') AS bno,
       '2' || lpad((100000 + n)::text, 11, '0') AS fair_bc,
       CASE WHEN seats > 0 THEN '1' || lpad((100000 + n)::text, 11, '0') END AS bus_bc,
       pg_temp.sid('user-2-' || (1 + n % 6)) AS scanner,
       ts, cpn
FROM u;

-- bulk (admin generated) bookings: one cash booking + one inactive-until-activated barcode per ticket
INSERT INTO seed_b
SELECT pg_temp.sid('bkb-' || k), 1000 + k, 4::smallint, 1::smallint, 3::smallint,
       c.ts - (6 - b) * 86400 + 600 - k,
       CASE WHEN b IN (1, 3) THEN 1 ELSE 0 END, CASE WHEN b IN (1, 3) THEN 0 ELSE 1 END, 0, NULL, NULL,
       (CASE WHEN b IN (1, 3) THEN 200 ELSE 100 END)::numeric, 0::numeric, 0::numeric,
       (CASE WHEN b IN (1, 3) THEN 200 ELSE 100 END)::numeric,
       NULL, pg_temp.sid('user-8-' || (1 + b % 2)), pg_temp.sid('batch-' || b), NULL,
       (b IN (1, 2) AND k % 3 = 0), b IN (1, 2),
       '88' || lpad(k::text, 8, '0'), '2' || lpad((500000 + k)::text, 11, '0'), NULL,
       pg_temp.sid('user-2-' || (1 + k % 6)), c.ts, 0
FROM (SELECT b, row_number() OVER (ORDER BY b, j) AS k
      FROM (VALUES (1, 25), (2, 25), (3, 25), (4, 5)) v(b, cnt), generate_series(1, v.cnt) j) bk
CROSS JOIN seed_ctx c;

INSERT INTO booking_master (id, booking_number, booking_request_id, txn_amount, trade_fair_ticket_booking_info,
                            bus_ticket_booking_info, coupon_info, merchant_info, booked_by, platform, payment_channel,
                            user_ticket_generator_id, user_referral_code, txn_id, txn_number, txn_ref_no, txn_ledger_id,
                            txn_status, payment_attempt_ids, payment_method, payment_gateway_response, payment_settled_by,
                            payment_updated_date, is_active, created_date, created_by, updated_date, updated_by)
SELECT b.id, b.bno, CASE WHEN b.platform <> 4 THEN md5('req-' || b.n) END, b.amount,
       CASE WHEN b.adults + b.children > 0 THEN jsonb_strip_nulls(jsonb_build_object(   -- bus-only bookings have no fair info
           'total_adult_quantity', b.adults, 'total_child_quantity', b.children,
           'total_adult_amount', b.adults * 200, 'total_child_amount', b.children * 100,
           'total_trade_fair_booking_amount', b.fair_amt,
           'customer_phone_number', b.phone, 'customer_dial_code', CASE WHEN b.phone IS NOT NULL THEN '+88' END,
           'customer_email', CASE WHEN b.phone IS NOT NULL THEN
               lower((ARRAY['rahim','karim','salma','nusrat','tanvir','mitu','sakib','farhana','imran','jannat'])[1 + b.n % 10]) || b.n || '@gmail.com' END,
           'txn_status', b.status,
           -- every 17th paid booking has no PDF yet (the "ticket still being generated" case)
           'ticket_link', CASE WHEN b.status = 3 AND b.platform <> 4 AND b.n % 17 <> 0 THEN 'https://example.invalid/tickets/' || b.bno || '-fair.pdf' END)) END,
       CASE WHEN b.seats > 0 THEN jsonb_strip_nulls(jsonb_build_object(
           'total_seat', b.seats, 'total_bus_booking_amount', b.bus_amt,
           'pickup_point', b.pickup, 'drop_point', b.dropp,
           'customer_phone_number', b.phone, 'customer_dial_code', CASE WHEN b.phone IS NOT NULL THEN '+88' END,
           'customer_email', CASE WHEN b.phone IS NOT NULL THEN
               lower((ARRAY['rahim','karim','salma','nusrat','tanvir','mitu','sakib','farhana','imran','jannat'])[1 + b.n % 10]) || b.n || '@gmail.com' END,
           'txn_status', b.status,
           'ticket_link', CASE WHEN b.status = 3 THEN 'https://example.invalid/tickets/' || b.bno || '-bus.pdf' END)) END,
       CASE b.cpn WHEN 1 THEN jsonb_build_object('coupon_code', 'DgePay10', 'discount_type', 1,
                                                 'discount_value', 10, 'discount_amount', b.coupon_amt)
                  WHEN 2 THEN jsonb_build_object('coupon_code', 'TAKA50', 'discount_type', 2,
                                                 'discount_value', 50, 'discount_amount', b.coupon_amt) END,
       '{"merchant_id":"1502418a38c547ed90d55e2028fe3fc4","merchant_name":"Dhaka International Trade Fair"}'::jsonb,
       b.booked_by, b.platform, b.channel, b.batch, b.ref,
       CASE WHEN b.platform IN (1, 2) AND b.status IN (3, 6) THEN md5('txn-' || b.n) END,
       CASE WHEN b.platform IN (1, 2) AND b.status IN (3, 6) THEN 'TXN' || lpad(b.n::text, 8, '0') END,
       CASE WHEN b.platform IN (1, 2) AND b.status IN (3, 6) THEN 'DGP' || lpad((b.n * 7919 % 1000000)::text, 6, '0') END,
       CASE WHEN b.platform = 3 THEN pg_temp.sid('led-d-' || b.n) END,
       b.status,
       -- every 7th online booking retried the payment: two checkout ids
       CASE WHEN b.platform IN (1, 2) AND b.status IS NOT NULL
            THEN jsonb_build_array('DITF' || lpad((b.n * 48271 % 100000000)::text, 8, '0'))
                 || CASE WHEN b.n % 7 = 1 THEN jsonb_build_array('DITF' || lpad((b.n * 69621 % 100000000)::text, 8, '0')) ELSE '[]'::jsonb END END,
       CASE WHEN b.platform IN (1, 2) AND b.status IN (3, 6) THEN (ARRAY['bKash','Nagad','Rocket','Visa','Mastercard'])[1 + b.n % 5]
            WHEN b.platform IN (3, 4) THEN 'Cash' END,
       CASE WHEN b.platform IN (1, 2) AND b.status IS NOT NULL
            THEN jsonb_build_object('status_code', b.status,
                     'message', CASE b.status WHEN 3 THEN 'Payment successful' WHEN 1 THEN 'Payment pending'
                                              WHEN 2 THEN 'Payment processing' WHEN 4 THEN 'Payment failed'
                                              WHEN 5 THEN 'Payment rejected' ELSE 'Payment refunded' END) END,
       CASE WHEN b.platform = 3 THEN 'AGENT' END,
       CASE WHEN b.status IS NOT NULL THEN b.created + 120 END,
       (b.n % 61 <> 0 OR b.platform = 4),   -- every 61st booking is soft-deleted
       b.created, b.booked_by, b.created, b.booked_by
FROM seed_b b;

INSERT INTO booking_barcode_details (id, booking_master_id, booking_number, trade_fair_ticket_barcode,
                                     trade_fair_ticket_barcode_valid, trade_fair_ticket_barcode_scanned_date,
                                     bus_ticket_barcode, bus_ticket_barcode_valid, bus_ticket_barcode_scanned_date,
                                     booking_qr_string, scanned_by, scanned_device, user_ticket_generator_id,
                                     is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('bc-' || b.id), b.id, b.bno, b.fair_bc,
       b.scanned, CASE WHEN b.scanned THEN LEAST(b.ts, b.created + 3600 * (1 + b.n % 6)) END,
       b.bus_bc, b.scanned AND b.bus_bc IS NOT NULL AND b.n % 2 = 0,
       CASE WHEN b.scanned AND b.bus_bc IS NOT NULL AND b.n % 2 = 0 THEN LEAST(b.ts, b.created + 3600 * (1 + b.n % 6)) END,
       b.bno || '-' || (b.created * 1000) || '-' || md5(b.id),
       CASE WHEN b.scanned THEN b.scanner END, CASE WHEN b.scanned THEN 'Zebra TC21-0' || (1 + b.n % 6) END,
       b.batch, b.bc_active AND (b.n % 61 <> 0 OR b.platform = 4), b.created, b.booked_by, b.created, b.booked_by
FROM seed_b b;

INSERT INTO ticket_scans (barcode_id, booking_master_id, trade_fair_ticket_barcode, scanned_date, scanned_by,
                          scanned_device, user_ticket_generator_id, adults, children)
SELECT pg_temp.sid('bc-' || b.id), b.id, b.fair_bc, LEAST(b.ts, b.created + 3600 * (1 + b.n % 6)), b.scanner,
       'Zebra TC21-0' || (1 + b.n % 6), b.batch, b.adults, b.children
FROM seed_b b WHERE b.scanned;

-- ---------------------------------------------------------------------------------------------------------------------
-- Agent wallets: top-ups (agents 1-9), a withdrawal for agents 1-3, and a debit per agent sale; balance = credits - debits.
-- Agent 10 has no ledger: balance 0.
-- ---------------------------------------------------------------------------------------------------------------------
INSERT INTO user_transaction_ledger (id, user_id, amount, txn_type, display_text, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('led-c-' || a || '-' || k), pg_temp.sid('user-1-' || a), CASE WHEN k % 2 = 1 THEN 5000 ELSE 10000 END, 1,
       'Balance top-up by admin', true,
       c.ts - (15 - (k - 1) * 4) * 86400, pg_temp.sid('user-3-1'), c.ts - (15 - (k - 1) * 4) * 86400, pg_temp.sid('user-3-1')
FROM generate_series(1, 9) a, generate_series(1, 4) k CROSS JOIN seed_ctx c;

INSERT INTO user_transaction_ledger (id, user_id, amount, txn_type, display_text, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('led-w-' || a), pg_temp.sid('user-1-' || a), 2000, 2, 'Balance withdrawn by admin', true,
       c.ts - 2 * 86400, pg_temp.sid('user-3-1'), c.ts - 2 * 86400, pg_temp.sid('user-3-1')
FROM generate_series(1, 3) a CROSS JOIN seed_ctx c;

INSERT INTO user_transaction_ledger (id, user_id, amount, txn_type, display_text, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('led-d-' || b.n), b.booked_by, b.amount, 2, 'You have successfully booked a ticket.', true,
       b.created, b.booked_by, b.created, b.booked_by
FROM seed_b b WHERE b.platform = 3;

UPDATE booking_user_master u
SET balance = COALESCE((SELECT sum(CASE l.txn_type WHEN 1 THEN l.amount ELSE -l.amount END)
                        FROM user_transaction_ledger l WHERE l.user_id = u.id), 0)
WHERE u.user_role = 1 AND u.id LIKE '5eed5eed%';

-- ---------------------------------------------------------------------------------------------------------------------
-- Stalls, QR collectors, staff QR cards and their scan history
-- ---------------------------------------------------------------------------------------------------------------------
INSERT INTO merchant_stall_master (id, stall_name, stall_number, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('stall-' || i),
       (ARRAY['Food Court','Artisan Corner','Textile Hall','Electronics Plaza','Toy World','Book Nook','Garments Pavilion','Handicrafts'])[i],
       'S-' || lpad(i::text, 2, '0'), i <> 8, c.ts - 18 * 86400, pg_temp.sid('user-3-1'), c.ts - 18 * 86400, pg_temp.sid('user-3-1')
FROM generate_series(1, 8) i CROSS JOIN seed_ctx c;

INSERT INTO qr_codes_collector (id, first_name, last_name, phone_number, dial_code, assigned_count, merchant_stall_master_id,
                                is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('coll-' || i), (ARRAY['Anwar','Bilkis','Chand','Delwar','Enam','Firoza'])[i],
       (ARRAY['Hossain','Akter','Mia','Sheikh','Talukder','Nahar'])[i], '01955000' || lpad(i::text, 3, '0'), '+88', 0,
       pg_temp.sid('stall-' || i), i <> 6, c.ts - 17 * 86400, pg_temp.sid('user-6-1'), c.ts - 17 * 86400, pg_temp.sid('user-6-1')
FROM generate_series(1, 6) i CROSS JOIN seed_ctx c;

INSERT INTO staff_qr_generator (id, qr_count, scan_limit, qr_label, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('sqg-' || v.k), v.cnt, v.lim, v.label, true, c.ts - 16 * 86400, pg_temp.sid('user-6-1'), c.ts - 16 * 86400, pg_temp.sid('user-6-1')
FROM (VALUES (1, 30, 1, 'Staff Daily (1 scan)'), (2, 20, 3, 'Vendor (3 scans)'), (3, 10, -1, 'VIP (unlimited)')) v(k, cnt, lim, label)
CROSS JOIN seed_ctx c;

INSERT INTO staff_qr_codes (id, staff_qr_code_number, staff_qr_string, staff_qr_generator_id, scan_limit, is_assigned,
                            qr_codes_collector_id, merchant_stall_master_id, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('sqc-' || k), '5' || lpad(k::text, 10, '0'), md5('sqr-' || k),
       pg_temp.sid('sqg-' || g), CASE g WHEN 1 THEN 1 WHEN 2 THEN 3 ELSE -1 END, k % 2 = 0,
       CASE WHEN k % 2 = 0 THEN pg_temp.sid('coll-' || (1 + (k / 2) % 6)) END,
       CASE WHEN k % 2 = 0 THEN pg_temp.sid('stall-' || (1 + (k / 2) % 6)) END,
       k <> 60, c.ts - 16 * 86400, pg_temp.sid('user-6-1'), c.ts - 16 * 86400, pg_temp.sid('user-6-1')   -- card 60 is deactivated
FROM (SELECT k, CASE WHEN k <= 30 THEN 1 WHEN k <= 50 THEN 2 ELSE 3 END AS g FROM generate_series(1, 60) k) q
CROSS JOIN seed_ctx c;

UPDATE qr_codes_collector q
SET assigned_count = (SELECT count(*) FROM staff_qr_codes s WHERE s.qr_codes_collector_id = q.id)
WHERE q.id LIKE '5eed5eed%';

INSERT INTO staff_qr_scan_history (id, staff_qr_codes_id, scanned_by, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('sqh-' || g), pg_temp.sid('sqc-' || (2 * (1 + g % 30))), pg_temp.sid('user-7-' || (1 + g % 4)), true,
       c.ts - (g % 7) * 86400 - (g * 977) % 80000, pg_temp.sid('user-7-' || (1 + g % 4)),
       c.ts - (g % 7) * 86400 - (g * 977) % 80000, pg_temp.sid('user-7-' || (1 + g % 4))
FROM generate_series(1, 150) g CROSS JOIN seed_ctx c;

-- Card number 50000000004 (1 scan per day) has already used today's scan: a scan now must be refused.
INSERT INTO staff_qr_scan_history (id, staff_qr_codes_id, scanned_by, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('sqh-limit'), pg_temp.sid('sqc-4'), pg_temp.sid('user-7-1'), true, c.ts - 60,
       pg_temp.sid('user-7-1'), c.ts - 60, pg_temp.sid('user-7-1')
FROM seed_ctx c;

-- ---------------------------------------------------------------------------------------------------------------------
-- Report export log
-- ---------------------------------------------------------------------------------------------------------------------
INSERT INTO report_export_files (id, report_name, download_url, user_id, report_date, is_active, created_date, created_by, updated_date, updated_by)
SELECT pg_temp.sid('rpt-' || i), 'ticket-' || (CASE WHEN i % 2 = 1 THEN 'fair-' ELSE 'bus-' END) || '77' || lpad(i::text, 8, '0'),
       'https://example.invalid/reports/' || '77' || lpad(i::text, 8, '0') || '.pdf', pg_temp.sid('user-3-1'),
       c.ts - i * 86400, true, c.ts - i * 86400, pg_temp.sid('user-3-1'), c.ts - i * 86400, pg_temp.sid('user-3-1')
FROM generate_series(1, 5) i CROSS JOIN seed_ctx c;

COMMIT;

-- Summary
SELECT 'booking_configs' t, count(*) FROM booking_configs WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'booking_user_master', count(*) FROM booking_user_master WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'user_transaction_ledger', count(*) FROM user_transaction_ledger WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'user_referral_codes', count(*) FROM user_referral_codes WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'user_ticket_generator', count(*) FROM user_ticket_generator WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'background_job', count(*) FROM background_job WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'booking_master', count(*) FROM booking_master WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'booking_barcode_details', count(*) FROM booking_barcode_details WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'ticket_scans', count(*) FROM ticket_scans WHERE barcode_id LIKE '5eed5eed%'
UNION ALL SELECT 'merchant_stall_master', count(*) FROM merchant_stall_master WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'qr_codes_collector', count(*) FROM qr_codes_collector WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'staff_qr_generator', count(*) FROM staff_qr_generator WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'staff_qr_codes', count(*) FROM staff_qr_codes WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'staff_qr_scan_history', count(*) FROM staff_qr_scan_history WHERE id LIKE '5eed5eed%'
UNION ALL SELECT 'report_export_files', count(*) FROM report_export_files WHERE id LIKE '5eed5eed%';
