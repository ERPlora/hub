#!/usr/bin/env bash
# Tests for download-tool.sh against a fake HTTP server on 127.0.0.1 that answers each request from a
# plan: a passing error of the server (a 5xx, a cut connection, a hung answer) followed by a good
# answer ends in green; an error that never passes ends in red with an ::error:: that names the URL.
#   bash .github/scripts/download-tool.test.sh
# Needs python3 (preinstalled on GitHub's ubuntu runners and on macOS) and curl.
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
root="$(mktemp -d)"
server_pid=""
cleanup() {
  if [ -n "$server_pid" ]; then
    kill "$server_pid" 2> /dev/null || true
  fi
  rm -rf "$root"
}
trap cleanup EXIT

# The file the server hands out and its SHA-256, as test.yml pins actionlint's.
printf 'a pinned tool\n' > "$root/tool"
TOOL_SHA256=f2213272f0fb904d9f87a72441b1413265729d57a354ad8f77bfd77dbf922fcf

# The fake server: one answer per request, from the plan in argv[1], one word per answer, the last
# word repeating: 200 (the tool), 504 or any other status (a short error body), cut (closes the
# connection without answering), hang (answers the tool after 4 s) or wait (a 503 that asks to come
# back in 20 s with Retry-After). Each request is logged to
# argv[3] as "<path> <answer>"; the port it listens on goes to argv[4].
cat > "$root/server.py" <<'PYEOF'
import http.server
import pathlib
import socket
import sys
import time

plan = pathlib.Path(sys.argv[1]).read_text().split()
tool = pathlib.Path(sys.argv[2]).read_bytes()
requests = pathlib.Path(sys.argv[3])
served = 0


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        global served
        answer = plan[min(served, len(plan) - 1)]
        served += 1
        with requests.open("a") as log:
            log.write(f"{self.path} {answer}\n")
        if answer == "cut":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.close_connection = True
            return
        if answer == "hang":
            time.sleep(4)
        status = 200 if answer in ("200", "hang") else 503 if answer == "wait" else int(answer)
        body = tool if status == 200 else b"error\n"
        self.send_response(status)
        if answer == "wait":
            self.send_header("Retry-After", "20")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
pathlib.Path(sys.argv[4]).write_text(str(server.server_address[1]))
server.serve_forever()
PYEOF

# download <plan> [<sha256>] [VAR=value...]: serves <plan> and runs download-tool.sh against it with 3
# attempts, 1 s apart, each cut at 2 s; the VARs override that environment. Sets status (its exit
# code), elapsed (its seconds), url and work: $work/out.log (its output), $work/requests (one line per request the server
# got) and $work/tool.tar.gz (the output it was asked for).
download() {
  local plan="$1" sha256="${2:-$TOOL_SHA256}" port=""
  shift $(($# < 2 ? $# : 2))
  work="$(mktemp -d "$root/case.XXXXXX")"
  printf '%s\n' "$plan" > "$work/plan"
  : > "$work/requests"
  python3 "$root/server.py" "$work/plan" "$root/tool" "$work/requests" "$work/port" 2> "$work/server.log" &
  server_pid=$!
  for _ in $(seq 100); do
    if [ -s "$work/port" ]; then
      port="$(cat "$work/port")"
      break
    fi
    sleep 0.1
  done
  if [ -z "$port" ]; then
    echo "the fake server did not start: $(cat "$work/server.log")" >&2
    exit 1
  fi
  url="http://127.0.0.1:$port/actionlint_1.7.12_linux_amd64.tar.gz"
  status=0
  local started="$SECONDS"
  env ATTEMPTS=3 RETRY_DELAY_SECONDS=1 ATTEMPT_TIMEOUT_SECONDS=2 "$@" \
    bash "$here/download-tool.sh" "$url" "$sha256" "$work/tool.tar.gz" > "$work/out.log" 2>&1 || status=$?
  elapsed=$((SECONDS - started))
  kill "$server_pid" 2> /dev/null || true
  wait "$server_pid" 2> /dev/null || true
  server_pid=""
}

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    sed 's/^/       /' "$work/out.log"
    failures=$((failures + 1))
  fi
}

# requests: how many requests the server got.
requests() { wc -l < "$work/requests" | tr -d ' '; }
# took_under <seconds>: the download ended before <seconds>.
took_under() { [ "$elapsed" -lt "$1" ]; }
# downloaded: green, the output is the pinned tool and no ::error:: was written.
downloaded() {
  [ "$status" -eq 0 ] && cmp -s "$root/tool" "$work/tool.tar.gz" && ! grep -q '::error::' "$work/out.log"
}
# refused <regex>: red, no output (nor a partial one) is left and an ::error:: matches <regex>.
refused() {
  [ "$status" -ne 0 ] && [ -z "$(find "$work" -name 'tool.tar.gz*' -print -quit)" ] &&
    grep -qE "::error::.*$1" "$work/out.log"
}

# --- downloads ----------------------------------------------------------------------------------
download "200"
check "a good answer downloads the tool in one request" 'downloaded && [ "$(requests)" = 1 ]'

download "504 200"
check "a passing 504 of the server is retried and ends in green" 'downloaded && [ "$(requests)" = 2 ]'

download "502 503 200"
check "passing 5xx answers are retried until the last attempt" 'downloaded && [ "$(requests)" = 3 ]'

download "cut 200"
check "a cut connection is retried and ends in green" 'downloaded && [ "$(requests)" = 2 ]'

download "hang 200"
check "a hung answer is cut at the attempt's timeout and retried" 'downloaded && [ "$(requests)" = 2 ]'

# --- errors that do not pass --------------------------------------------------------------------
download "504"
check "a 504 that never passes ends in red with an ::error:: that names the URL" 'refused "$url"'
check "it gave up after the attempts it was given" '[ "$(requests)" = 3 ]'

download "504" "$TOOL_SHA256" ATTEMPTS=1
check "ATTEMPTS=1 tries once" 'refused "$url" && [ "$(requests)" = 1 ]'

download "cut"
check "a connection always cut ends in red" 'refused "$url" && [ "$(requests)" = 3 ]'

# A Retry-After longer than --retry-delay replaces it: without a budget, a 429/503 asking for minutes
# outlasts the job's timeout and the ::error:: is never written.
download "wait"
check "a Retry-After past the retries' budget ends in red at once instead of waiting it out" \
  'refused "$url" && [ "$(requests)" = 1 ] && took_under 5'

download "200" "$(printf '0%.0s' $(seq 64))"
check "a file that is not the pinned one ends in red, naming its URL and SHA-256" \
  'refused "$url.*$TOOL_SHA256" && [ "$(requests)" = 1 ]'

# --- what it is given ---------------------------------------------------------------------------
download "200" "not-a-sha256"
check "a pin that is no SHA-256 is refused before any request" 'refused "SHA-256" && [ "$(requests)" = 0 ]'

for setting in ATTEMPTS=0 ATTEMPTS=x RETRY_DELAY_SECONDS=-1 ATTEMPT_TIMEOUT_SECONDS=0; do
  download "200" "$TOOL_SHA256" "$setting"
  check "$setting is refused before any request" 'refused "${setting%%=*}" && [ "$(requests)" = 0 ]'
done

work="$(mktemp -d "$root/case.XXXXXX")"
status=0
bash "$here/download-tool.sh" "http://127.0.0.1:9/x" "$TOOL_SHA256" > "$work/out.log" 2>&1 || status=$?
check "a missing argument is refused" 'refused "usage"'

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
