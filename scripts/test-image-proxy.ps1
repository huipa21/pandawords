[CmdletBinding()]
param([Parameter(Mandatory)][string]$ApiImage)

$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 10)
$network = "pw-img-$suffix"
$volume = "pw-img-media-$suffix"
$db = "pw-img-db-$suffix"
$api = "pw-img-api-$suffix"
$proxy = "pw-img-proxy-$suffix"
$savedEnvironment = @{}
foreach ($key in @('SURREAL_URL', 'SURREAL_NAMESPACE', 'SURREAL_DATABASE', 'SURREAL_USER',
    'SURREAL_PASS', 'JWT_SECRET', 'ADMIN_PASSWORD', 'LLM_DAILY_BUDGET', 'AUDIO_NETWORK_ENABLED', 'APP_ENV')) {
    $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key)
}
$env:SURREAL_URL = 'ws://surrealdb:8000/rpc'
$env:SURREAL_NAMESPACE = 'image_proxy'
$env:SURREAL_DATABASE = 'smoke'
$env:SURREAL_USER = 'root'
$env:SURREAL_PASS = [guid]::NewGuid().ToString('N')
$env:JWT_SECRET = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$env:ADMIN_PASSWORD = [guid]::NewGuid().ToString('N')
$env:LLM_DAILY_BUDGET = '0'
$env:AUDIO_NETWORK_ENABLED = 'false'
$env:APP_ENV = 'production'
$environment = @('-e', 'SURREAL_URL', '-e', 'SURREAL_NAMESPACE', '-e', 'SURREAL_DATABASE',
    '-e', 'SURREAL_USER', '-e', 'SURREAL_PASS', '-e', 'JWT_SECRET', '-e', 'ADMIN_PASSWORD',
    '-e', 'LLM_DAILY_BUDGET', '-e', 'AUDIO_NETWORK_ENABLED', '-e', 'APP_ENV')
$image = $ApiImage
function Assert-Native { if ($LASTEXITCODE) { throw "Container command failed ($LASTEXITCODE)" } }
try {
    podman network create $network | Out-Null
    Assert-Native
    podman volume create $volume | Out-Null
    Assert-Native
    podman run --pull=never --detach --name $db --network $network --network-alias surrealdb docker.io/surrealdb/surrealdb:v3.3.5 start --no-banner --log error --user root --pass $env:SURREAL_PASS memory | Out-Null
    Assert-Native
    for ($i = 0; $i -lt 30; $i++) {
        podman exec $db /surreal is-ready --endpoint ws://127.0.0.1:8000 *> $null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep 1
    }
    podman run --pull=never --rm --network $network @environment $image python -m app.db.migrate | Select-Object -Last 2
    Assert-Native
    $bootstrap = @'
import asyncio
from app.core.config import Settings
from app.db.client import database_lifespan
from app.domain.auth import UserCreate
from app.services.auth import create_user
async def run():
    settings=Settings()
    async with database_lifespan(settings) as database:
        db=await database.get_connection()
        await create_user(db,UserCreate(username="proxyuser",password=settings.admin_password,must_change_password=False))
asyncio.run(run())
'@
    $bootstrap | podman run --pull=never --rm -i --network $network @environment $image python -
    Assert-Native
    podman run --pull=never --detach --name $api --network $network --network-alias api @environment --volume "${volume}:/data/media" $image | Out-Null
    Assert-Native
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        podman exec $api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/healthz',timeout=2)" *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep 1
    }
    if (-not $ready) { throw 'Isolated image-test API did not become ready.' }
    podman create --pull=never --name $proxy --network $network --network-alias proxy --volume "${volume}:/data/media:ro" docker.io/library/nginx:1.30-alpine | Out-Null
    Assert-Native
    podman cp deploy\nginx.conf "${proxy}:/etc/nginx/conf.d/default.conf"
    Assert-Native
    podman start $proxy | Out-Null
    Assert-Native
    $probe = @'
import asyncio,io,pathlib,os
import httpx
from PIL import Image
from app.core.config import Settings
from app.core.record_ids import encode_rid
from app.db.client import database_lifespan
from app.db.media_test_support import sense
async def target():
    async with database_lifespan(Settings()) as database:
        return encode_rid(await sense(await database.get_connection()),"sense")
rid=asyncio.run(target())
root=pathlib.Path("/data/media")
print("MEDIA",os.getuid(),root.stat())
out=io.BytesIO()
Image.new("RGB",(4,4),(1,2,3)).save(out,format="PNG")
content=out.getvalue()
content+=b"\0"*(10*1024*1024-len(content))
with httpx.Client(base_url="http://proxy",timeout=60) as client:
    login=client.post("/api/auth/login",json={"username":"proxyuser","password":Settings().admin_password})
    assert login.status_code==200,login.status_code
    client.headers["Authorization"]="Bearer "+login.json()["access_token"]
    path=f"/api/images/senses/{rid}"
    headers={"Content-Type":"image/png","request-id":"proxy-nearlimit-0001"}
    result=client.post(path,content=content,headers=headers)
    print("UPLOAD",result.status_code,result.text[:1000])
    assert result.status_code==200
    media=result.json()["id"]
    delivery=client.get("/api/media/"+media)
    print("DELIVERY",delivery.status_code,len(delivery.content))
    assert delivery.status_code==200 and delivery.content==content
    too_big=client.post(path,content=content+b"\0",headers={**headers,"request-id":"proxy-oversize-0001"})
    print("OVERSIZE",too_big.status_code)
    assert too_big.status_code==413
    removed=client.delete(path+"/"+media)
    print("DELETE",removed.status_code)
    assert removed.status_code==204
    missing=client.get("/api/media/"+media)
    print("REMOVED_DELIVERY",missing.status_code,"FILES",list(root.rglob("*")))
    assert missing.status_code==404
    assert not list(root.rglob("*.png"))
'@
    $probe | podman exec -i $api python -
    Assert-Native
} finally {
    foreach ($container in @($proxy,$api,$db)) { podman rm --force $container 2>$null | Out-Null }
    podman volume rm $volume 2>$null | Out-Null
    podman network rm $network 2>$null | Out-Null
    foreach ($key in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key])
    }
    Pop-Location
}
