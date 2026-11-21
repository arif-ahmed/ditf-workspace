# Plays the customer on the mock DGePay page (needs: .\scripts\dev.ps1 up -MockPayments, and a booking whose
# initiate-payment already worked). Sets the payment's outcome on the mock, then does what DGePay does: sends the
# browser to the API's callback, which verifies it with the mock, marks the booking paid and makes the ticket PDF.
#   .\scripts\mock-pay.ps1                  pay the most recent pending checkout
#   .\scripts\mock-pay.ps1 -Fail            same, but the payment fails (status 4)
#   .\scripts\mock-pay.ps1 -Booking 7641327001
param([string]$Booking, [switch]$Fail)
$ErrorActionPreference = 'Stop'
$where = if ($Booking) { "booking_number = '$($Booking -replace "[^0-9A-Za-z-]", '')'" } else { 'txn_status = 1' }
$id = (docker exec ditf-pg psql -U ditf -d ditf -tA -c "SELECT txn_id FROM booking_master WHERE $where AND txn_id IS NOT NULL ORDER BY payment_updated_date DESC LIMIT 1").Trim()
if (-not $id) { throw 'No booking with a started checkout found. Run initiate-payment (the Pay button) first.' }
$state = Invoke-RestMethod http://127.0.0.1:18080/mock/state   # fails fast if the mock is not running
if (-not $state.checkouts.PSObject.Properties[$id]) { throw "The mock never saw checkout $id (an old attempt, or the API is not using the mock: dev.ps1 up -MockPayments)." }
$body = @{ unique_txn_id = $id; status_code = $(if ($Fail) { 4 } else { 3 }) } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:18080/mock/result -Body $body -ContentType application/json | Out-Null
$r = Invoke-WebRequest "http://localhost:9096/ticket-booking/payment/callback/$id" -MaximumRedirection 0 -SkipHttpErrorCheck
"checkout $id -> callback HTTP $($r.StatusCode)"
if ($r.Headers.Location) { "browser goes to: $($r.Headers.Location)" }
