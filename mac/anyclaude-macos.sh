#!/bin/sh
# Second Claude Desktop instance, routed to anyclaude-M3 through the :8801 proxy.
#
# The isolated userData dir is what keeps this off the subscription profile AND suppresses the
# app's relocation to a `Claude-3p` profile (see README.md, trap 2 — if a
# Claude-3p dir ever appears, isolation broke). The binary is launched directly on purpose:
# `open -n` does not reliably pass env vars through to the app.
#
# Seed configLibrary/ from tools/anyclaude-desktop/configLibrary/ BEFORE the first launch and never
# sign in: gateway mode needs no Anthropic login, and an OAuth deep link would land in the default
# profile anyway (trap 4). The Mac build shows no Developer menu, so the file IS the interface.
set -e

PROFILE="${ANYCLAUDE_PROFILE:-$HOME/ClaudeProfiles/anyclaude-profile}"
BIN="/Applications/Claude.app/Contents/MacOS/Claude"
APP="${ANYCLAUDE_APP:-/Applications/anyclaude.app}"

# `--install-app` puts a launcher named "anyclaude" in /Applications so the Applications folder tells
# the two instances apart. It only STARTS the instance: the running window is still Claude Desktop's
# own bundle, so it keeps its Claude icon and auto-updates normally. Built with osacompile because a
# hand-rolled bundle whose executable exits immediately is rejected by LaunchServices (-10669).
if [ "${1:-}" = "--install-app" ]; then
  self=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
  rm -rf "$APP"
  osacompile -o "$APP" -e "do shell script \"'$self' > /dev/null 2>&1 &\"" || {
    echo "osacompile failed (is $(dirname "$APP") writable?)" >&2
    exit 1
  }
  /usr/libexec/PlistBuddy -c 'Set :CFBundleName anyclaude' \
    -c 'Add :CFBundleDisplayName string anyclaude' "$APP/Contents/Info.plist" >/dev/null 2>&1 || true
  # Wear Claude's icon: it launches Claude, so an AppleScript scroll would just be confusing.
  # Assets.car has to go — its AppIcon outranks CFBundleIconFile, which is why copying the .icns
  # alone left the applet icon in place.
  cp /Applications/Claude.app/Contents/Resources/electron.icns "$APP/Contents/Resources/applet.icns"
  rm -f "$APP/Contents/Resources/Assets.car"
  touch "$APP"
  # LaunchServices caches icons per bundle; without this the Finder keeps showing the old one.
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$APP" >/dev/null 2>&1 || true
  echo "installed $APP"
  exit 0
fi

[ -x "$BIN" ] || { echo "Claude Desktop not found at $BIN" >&2; exit 1; }

# Proof of a live router is a POST /v1/messages; GET /v1/models falls through to Anthropic and 401s.
# Two attempts: a cold M3 call, or a proxy launchd just restarted, can miss a single short timeout.
routing=0
for _ in 1 2; do
  if curl -s -m 45 http://127.0.0.1:8801/v1/messages \
      -H "x-api-key: router-dummy" -H "anthropic-version: 2023-06-01" \
      -H "content-type: application/json" \
      -d '{"model":"claude-opus-4-8","max_tokens":16,"messages":[{"role":"user","content":"ping"}]}' \
      | grep -q '"model":"anyclaude'; then
    routing=1
    break
  fi
  sleep 3
done
[ "$routing" = 1 ] || {
  echo "proxy on :8801 is not routing to anyclaude — start com.anyclaude.proxy first" >&2
  exit 1
}

# CLAUDE_USER_DATA_DIR is undocumented, so a Claude Desktop update could drop it. This launcher
# would then silently become a no-op and open an ordinary subscription Claude — harmless, but
# baffling, and it would quietly bill Anthropic. Say so instead. (Mirrors launch-anyclaude.ps1.)
ASAR="/Applications/Claude.app/Contents/Resources/app.asar"
if [ -f "$ASAR" ] && ! grep -qa "CLAUDE_USER_DATA_DIR" "$ASAR"; then
  echo "Claude Desktop no longer supports CLAUDE_USER_DATA_DIR — the anyclaude instance cannot be" >&2
  echo "isolated on this build, so this would just open your subscription Claude. See" >&2
  echo "README.md." >&2
  osascript -e 'display alert "anyclaude Desktop" message "Claude Desktop no longer supports CLAUDE_USER_DATA_DIR. This launcher would open your normal subscription Claude, so it stopped instead." as warning' >/dev/null 2>&1 || true
  exit 1
fi

mkdir -p "$PROFILE"

# Self-heal the gateway config from the repo seed. Without it the instance boots as a plain,
# logged-out Claude and the OAuth deep-link trap makes recovery annoying. An existing config is
# never overwritten, so in-app edits (model labels, extra entries) stick. (Mirrors launch-anyclaude.ps1.)
SEED="$(cd "$(dirname "$0")" && pwd)/configLibrary"
if [ -d "$SEED" ] && [ ! -f "$PROFILE/configLibrary/_meta.json" ]; then
  mkdir -p "$PROFILE/configLibrary"
  cp "$SEED"/* "$PROFILE/configLibrary/"
  echo "[anyclaude] gateway config missing -- restored from repo seed"
fi

# --foreground: become the app (used by the anyclaude.app wrapper — LaunchServices kills a bundle
# whose executable returns immediately). Otherwise background it and hand the shell back.
if [ "${1:-}" = "--foreground" ]; then
  exec env CLAUDE_USER_DATA_DIR="$PROFILE" "$BIN"
fi
CLAUDE_USER_DATA_DIR="$PROFILE" "$BIN" >/dev/null 2>&1 &
echo "anyclaude Claude Desktop starting with profile: $PROFILE"
