#!/usr/bin/env bash
# Tests for clone-repo.sh against a repository served over file:// (GITHUB_SERVER_URL), through a fake
# git in the PATH that answers each call that would reach GitHub (the clone and the sparse checkout)
# from a plan and logs what it was given; on "ok" it hands the call to the real git.
#   bash .github/scripts/clone-repo.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# Neither the machine's nor the user's git config (hooks, headers) reaches the clones.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
REAL_GIT="$(command -v git)"
export REAL_GIT
TOKEN="ghs_job-token-of-the-test"
SERVER="file://$root/server"

# The repository on the fake server: two commits, so a clone at depth 1 is shallow, and two folders, so
# a sparse clone shows which ones it checked out.
git init --quiet -b main "$root/source"
mkdir -p "$root/source/public/declaracion" "$root/source/other"
echo v1 > "$root/source/public/declaracion/v1"
git -C "$root/source" add . && git -C "$root/source" -c user.name=t -c user.email=t@t commit --quiet -m one
echo other > "$root/source/other/file"
git -C "$root/source" add . && git -C "$root/source" -c user.name=t -c user.email=t@t commit --quiet -m two
git clone --quiet --bare "$root/source" "$root/server/ERPlora/saas.git"
git -C "$root/server/ERPlora/saas.git" config uploadpack.allowFilter true

# The fake git: for clone and sparse-checkout, one answer per call from $PLAN (one word per call, the last
# repeating): ok (the real git), fail (GitHub's 403, after leaving a partial clone) or hang. Each of those
# calls is logged to $CALLS as "<command> existed=<yes|no> header=<the extraheader git sees> args=<argv>".
mkdir -p "$root/bin"
cat > "$root/bin/git" <<'SHEOF'
#!/usr/bin/env bash
set -euo pipefail
args=("$@") dir=""
while [ "${args[0]:-}" = -C ]; do dir="${args[1]}" args=("${args[@]:2}"); done
command="${args[0]:-}"
case "$command" in clone) target="${args[${#args[@]}-1]}" ;; sparse-checkout) target="$dir" ;; *) exec "$REAL_GIT" "$@" ;; esac
plan=($(cat "$PLAN"))
served="$(wc -l < "$CALLS" | tr -d ' ')"
answer="${plan[$((served < ${#plan[@]} ? served : ${#plan[@]} - 1))]}"
header="$("$REAL_GIT" config --get "http.$GITHUB_SERVER_URL/.extraheader" || true)"
echo "$command existed=$([ -e "$target" ] && echo yes || echo no) header=$header args=$*" >> "$CALLS"
case "$answer" in
  fail) if [ "$command" = clone ]; then mkdir -p "$target/.git"; fi
    echo "fatal: unable to access '$GITHUB_SERVER_URL': The requested URL returned error: 403" >&2
    exit 128 ;;
  hang) exec sleep 10 ;;
esac
exec "$REAL_GIT" "$@"
SHEOF
chmod +x "$root/bin/git"

# clone <plan> [<path>...]: runs clone-repo.sh ERPlora/saas into $work/saas with 3 attempts, no wait between
# them, each cut at 3 s; $settings (VAR=value words) overrides that environment. Sets status (its exit code),
# elapsed (its seconds) and work: $work/out.log (its output) and $work/calls (the fake git's log).
settings=""
clone() {
  local plan="$1"
  shift
  work="$(mktemp -d "$root/case.XXXXXX")"
  printf '%s\n' "$plan" > "$work/plan"
  : > "$work/calls"
  status=0
  local started="$SECONDS"
  # shellcheck disable=SC2086
  env PATH="$root/bin:$PATH" PLAN="$work/plan" CALLS="$work/calls" GITHUB_SERVER_URL="$SERVER" GH_TOKEN="$TOKEN" \
    ATTEMPTS=3 RETRY_DELAY_SECONDS=0 ATTEMPT_TIMEOUT_SECONDS=3 $settings \
    bash "$here/clone-repo.sh" ERPlora/saas "$work/saas" "$@" > "$work/out.log" 2>&1 || status=$?
  elapsed=$((SECONDS - started))
  settings=""
}

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    sed 's/^/       /' "$work/out.log" "$work/calls"
    failures=$((failures + 1))
  fi
}

# calls <command>: how many times the fake git was asked for <command>.
calls() { grep -c "^$1 " "$work/calls" || true; }
took_under() { [ "$elapsed" -lt "$1" ]; }
took_at_least() { [ "$elapsed" -ge "$1" ]; }
cloned() { [ "$status" -eq 0 ] && [ "$(git -C "$work/saas" rev-parse --is-shallow-repository)" = true ]; }
# not_downloaded <path>: the clone does not hold the file at <path> (rev-list prints it as missing, without fetching it).
not_downloaded() {
  git -C "$work/saas" rev-list --objects --missing=print HEAD | grep -qx "?$(git -C "$root/source" rev-parse "HEAD:$1")"
}
refused() { [ "$status" -ne 0 ] && [ ! -e "$work/saas" ] && grep -qE "::error::.*$1" "$work/out.log"; }
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
# every_call_has_the_token: each logged call carried "Authorization: Basic <base64 of x-access-token:<token>>".
every_call_has_the_token() {
  local line name scheme credentials
  [ -s "$work/calls" ] && while read -r line; do
    line="${line#* header=}"
    read -r name scheme credentials <<< "${line%% args=*}"
    [ "$(lower "$name $scheme")" = "authorization: basic" ] || return 1
    [ "$(printf '%s' "$credentials" | base64 -d)" = "x-access-token:$TOKEN" ] || return 1
  done < "$work/calls"
}

# --- clones -------------------------------------------------------------------------------------
clone "ok"
check "a clone without paths brings the whole tree, at depth 1" \
  'cloned && [ -f "$work/saas/public/declaracion/v1" ] && [ -f "$work/saas/other/file" ]'

clone "ok" public/declaracion
check "a clone with paths checks out and downloads only those, at depth 1" \
  'cloned && [ -f "$work/saas/public/declaracion/v1" ] && [ ! -e "$work/saas/other" ] && not_downloaded other/file'
check "the clone and the sparse checkout (which fetches the paths' files) both reach GitHub as the job's token" \
  '[ "$(calls clone)" = 1 ] && [ "$(calls sparse-checkout)" = 1 ] && every_call_has_the_token'
check "the token is in neither git's arguments nor the clone's config" \
  '! grep -qF "$TOKEN" "$work/calls" && ! grep -rqiE "extraheader|basic" "$work/saas/.git/config"'

# --- GitHub failing -----------------------------------------------------------------------------
clone "fail ok" public/declaracion
check "a clone GitHub refuses (403) is retried and ends in green" 'cloned && [ "$(calls clone)" = 2 ]'
check "the partial clone of a failed attempt is gone before the next" \
  '[ "$(grep "^clone " "$work/calls" | sed -n 2p | grep -c "existed=no")" = 1 ]'

clone "ok fail ok" public/declaracion
check "a failed sparse checkout is retried from a new clone" \
  'cloned && [ "$(calls clone)" = 2 ] && [ "$(calls sparse-checkout)" = 2 ] && [ -f "$work/saas/public/declaracion/v1" ]'

clone "hang ok"
check "a hung attempt is cut at the attempt's timeout and retried" 'cloned && [ "$(calls clone)" = 2 ] && took_under 8'

clone "fail"
check "a clone that never passes ends in red with an ::error:: that names the repository, and no folder" \
  'refused "ERPlora/saas" && [ "$(calls clone)" = 3 ]'

settings="ATTEMPTS="
clone "fail"
check "by default it tries 5 times" 'refused "ERPlora/saas" && [ "$(calls clone)" = 5 ]'

settings="RETRY_DELAY_SECONDS=2"
clone "fail ok"
check "it waits RETRY_DELAY_SECONDS before trying again" 'cloned && took_at_least 2'

# --- what it is given ---------------------------------------------------------------------------
settings="GH_TOKEN="
clone "ok"
check "without GH_TOKEN it refuses, before any call to GitHub" 'refused "GH_TOKEN" && [ "$(calls clone)" = 0 ]'

for setting in ATTEMPTS=0 ATTEMPTS=x RETRY_DELAY_SECONDS=-1 ATTEMPT_TIMEOUT_SECONDS=0; do
  settings="$setting"
  clone "ok"
  check "$setting is refused before any call to GitHub" 'refused "${setting%%=*}" && [ "$(calls clone)" = 0 ]'
done

work="$(mktemp -d "$root/case.XXXXXX")"
: > "$work/calls"
status=0
GH_TOKEN="$TOKEN" bash "$here/clone-repo.sh" ERPlora/saas > "$work/out.log" 2>&1 || status=$?
check "a missing argument is refused" '[ "$status" -ne 0 ] && grep -q "::error::usage" "$work/out.log"'

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
