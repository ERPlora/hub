#!/usr/bin/env bash
# Tests for apt-install.sh against a fake apt-get, sudo and sleep on the PATH: the packages come from
# GitHub's cache (the archives folder) without touching Ubuntu's mirror; without them, a passing
# failure of the mirror is retried, a failure that never passes ends in red with an ::error:: that
# names the packages, the runner's Microsoft sources are dropped before apt refreshes its lists, and
# the archives are left readable for the cache to save.
#   bash .github/scripts/apt-install.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# The fake commands log each call to $FAKE_CALLS, one line per call.
#   sudo <cmd...>: logs "sudo <cmd...>" and runs it as the caller, with FAKE_ROOT=1.
#   sleep <n>: logs "sleep <n>" and returns at once.
#   apt-get without sudo (no FAKE_ROOT): fails like apt run by the job's user, on dpkg's lock (exit 100).
#   apt-get update: logs it and, like apt with an unreachable mirror, only warns (exit 0); with a source
#   of packages.microsoft.com left in $APT_SOURCES_DIR it fails as apt does on that source's 403 (exit 100).
#   apt-get install [--no-download] -o Dir::Cache::Archives=<dir> ... <packages>: like apt, a .deb
#   already in <dir> is handed to dpkg without downloading it again (apt only checks its size), and dpkg
#   fails on a broken one; with --no-download and no .deb it fails at once; otherwise it takes the next
#   word of the plan in $FAKE_PLAN (the last one repeats): ok downloads the .deb into <dir> (leaving
#   apt's partial/ and lock behind, as apt does) and installs, fail is the mirror's DNS error (exit 100).
mkdir -p "$root/bin"
cat > "$root/bin/sudo" <<'EOF'
#!/usr/bin/env bash
echo "sudo $*" >> "$FAKE_CALLS"
FAKE_ROOT=1 exec "$@"
EOF
cat > "$root/bin/sleep" <<'EOF'
#!/usr/bin/env bash
echo "sleep $*" >> "$FAKE_CALLS"
EOF
cat > "$root/bin/apt-get" <<'EOF'
#!/usr/bin/env bash
echo "apt-get $*" >> "$FAKE_CALLS"
if [ "${FAKE_ROOT:-}" != 1 ]; then
  echo "E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)"
  exit 100
fi
archives="" no_download=0 command=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) archives="${2#Dir::Cache::Archives=}"; shift 2 ;;
    --no-download) no_download=1; shift ;;
    -*) shift ;;
    *) [ -z "$command" ] && command="$1"; shift ;;
  esac
done
deb="$archives/libfake_1.0_amd64.deb"
if [ "$command" = update ]; then
  if grep -qsF packages.microsoft.com "$APT_SOURCES_DIR"/*; then
    echo "E: Failed to fetch https://packages.microsoft.com/ubuntu/24.04/prod/dists/noble/InRelease  403  Forbidden"
    echo "E: The repository 'https://packages.microsoft.com/ubuntu/24.04/prod noble InRelease' is no longer signed."
    exit 100
  fi
  echo "W: Failed to fetch mirror+file:/etc/apt/apt-mirrors.txt/dists/noble/InRelease  Temporary failure resolving 'azure.archive.ubuntu.com'"
  exit 0
fi
if [ -f "$deb" ]; then
  if [ "$(cat "$deb")" = "a package" ]; then
    echo "installed from $archives"
    exit 0
  fi
  echo "E: Sub-process /usr/bin/dpkg returned an error code (1)"
  exit 100
fi
if [ "$no_download" = 1 ]; then
  echo "E: Unable to fetch some archives, maybe run apt-get update or try with --fix-missing?"
  exit 100
fi
read -r -a plan < "$FAKE_PLAN"
# This call is already logged: the plan's word for it is the one of its rank among the mirror's installs.
network="$(grep '^apt-get install' "$FAKE_CALLS" | grep -vc -- '--no-download' | tr -d ' ')"
index=$((network - 1))
[ "$index" -ge "${#plan[@]}" ] && index=$((${#plan[@]} - 1))
if [ "${plan[$index]}" = ok ]; then
  mkdir -p "$archives/partial"
  : > "$archives/lock"
  echo "a package" > "$deb"
  echo "downloaded and installed"
  exit 0
fi
echo "E: Failed to fetch http://azure.archive.ubuntu.com/ubuntu/pool/main/f/fake/libfake_1.0_amd64.deb  Temporary failure resolving 'azure.archive.ubuntu.com'"
exit 100
EOF
chmod +x "$root/bin/sudo" "$root/bin/sleep" "$root/bin/apt-get"

# install <plan> [cached|broken|microsoft] [VAR=value...]: runs apt-install.sh for libfake and libother
# with the fake commands, ATTEMPTS=3 and RETRY_DELAY_SECONDS=7 unless a VAR overrides them, and apt's
# sources in $work/sources (Ubuntu's and PGDG's); "cached" puts the .deb in the archives folder first,
# as a cache hit does, "broken" a .deb dpkg refuses, and "microsoft" adds the Microsoft sources of
# GitHub's runners, in both formats apt reads. Sets status (its exit code) and work: $work/out.log (its
# output), $work/calls (the fake commands' calls), $work/archives and $work/sources.
install() {
  local plan="$1"
  shift
  work="$(mktemp -d "$root/case.XXXXXX")"
  printf '%s\n' "$plan" > "$work/plan"
  : > "$work/calls"
  mkdir -p "$work/sources"
  printf 'Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\nSuites: noble\nComponents: main\n' \
    > "$work/sources/ubuntu.sources"
  echo "deb [signed-by=/usr/share/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main" \
    > "$work/sources/pgdg.list"
  if [ "${1:-}" = microsoft ]; then
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/24.04/prod noble main" \
      > "$work/sources/microsoft-prod.list"
    printf 'Types: deb\nURIs: https://packages.microsoft.com/repos/edge\nSuites: stable\nComponents: main\n' \
      > "$work/sources/microsoft-edge.sources"
    shift
  fi
  if [ "${1:-}" = cached ] || [ "${1:-}" = broken ]; then
    mkdir -p "$work/archives"
    if [ "$1" = cached ]; then
      echo "a package" > "$work/archives/libfake_1.0_amd64.deb"
    else
      echo "a broken package" > "$work/archives/libfake_1.0_amd64.deb"
    fi
    shift
  fi
  status=0
  env PATH="$root/bin:$PATH" FAKE_PLAN="$work/plan" FAKE_CALLS="$work/calls" APT_SOURCES_DIR="$work/sources" \
    ATTEMPTS=3 RETRY_DELAY_SECONDS=7 "$@" \
    bash "$here/apt-install.sh" "$work/archives" libfake libother > "$work/out.log" 2>&1 || status=$?
}

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    sed 's/^/       /' "$work/out.log"
    sed 's/^/       call: /' "$work/calls"
    failures=$((failures + 1))
  fi
}

# calls <regex>: how many calls of the fake commands match <regex>.
calls() { grep -cE "$1" "$work/calls" | tr -d ' '; }
# from_mirror: how many installs went to Ubuntu's mirror (without --no-download).
from_mirror() { grep '^apt-get install' "$work/calls" | grep -vc -- '--no-download' | tr -d ' '; }
# installed: green and no ::error:: was written.
installed() { [ "$status" -eq 0 ] && ! grep -q '::error::' "$work/out.log"; }
# left_for_the_cache: the .deb is in the archives folder, without apt's partial/ and lock (which
# root keeps unreadable, so the cache could not save the folder, and so only root removes them), and
# the folder was handed back to the job's user.
left_for_the_cache() {
  [ -f "$work/archives/libfake_1.0_amd64.deb" ] && [ ! -e "$work/archives/partial" ] &&
    [ ! -e "$work/archives/lock" ] && [ "$(calls "^sudo rm -rf $work/archives/partial $work/archives/lock\$")" = 1 ] &&
    [ "$(calls "^sudo chown -R [^ ]+ $work/archives\$")" = 1 ]
}
# refused <regex>: red and an ::error:: matches <regex>.
refused() { [ "$status" -ne 0 ] && grep -qE "::error::.*$1" "$work/out.log"; }

# --- from GitHub's cache --------------------------------------------------------------------------
install "fail" cached
check "with the .deb in the cache it installs without Ubuntu's mirror" \
  'installed && [ "$(from_mirror)" = 0 ] && [ "$(calls "^apt-get update")" = 0 ] && [ "$(calls "^sleep")" = 0 ]'
check "the install from the cache never downloads and reads the cache's archives" \
  '[ "$(grep "^apt-get install " "$work/calls" | grep -- " --no-download " | grep -- " -o Dir::Cache::Archives=$work/archives " |
     grep -c " libfake libother$")" = 1 ]'

# --- from Ubuntu's mirror -------------------------------------------------------------------------
install "ok"
check "without the cache it refreshes the lists and downloads once" \
  'installed && [ "$(calls "^apt-get update")" = 1 ] && [ "$(from_mirror)" = 1 ] && [ "$(calls "^sleep")" = 0 ]'
check "it installs the packages it is given, without the recommended ones, into the cache's archives" \
  '[ "$(calls "^apt-get install -y --no-install-recommends -o Dir::Cache::Archives=$work/archives libfake libother$")" = 1 ]'
check "it leaves the .deb readable in the archives for the cache to save" 'left_for_the_cache'

install "fail ok"
check "a passing failure of the mirror is retried and ends in green" \
  'installed && [ "$(from_mirror)" = 2 ] && left_for_the_cache'
check "each retry waits RETRY_DELAY_SECONDS and refreshes the lists again" \
  '[ "$(calls "^sleep 7$")" = 1 ] && [ "$(calls "^apt-get update")" = 2 ]'

install "fail fail ok"
check "passing failures are retried until the last attempt" 'installed && [ "$(from_mirror)" = 3 ]'

# apt only checks the size of a .deb already in its archives: one dpkg refuses (or one of another
# version than the image's lists) would be handed to dpkg again on every attempt.
install "ok" broken
check "a .deb of the cache that does not install is downloaded again from the mirror" \
  'installed && [ "$(from_mirror)" = 1 ] && [ "$(cat "$work/archives/libfake_1.0_amd64.deb")" = "a package" ]'

# --- the runner's sources the Hub does not use -----------------------------------------------------
# GitHub's runners come with Microsoft's package source, which the Hub does not use: at times it answers
# 403 and apt-get update fails on it (exit 100) whatever the other sources answer, every attempt alike.
install "ok" microsoft
check "without the cache it drops the runner's Microsoft sources before apt refreshes its lists, and installs" \
  'installed && [ "$(calls "^apt-get update")" = 1 ] && [ "$(from_mirror)" = 1 ] &&
     [ ! -e "$work/sources/microsoft-prod.list" ] && [ ! -e "$work/sources/microsoft-edge.sources" ]'
check "they are root's, so it drops them with sudo" \
  '[ "$(calls "^sudo rm -f $work/sources/microsoft-prod.list$")" = 1 ] &&
     [ "$(calls "^sudo rm -f $work/sources/microsoft-edge.sources$")" = 1 ]'
check "it keeps the sources the Hub installs from" '[ -f "$work/sources/ubuntu.sources" ] && [ -f "$work/sources/pgdg.list" ]'

# --- failures that do not pass --------------------------------------------------------------------
install "fail"
check "a mirror that never answers ends in red with an ::error:: that names the packages" 'refused "libfake libother"'
check "it gave up after the attempts it was given, waiting between them" \
  '[ "$(from_mirror)" = 3 ] && [ "$(calls "^sleep 7$")" = 2 ]'

install "fail" ATTEMPTS=1
check "ATTEMPTS=1 tries the mirror once" 'refused "libfake" && [ "$(from_mirror)" = 1 ] && [ "$(calls "^sleep")" = 0 ]'

install "fail" ATTEMPTS= RETRY_DELAY_SECONDS=
check "by default it tries the mirror 3 times, 30 s apart" \
  'refused "libfake" && [ "$(from_mirror)" = 3 ] && [ "$(calls "^sleep 30$")" = 2 ]'

# --- what it is given -----------------------------------------------------------------------------
for setting in ATTEMPTS=0 ATTEMPTS=x RETRY_DELAY_SECONDS=-1 RETRY_DELAY_SECONDS=x; do
  install "ok" "$setting"
  check "$setting is refused before apt runs" 'refused "${setting%%=*}" && [ "$(calls "^apt-get")" = 0 ]'
done

work="$(mktemp -d "$root/case.XXXXXX")"
: > "$work/calls"
status=0
env PATH="$root/bin:$PATH" FAKE_CALLS="$work/calls" bash "$here/apt-install.sh" "$work/archives" > "$work/out.log" 2>&1 ||
  status=$?
check "no package to install is refused" 'refused "usage" && [ "$(calls "^apt-get")" = 0 ]'

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
