# Decrypt / encrypt the booking API's AES-128-ECB payloads (platform_secret_key), to read DevTools Network bodies.
#   .\scripts\aes.ps1 d "<base64 from request body or response 'data'>"   -> pretty JSON
#   .\scripts\aes.ps1 e '{"booking_master_id":"abc"}'                      -> base64 to paste into curl
# Pass a whole response like {"success":1,"data":"..."} to d and it decrypts the data field.
param([ValidateSet('d', 'e')][string]$Mode, [Parameter(Mandatory)][string]$Text)
$props = Join-Path $PSScriptRoot '..\dg-tms-api\src\main\resources\application.properties'
$key = (Select-String -Path $props -Pattern '^platform_secret_key=(.+)$').Matches[0].Groups[1].Value.Trim()
$aes = [Security.Cryptography.Aes]::Create()
$aes.Mode = 'ECB'; $aes.Padding = 'PKCS7'; $aes.Key = [Text.Encoding]::UTF8.GetBytes($key)
if ($Mode -eq 'e') {
    $b = [Text.Encoding]::UTF8.GetBytes($Text)
    [Convert]::ToBase64String($aes.CreateEncryptor().TransformFinalBlock($b, 0, $b.Length))
} else {
    $Text = $Text.Trim().Trim('"')
    if ($Text.StartsWith('{')) { $Text = ($Text | ConvertFrom-Json).data }
    $b = [Convert]::FromBase64String($Text)
    $plain = [Text.Encoding]::UTF8.GetString($aes.CreateDecryptor().TransformFinalBlock($b, 0, $b.Length))
    try { $plain | ConvertFrom-Json | ConvertTo-Json -Depth 10 } catch { $plain }
}
