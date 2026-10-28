# Starts agentbrowser as a remote MCP connector (HTTP + HTTPS tunnel) so Claude can use it
# from any device, including your phone. Keep this window open; Ctrl+C stops everything.
#
#   powershell -ExecutionPolicy Bypass -File .\start-connector.ps1
#
# Needs cloudflared:  winget install --id Cloudflare.cloudflared

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$port = 8790
$env:AGENTBROWSER_DATA = Join-Path $root ".agentbrowser"
# Separate browser profile from the desktop-app (stdio) server, so both can run at once.
# Skills and discovered APIs are still shared.
$env:AGENTBROWSER_PROFILE = Join-Path $env:AGENTBROWSER_DATA "profile-remote"
if (-not $env:AGENTBROWSER_HEADLESS) { $env:AGENTBROWSER_HEADLESS = "0" }

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared is not installed. Run:  winget install --id Cloudflare.cloudflared" -ForegroundColor Yellow
    Write-Host "then open a NEW PowerShell window and run this script again."
    exit 1
}

$server = Start-Process -FilePath $py -ArgumentList "-m", "agentbrowser.mcp_server", "--http", "--port", "$port" `
    -WorkingDirectory $root -PassThru -NoNewWindow
$tokenFile = Join-Path $env:AGENTBROWSER_DATA "mcp_token.txt"
for ($i = 0; $i -lt 30 -and -not (Test-Path $tokenFile); $i++) { Start-Sleep -Milliseconds 500 }
$token = (Get-Content $tokenFile -Raw).Trim()

$log = Join-Path $env:TEMP "agentbrowser-tunnel.log"
Remove-Item $log -ErrorAction SilentlyContinue
$tunnel = Start-Process cloudflared -ArgumentList "tunnel", "--url", "http://127.0.0.1:$port", "--no-autoupdate", "--logfile", "`"$log`"" `
    -PassThru -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
}

try {
    if (-not $url) { throw "Tunnel did not start. See $log" }
    $connector = "$url/$token/mcp"
    try { Set-Clipboard -Value $connector } catch {}
    Write-Host ""
    Write-Host "agentbrowser connector is live (copied to clipboard):" -ForegroundColor Green
    Write-Host "  $connector" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Add it in Claude: Settings > Connectors > Add custom connector."
    Write-Host "Keep this window open and the laptop awake. Ctrl+C to stop."
    Write-Host "Note: the address changes each time you restart this script; update the connector if so."
    Wait-Process -Id $server.Id
}
finally {
    foreach ($p in @($tunnel, $server)) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
}
