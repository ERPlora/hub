#!/usr/bin/env bash
# Tests of the built hub image against the app ↔ infra contract (aws-next/README.md, «Imagen»).
#   docker buildx build --platform linux/arm64 --provenance=false -t erplora/hub:test --load \
#     --build-arg APP_VERSION="$(git rev-parse HEAD)" --build-arg APP_RELEASED_AT="$(git show -s --format=%cI HEAD)" .
#   bash docker/image.test.sh erplora/hub:test
# Every container runs like on Fargate here: read-only root filesystem, writable /tmp only.
# Conditions are single-quoted on purpose: check() evaluates them later (SC2016, SC2034).
# shellcheck disable=SC2016,SC2034
set -euo pipefail

image="${1:?usage: image.test.sh <image>}"
failures=0
containers=()

cleanup() {
  if [[ ${#containers[@]} -gt 0 ]]; then docker rm -f "${containers[@]}" > /dev/null 2>&1 || true; fi
}
trap cleanup EXIT

docker image inspect "$image" > /dev/null || { echo "FAIL - image $image not found"; exit 1; }

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    failures=$((failures + 1))
  fi
}

# in_image <command…>: a one-off container of the image, as a task would start it.
in_image() { docker run --rm --read-only --tmpfs /tmp "$image" "$@"; }

# The production environment the settings demand (DEBUG off), with dummy values and no database.
PROD_ENV=(-e DEBUG=0 -e SECRET_KEY=x -e ALLOWED_HOSTS=erplora.com -e SAAS_URL=https://erplora.com
  -e INTERNAL_SHARED_SECRET=x -e DB_HOST=db.invalid -e DB_NAME=hub -e DB_USER=x -e DB_PASSWORD=x)

check "built for linux/arm64" '[[ $(docker image inspect -f "{{.Os}}/{{.Architecture}}" "$image") == linux/arm64 ]]'
check "runs as uid 10001" '[[ $(in_image id -u) == 10001 ]]'
check "default command: daphne on 0.0.0.0:8000 behind the proxy headers" '
  cmd="$(docker image inspect -f "{{json .Config.Cmd}}" "$image")"
  [[ $cmd == *daphne* && $cmd == *--proxy-headers* && $cmd == *0.0.0.0* && $cmd == *8000* &&
     $cmd == *config.asgi:application* ]]'
check "python and the live package" 'in_image python -c "import live, django, daphne"'
check "WeasyPrint loads its libraries and prints a PDF" \
  'in_image python -c "import weasyprint; assert weasyprint.HTML(string=\"<p>x</p>\").write_pdf().startswith(b\"%PDF-\")"'
check "Fontconfig finds a writable cache on the read-only filesystem" \
  '! in_image python -c "import weasyprint; weasyprint.HTML(string=\"<p>x</p>\").write_pdf()" 2>&1 | grep -q "Fontconfig error"'
check "pgbouncer is installed" 'in_image pgbouncer --version | grep -qi pgbouncer'
check "pg_isready is the PostgreSQL 18 client" 'in_image pg_isready --version | grep -Eq "\) 18\."'
check "RDS CA bundle, readable by the app user" \
  'in_image sh -c "grep -q \"BEGIN CERTIFICATE\" /etc/ssl/certs/rds-global-bundle.pem"'
check "pgbouncer-entrypoint is an executable on the PATH" \
  '[[ $(in_image sh -c "command -v pgbouncer-entrypoint") == /usr/local/bin/pgbouncer-entrypoint ]] &&
   in_image test -x /usr/local/bin/pgbouncer-entrypoint'
check "pgbouncer-healthcheck is an executable on the PATH" \
  '[[ $(in_image sh -c "command -v pgbouncer-healthcheck") == /usr/local/bin/pgbouncer-healthcheck ]] &&
   in_image test -x /usr/local/bin/pgbouncer-healthcheck'
check "the Vite manifest lists the SPA entry" \
  'in_image python -c "import json; m = json.load(open(\"frontend/dist/.vite/manifest.json\")); assert m[\"frontend/main.ts\"][\"isEntry\"]"'
# With PROD_ENV: without DEBUG nor SECRET_KEY the settings refuse to load (DEBUG is off by default).
check "collectstatic ran: the SPA entry and the admin are in STATIC_ROOT" '
  docker run --rm --read-only --tmpfs /tmp "${PROD_ENV[@]}" "$image" python -c "
import json, os, django
os.environ.setdefault(\"DJANGO_SETTINGS_MODULE\", \"config.settings\")
django.setup()
from django.conf import settings
root = settings.STATIC_ROOT
entry = json.load(open(\"frontend/dist/.vite/manifest.json\"))[\"frontend/main.ts\"][\"file\"]
assert os.path.isfile(root / \"spa\" / entry), entry
assert os.path.isfile(root / \"admin\" / \"css\" / \"base.css\")
"'
check "the modules' documentation images are collected under catalog/<id>/img/" \
  'in_image sh -c "test -f staticfiles/catalog/demo/img/items-list.png && ! test -e staticfiles/catalog/demo/WORKBOOK.md"'
# Round 16 (spec §4.3): the build already ran it; the image carries what it needs (icons, WORKBOOKs, catalogues).
check "register_apps --check passes without any database" \
  'docker run --rm --read-only --tmpfs /tmp "${PROD_ENV[@]}" "$image" python manage.py register_apps --check > /dev/null'
check "the release is fixed in the image: APP_VERSION and APP_RELEASED_AT" '
  env_json="$(docker image inspect -f "{{json .Config.Env}}" "$image")"
  [[ $env_json == *\"APP_VERSION=* && $env_json == *\"APP_RELEASED_AT=* ]]'
check "the translation client is a development dependency only" \
  '! in_image python -c "import anthropic" 2> /dev/null'
check "compilemessages ran: the Spanish catalogues are compiled" \
  'in_image sh -c "test -f base/locale/es/LC_MESSAGES/django.mo"'
check "settings import with DEBUG off: manage.py check" \
  'docker run --rm --read-only --tmpfs /tmp "${PROD_ENV[@]}" "$image" python manage.py check > /dev/null'
# Errors only (warnings are the dummy SECRET_KEY and the HSTS/secure-cookie settings of the app lane).
check "manage.py check --deploy reports no errors" \
  'docker run --rm --read-only --tmpfs /tmp "${PROD_ENV[@]}" "$image" python manage.py check --deploy > /dev/null 2>&1'

# The web answers /healthz (the container healthcheck, verbatim) with a read-only filesystem.
web="$(docker run -d --read-only --tmpfs /tmp "${PROD_ENV[@]}" "$image")"
containers+=("$web")
healthz='import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=3)'
web_up=0
for _ in $(seq 1 30); do
  if docker exec "$web" python -c "$healthz" > /dev/null 2>&1; then web_up=1; break; fi
  sleep 1
done
check "daphne serves /healthz on 8000 with a read-only filesystem" '[[ $web_up -eq 1 ]]'

# The sidecar: same image, `pgbouncer-entrypoint`, the healthcheck of modules/ecs-service verbatim.
healthcheck=(pgbouncer-healthcheck)
bouncer="$(docker run -d --read-only --tmpfs /tmp \
  -e PGBOUNCER_SERVER_HOST=writer.invalid -e PGBOUNCER_SERVER_PORT=5432 -e PGBOUNCER_LISTEN_PORT=6432 \
  -e PGBOUNCER_MAX_USER_CONNECTIONS=40 -e PGBOUNCER_SERVER_TLS_CA_FILE=/etc/ssl/certs/rds-global-bundle.pem \
  -e PGBOUNCER_AUTH_USER=hub_app -e PGBOUNCER_AUTH_PASSWORD='pa"ss' "$image" pgbouncer-entrypoint)"
containers+=("$bouncer")
bouncer_up=0
for _ in $(seq 1 20); do
  if docker exec "$bouncer" "${healthcheck[@]}" 2> /dev/null; then bouncer_up=1; break; fi
  sleep 0.5
done
check "the sidecar's healthcheck passes on 127.0.0.1:6432" '[[ $bouncer_up -eq 1 ]]'
check "the healthcheck leaves no line in the sidecar's log (it ran every 5 s in prod)" '
  before="$(docker logs "$bouncer" 2>&1 | grep -v " LOG stats: ")"
  for _ in 1 2 3; do docker exec "$bouncer" "${healthcheck[@]}"; done
  sleep 1
  [[ $(docker logs "$bouncer" 2>&1 | grep -v " LOG stats: ") == "$before" ]]'
check "the healthcheck defaults to port 6432" \
  'docker exec "$bouncer" env -u PGBOUNCER_LISTEN_PORT "${healthcheck[@]}"'
check "the healthcheck fails where pgbouncer does not listen" \
  '! docker exec -e PGBOUNCER_LISTEN_PORT=6433 "$bouncer" "${healthcheck[@]}" 2> /dev/null'
check "pgbouncer is PID 1's process, not a shell around it" \
  '[[ $(docker exec "$bouncer" cat /proc/1/comm) == pgbouncer ]]'
check "pgbouncer listens on loopback only" '
  ip="$(docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" "$bouncer")"
  [[ -n $ip ]] && ! docker exec "$bouncer" pg_isready -q -h "$ip" -p 6432'
check "its config and auth file live in /tmp/pgbouncer, the auth file private" \
  '[[ $(docker exec "$bouncer" stat -c %a /tmp/pgbouncer/userlist.txt) == 600 ]] &&
   docker exec "$bouncer" grep -qx "auth_file=/tmp/pgbouncer/userlist.txt" /tmp/pgbouncer/pgbouncer.ini'
check "the sidecar's log does not show the password" '! docker logs "$bouncer" 2>&1 | grep -q "pa\"ss"'
check "without PGBOUNCER_SERVER_HOST the sidecar exits non-zero, naming it" '
  out="$(docker run --rm --read-only --tmpfs /tmp -e PGBOUNCER_AUTH_USER=hub_app -e PGBOUNCER_AUTH_PASSWORD=x \
    -e PGBOUNCER_MAX_USER_CONNECTIONS=40 "$image" pgbouncer-entrypoint 2>&1)" && exit 1
  [[ $out == *PGBOUNCER_SERVER_HOST* ]]'

if [[ $failures -gt 0 ]]; then
  echo "$failures failure(s)"
  exit 1
fi
echo "all passed"
