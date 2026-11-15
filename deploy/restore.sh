#!/usr/bin/env bash
# Restore a pandawords.site archive into this deployment (operator-only; no web/API equivalent).
#
#   bash restore.sh /path/to/site-YYYYMMDDTHHMMSSffffffZ.tar.gz
#
# Run from the directory holding compose.yml and .env. Stages:
#   preflight  verify the archive (format, version, paths, sizes, sha256) - nothing changes
#   stop       stop web/api/worker/backup so nothing writes during the restore
#   restore    export the current database (pre-restore-*.surql in the site-backups volume),
#              import into an empty database, swap in the media volume, verify both
#   restart    start every service again (migrate upgrades an older archive's schema)
# Any failure exits nonzero naming the stage; services stay stopped after a failed restore.
set -Eeuo pipefail

COMPOSE=${COMPOSE:-docker compose}
stage="arguments"
stopped=0

fail() {
    local code=$?
    echo "RESTORE FAILED at stage '${stage}' (exit ${code})." >&2
    case "${stage}" in
        arguments) echo "Usage: bash restore.sh <archive.tar.gz>" >&2 ;;
        preflight) echo "The archive was rejected; nothing was changed. Use a valid archive." >&2 ;;
        stop) echo "Could not stop writers; nothing was restored. Check: ${COMPOSE} ps" >&2 ;;
        restore)
            echo "Database/media may be partially restored. Services remain stopped." >&2
            echo "Fix the reported cause, then rerun this script with the same archive." >&2
            echo "The previous database export is in the site-backups volume (pre-restore-*)." >&2
            ;;
        restart) echo "Restore was verified but services did not become healthy: ${COMPOSE} ps / logs" >&2 ;;
    esac
    if [[ ${stopped} -eq 1 && ${stage} != "restart" ]]; then
        echo "Start services manually only after a successful restore: ${COMPOSE} up -d" >&2
    fi
    exit 1
}
trap fail ERR

if [[ $# -ne 1 || ! -f $1 ]]; then
    false
fi
archive=$(realpath -- "$1")
if [[ ! -f compose.yml || ! -f .env ]]; then
    echo "Run from the deployment directory (compose.yml and .env)." >&2
    false
fi

run_core() {
    # The archive streams over stdin, so it need not be readable by the container user.
    ${COMPOSE} run --rm --no-deps -T backup python -m app.backup "$@" - <"${archive}"
}

stage="preflight"
if [[ -f "${archive}.sha256" ]]; then
    expected=$(cut -d' ' -f1 <"${archive}.sha256")
    actual=$(sha256sum -- "${archive}" | cut -d' ' -f1)
    [[ ${expected} == "${actual}" ]] || { echo "Archive does not match ${archive}.sha256" >&2; false; }
fi
${COMPOSE} up -d --wait surrealdb
run_core check

stage="stop"
${COMPOSE} stop web api worker backup
stopped=1

stage="restore"
run_core restore --replace

stage="restart"
${COMPOSE} up -d
ready=0
for _ in $(seq 1 60); do
    if ${COMPOSE} exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/readyz', timeout=3).close()" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 5
done
[[ ${ready} -eq 1 ]]
trap - ERR
echo "Restore completed, verified and services restarted."
