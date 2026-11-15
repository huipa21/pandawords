param([string]$ApiImage = 'localhost/pandawords-api:phase45-validation')

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$id = [guid]::NewGuid().ToString('N').Substring(0, 12)
$scratch = Join-Path (Get-Location) ".security-hardening-$id"
$network = "pw-security-$id"
$volume = "pw-security-media-$id"
$database = "pw-security-db-$id"
$api = "pw-security-api-$id"
$web = "pw-security-web-$id"
$ingress = "pw-security-ingress-$id"
$created = [System.Collections.Generic.List[string]]::new()
$networkCreated = $false
$volumeCreated = $false
$password = "Security-$([guid]::NewGuid().ToString('N'))-123!"
$databasePassword = [guid]::NewGuid().ToString('N')
$jwt = "$([guid]::NewGuid().ToString('N'))$([guid]::NewGuid().ToString('N'))"
$octets = @(Get-Random -Minimum 80 -Maximum 220), @(Get-Random -Minimum 1 -Maximum 250)
$prefix = "10.$($octets[0]).$($octets[1])"
$webIp = "$prefix.3"
$ingressIp = "$prefix.4"
$databaseImage = 'docker.io/surrealdb/surrealdb:v3.3.5'
$webImage = 'docker.io/library/nginx:1.30-alpine'

function Invoke-Podman {
    & podman @args
    if ($LASTEXITCODE -ne 0) { throw "podman $($args[0]) failed ($LASTEXITCODE)" }
}

function Start-OwnedContainer {
    param([string]$Name, [string[]]$Arguments)
    Invoke-Podman run --detach --pull=never --name $Name @Arguments | Out-Null
    $created.Add($Name)
}

function Invoke-Probe {
    param([string]$Peer, [string]$Target, [int]$Allowed)
    $program = @'
import json
import sys
import urllib.error
import urllib.request

target, allowed = sys.argv[1], int(sys.argv[2])
for index in range(allowed + 1):
    headers = {
        "X-Panda-Client-IP": f"203.0.113.{(index % 250) + 1}",
        "X-Forwarded-For": f"198.51.100.{(index % 250) + 1}",
        "X-Real-IP": f"192.0.2.{(index % 250) + 1}",
    }
    request = urllib.request.Request(target + "/api/projects", headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status = response.status
        if index < allowed:
            assert status == 401, (index, status)
        else:
            assert status == 429, status
            assert int(response.headers["Retry-After"]) > 0
            assert response.headers["Cache-Control"] == "no-store"
            assert json.load(response) == {
                "code": "http.too_many_requests",
                "message": "Too many requests.",
                "field": None,
            }
print("Spoofed IPs shared one bounded bucket with a standard 429.")
'@
    $program | & podman run --rm -i --pull=never --network $network --ip $Peer `
        --entrypoint python $ApiImage - $Target $Allowed
    if ($LASTEXITCODE -ne 0) { throw 'Proxy identity probe failed.' }
}

try {
    New-Item -ItemType Directory -Path $scratch, (Join-Path $scratch 'browser') | Out-Null
    Invoke-Podman network create --subnet "$prefix.0/24" $network | Out-Null
    $networkCreated = $true
    Invoke-Podman volume create $volume | Out-Null
    $volumeCreated = $true
    Start-OwnedContainer $database @(
        '--network', $network, '--ip', "$prefix.2", '--network-alias', 'db',
        $databaseImage, 'start', '--bind', '0.0.0.0:8000',
        '--user', 'root', '--pass', $databasePassword, 'memory'
    )
    Start-OwnedContainer $api @(
        '--network', $network, '--ip', "$prefix.5", '--network-alias', 'api',
        '--user', '0:0', '--volume', "${volume}:/data/media",
        '--env', 'APP_ENV=production', '--env', 'SURREAL_URL=ws://db:8000/rpc',
        '--env', 'SURREAL_NAMESPACE=security', '--env', 'SURREAL_DATABASE=isolated',
        '--env', 'SURREAL_USER=root', '--env', "SURREAL_PASS=$databasePassword",
        '--env', "JWT_SECRET=$jwt", '--env', "ADMIN_PASSWORD=$password",
        '--env', 'MEDIA_DIR=/data/media', '--env', 'LEXICON_PATH=/data/lexicon-fixture.sqlite',
        '--env', 'AUDIO_NETWORK_ENABLED=false', '--env', 'RATE_LIMIT_ANONYMOUS=20',
        '--env', "TRUSTED_PROXY_CIDRS=[`"$webIp/32`"]",
        '--entrypoint', 'sh', $ApiImage, '-c',
        'while [ ! -f /app/backend/security.ready ]; do sleep 0.1; done; exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-proxy-headers --no-access-log'
    )
    Invoke-Podman exec $api rm -rf /app/backend/app
    Invoke-Podman cp backend\app "${api}:/app/backend/app"
    Invoke-Podman cp backend\tests\fixtures\lexicon_small.sqlite "${api}:/data/lexicon-fixture.sqlite"

    $databaseReady = $false
    for ($i = 0; $i -lt 60; $i++) {
        & podman exec $database /surreal is-ready --endpoint ws://127.0.0.1:8000 *> $null
        if ($LASTEXITCODE -eq 0) { $databaseReady = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $databaseReady) { throw 'The isolated database did not become ready.' }

    $seed = @'
import asyncio
from app.core.config import Settings
from app.db.client import database_lifespan
from app.db.migrate import run_migrations
from app.domain.auth import UserCreate
from app.services.auth import create_user

async def main():
    settings = Settings()
    async with database_lifespan(settings) as database:
        connection = await database.get_connection()
        await run_migrations(connection)
        await create_user(connection, UserCreate(
            username="securityfixture", password=settings.admin_password, role="user",
            must_change_password=False,
        ))

asyncio.run(main())
'@
    $seed | & podman exec -i $api python -
    if ($LASTEXITCODE -ne 0) { throw 'The isolated database fixture failed.' }
    Invoke-Podman exec $api touch /app/backend/security.ready

    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        & podman exec $api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/readyz', timeout=2)" *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'The isolated API did not become ready.' }

    Start-OwnedContainer $web @(
        '--network', $network, '--ip', $webIp, '--network-alias', 'web',
        '--volume', "${volume}:/data/media:ro", '--entrypoint', 'sh', $webImage, '-c',
        'while [ ! -f /etc/nginx/conf.d/security.ready ]; do sleep 0.1; done; exec nginx -g "daemon off;"'
    )
    Invoke-Podman exec $web sed -i 's/worker_processes  auto;/worker_processes  1;/' /etc/nginx/nginx.conf
    Invoke-Podman exec $web mkdir -p /etc/nginx/proxy-trust
    Invoke-Podman cp deploy\nginx.conf "${web}:/etc/nginx/conf.d/default.conf"
    Invoke-Podman cp frontend\dist\. "${web}:/usr/share/nginx/html"
    @"
set_real_ip_from $ingressIp/32;
real_ip_header X-Panda-Client-IP;
real_ip_recursive off;
"@ | Set-Content -Encoding utf8 (Join-Path $scratch 'trusted.conf')
    Invoke-Podman cp (Join-Path $scratch 'trusted.conf') "${web}:/etc/nginx/proxy-trust/trusted.conf"
    Invoke-Podman exec $web nginx -t
    Invoke-Podman exec $web touch /etc/nginx/conf.d/security.ready

    Start-OwnedContainer $ingress @(
        '--network', $network, '--ip', $ingressIp, '--network-alias', 'ingress',
        '-p', '127.0.0.1::80',
        '--entrypoint', 'sh', $webImage, '-c',
        'while [ ! -f /etc/nginx/conf.d/security.ready ]; do sleep 0.1; done; exec nginx -g "daemon off;"'
    )
    Invoke-Podman exec $ingress sed -i 's/worker_processes  auto;/worker_processes  1;/' /etc/nginx/nginx.conf
    @'
server {
    listen 80;
    server_name _;
    access_log off;
    location / {
        proxy_pass http://web:80;
        proxy_set_header Host $host;
        proxy_set_header X-Panda-Client-IP $remote_addr;
    }
}
'@ | Set-Content -Encoding utf8 (Join-Path $scratch 'ingress.conf')
    Invoke-Podman cp (Join-Path $scratch 'ingress.conf') "${ingress}:/etc/nginx/conf.d/default.conf"
    Invoke-Podman exec $ingress nginx -t
    Invoke-Podman exec $ingress touch /etc/nginx/conf.d/security.ready
    $bound = Invoke-Podman port $ingress 80
    if ($bound -notmatch '^127\.0\.0\.1:(\d+)$') { throw 'Unexpected isolated ingress binding.' }
    $env:PANDAWORDS_SECURITY_BASE_URL = "http://127.0.0.1:$($Matches[1])"
    $env:PANDAWORDS_SECURITY_PASSWORD = $password
    $env:TEMP = Join-Path $scratch 'browser'
    $env:TMP = $env:TEMP
    $env:TMPDIR = $env:TEMP

    $responsive = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $response = Invoke-WebRequest "$env:PANDAWORDS_SECURITY_BASE_URL/api/healthz" -NoProxy -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $responsive = $true; break }
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $responsive) { throw 'The isolated production proxy did not become responsive.' }
    $logProbe = @'
from http.client import HTTPConnection

connection = HTTPConnection("web", timeout=10)
connection.putrequest("POST", "/api/images/senses/unused?private=synthetic-private-content-probe")
connection.putheader("Content-Length", str(12 * 1024 * 1024))
connection.endheaders()
response = connection.getresponse()
assert response.status == 413
response.read()
connection.close()
'@
    $logProbe | & podman exec -i $api python -
    if ($LASTEXITCODE -ne 0) { throw 'Nginx request-log privacy probe failed.' }
    $webLogs = & podman logs $web 2>&1 | Out-String
    if ($webLogs.Contains('synthetic-private-content-probe')) {
        throw 'Nginx logged a synthetic private query during an error.'
    }
    node scripts\test-security-browser.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Production proxy/browser checks failed.' }

    Invoke-Probe "$prefix.6" 'http://web' 20
    Invoke-Probe "$prefix.7" 'http://ingress' 20
    Invoke-Probe "$prefix.8" 'http://ingress' 20
}
finally {
    for ($i = $created.Count - 1; $i -ge 0; $i--) {
        & podman rm -f $created[$i] *> $null
        if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove owned container $($created[$i])." }
    }
    if ($volumeCreated) {
        & podman volume rm $volume *> $null
        if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove owned volume $volume." }
    }
    if ($networkCreated) {
        & podman network rm $network *> $null
        if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove owned network $network." }
    }
    if (Test-Path $scratch) {
        if ((Get-Item $scratch -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw 'Refusing to remove a reparse-point scratch directory.'
        }
        if (Get-ChildItem $scratch -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue) {
            throw 'Refusing to traverse reparse points in the scratch directory.'
        }
        Remove-Item $scratch -Recurse -Force
    }
}
