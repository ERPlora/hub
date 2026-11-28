#!/usr/bin/env bash
# Installs the packages the CI needs, from GitHub's cache when it holds them:
#   bash .github/scripts/apt-install.sh <archives> <package>...
# <archives> is the folder of their .deb files; test.yml keeps WeasyPrint's in GitHub's cache (actions/cache),
# one entry per runner image.
# 1. From the cache: apt installs from the .deb files in <archives> without downloading anything nor
#    refreshing its lists, so Ubuntu's mirror is not needed (hub#1222: a DNS outage of the mirror kept
#    every run red for hours). Only this repository's runs write the cache, as with setup-uv's.
# 2. Without them (a new runner image, an evicted cache) or when they do not install: the .deb files of
#    the cache are dropped, since apt only checks the size of the ones it finds and would hand a broken
#    one to dpkg again; apt refreshes its lists and downloads into <archives>, ATTEMPTS attempts in all,
#    RETRY_DELAY_SECONDS apart, and the folder is left readable for the cache to save (it is only
#    saved under a new key). apt itself already tries the mirror list of the runner (Azure's mirror,
#    archive.ubuntu.com, security.ubuntu.com); with the mirror out of reach each attempt takes about
#    5 minutes (3 for the lists, 1 to 2 for the download), so the defaults give up after about 15
#    minutes, inside the python job's 30, with an ::error:: that names the packages.
#    Before the lists are refreshed, the runner's sources of packages.microsoft.com are dropped: the Hub
#    installs nothing from them, and when they answer 403 apt-get update fails whatever the others answer.
#
# Env: optional ATTEMPTS (3), RETRY_DELAY_SECONDS (30), APT_SOURCES_DIR (/etc/apt/sources.list.d).
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

if [ "$#" -lt 2 ]; then
  fail "usage: apt-install.sh <archives> <package>..."
fi
archives="$1"
shift

attempts="${ATTEMPTS:-3}" delay="${RETRY_DELAY_SECONDS:-30}" sources="${APT_SOURCES_DIR:-/etc/apt/sources.list.d}"
if ! [[ "$attempts" =~ ^[1-9][0-9]*$ ]]; then
  fail "ATTEMPTS must be a whole number of 1 or more, not '$attempts'"
fi
if ! [[ "$delay" =~ ^[0-9]+$ ]]; then
  fail "RETRY_DELAY_SECONDS must be a whole number of 0 or more, not '$delay'"
fi

# apt downloads into <archives>/partial and locks <archives>/lock, both as root.
mkdir -p "$archives/partial"
apt_install() {
  sudo apt-get install -y --no-install-recommends -o Dir::Cache::Archives="$archives" "$@"
}

if apt_install --no-download "$@"; then
  echo "installed $* from GitHub's cache"
  exit 0
fi
echo "$archives has no .deb of $* that installs on this runner image: downloading them from apt's sources"
sudo find "$archives" -maxdepth 1 -name '*.deb' -delete
for source in "$sources"/*; do
  if [ -f "$source" ] && grep -qF packages.microsoft.com "$source"; then
    sudo rm -f "$source"
    echo "dropped $source: nothing is installed from packages.microsoft.com"
  fi
done

attempt=1
until sudo apt-get update && apt_install "$@"; do
  if [ "$attempt" -ge "$attempts" ]; then
    fail "could not install $* from apt's sources (apt's error above): it gave up after $attempts attempt(s), ${delay} s apart; if a mirror is down, re-run the job once it answers"
  fi
  attempt=$((attempt + 1))
  echo "apt's sources failed; attempt $attempt of $attempts in ${delay} s"
  sleep "$delay"
done

# partial/ and lock stay root's and unreadable: without them, and handed to the job's user, the folder
# is what actions/cache saves at the end of the job.
sudo rm -rf "$archives/partial" "$archives/lock"
sudo chown -R "$(id -un)" "$archives"
echo "installed $* from apt's sources; their .deb files stay in $archives for GitHub's cache"
