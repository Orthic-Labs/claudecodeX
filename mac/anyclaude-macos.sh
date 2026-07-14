#!/bin/sh
# Second Claude Desktop instance, routed through the configured anyclaude proxy.
#
# The isolated userData dir is what keeps this off the subscription profile AND suppresses the
# app's relocation to a `Claude-3p` profile (see README.md — if a
# Claude-3p dir ever appears, isolation broke). The binary is launched directly on purpose:
# `open -n` does not reliably pass env vars through to the app.
#
# Seed configLibrary/ from the repo BEFORE the first launch and never
# sign in: gateway mode needs no Anthropic login, and an OAuth deep link would land in the default
# profile anyway. Some Mac builds show no Developer menu, so the file is the interface.
set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROFILE="${ANYCLAUDE_PROFILE:-$HOME/ClaudeProfiles/anyclaude-profile}"
CONFIG="$PROFILE/claude-config"
COWORK_FILES="$PROFILE/cowork-user-files"
DESKTOP_CONFIG="$PROFILE/claude_desktop_config.json"
BIN="/Applications/Claude.app/Contents/MacOS/Claude"
APP="${ANYCLAUDE_APP:-/Applications/anyclaude.app}"
PYTHON="${ANYCLAUDE_PYTHON:-$(command -v python3 || true)}"

# `--install-app` puts a launcher named "anyclaude" in /Applications so the Applications folder tells
# the two instances apart. It only STARTS the instance: the running window is still Claude Desktop's
# own bundle, so it keeps its Claude icon and auto-updates normally. Built with osacompile because a
# hand-rolled bundle whose executable exits immediately is rejected by LaunchServices (-10669).
if [ "${1:-}" = "--install-app" ]; then
  self=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
  [ -x "$PYTHON" ] || { echo "python3 not found on PATH" >&2; exit 1; }
  rm -rf "$APP"
  osacompile -o "$APP" \
    -e "do shell script \"ANYCLAUDE_PYTHON='$PYTHON' '$self' --foreground > /dev/null 2>&1 &\"" || {
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
[ -x "$PYTHON" ] || { echo "python3 not found on PATH" >&2; exit 1; }
[ -f "$ROOT/config.json" ] || {
  echo "config.json not found. Copy one from examples/ first (see README.md)." >&2
  exit 1
}
PORT=$("$PYTHON" - "$ROOT/config.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(int(json.load(handle).get("port", 8801)))
PY
)

# This local health check verifies the configured proxy without spending a provider inference call.
routing=0
for _ in 1 2; do
  if curl -fsS -o /dev/null -m 5 "http://127.0.0.1:$PORT/health"; then
    routing=1
    break
  fi
  sleep 3
done
[ "$routing" = 1 ] || {
  echo "proxy on :$PORT is not routing — start 'python3 proxy.py' from the repo first" >&2
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

mkdir -p "$PROFILE" "$CONFIG" "$COWORK_FILES"

# The isolated CLAUDE_CONFIG_DIR is meant to separate auth and Desktop state, but it also hides the
# skills and subagents already installed in ~/.claude: they simply do not exist in this profile, so
# Claude Code inside the anyclaude window silently has none of them. Link them back rather than copy,
# so the originals stay the single source of truth and edits land in both instances.
#
# settings.json is deliberately NOT linked. It commonly pins an Anthropic-only model name, which the
# gateway provider does not serve. Set ANYCLAUDE_SHARE_CLAUDE_CODE=0 for a fully sealed profile.
if [ "${ANYCLAUDE_SHARE_CLAUDE_CODE:-1}" = 1 ]; then
  for share in skills agents; do
    src="$HOME/.claude/$share"
    dst="$CONFIG/$share"
    if [ -d "$src" ]; then
      # Re-point a stale or broken link, but never clobber a real directory the user put here.
      [ -L "$dst" ] && rm -f "$dst"
      [ -e "$dst" ] || ln -s "$src" "$dst"
    fi
  done
fi

# Claude Code state must not fall back to ~/.claude: that path may be a symlink into a selected
# workspace and makes Desktop reject the folder as protected. Cowork also defaults to ~/Claude,
# which collides with ~/claude on a case-insensitive Mac. Keep both inside this isolated profile.
"$PYTHON" - "$DESKTOP_CONFIG" "$COWORK_FILES" <<'PY'
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

config, cowork_files = map(Path, sys.argv[1:])
data = json.loads(config.read_text()) if config.exists() else {}
if not isinstance(data, dict):
    raise SystemExit(f"Expected a JSON object in {config}")
current = data.get("coworkUserFilesPath")
default = Path.home() / "Claude"
is_default = current is None or (
    str(Path(current).expanduser().resolve(strict=False)).casefold()
    == str(default.resolve(strict=False)).casefold()
)
if is_default:
    mode = stat.S_IMODE(config.stat().st_mode) if config.exists() else 0o600
    data["coworkUserFilesPath"] = str(cowork_files)
    with tempfile.NamedTemporaryFile(
        "w", dir=config.parent, prefix=f".{config.name}.", delete=False
    ) as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        os.chmod(temporary, mode)
        os.replace(temporary, config)
    finally:
        temporary.unlink(missing_ok=True)
PY

# Self-heal the gateway config from the repo seed. Without it the instance boots as a plain,
# logged-out Claude and the OAuth deep-link trap makes recovery annoying. An existing config is
# never overwritten, so in-app edits (model labels, extra entries) stick. (Mirrors launch-anyclaude.ps1.)
SEED="$ROOT/configLibrary"
if [ -d "$SEED" ] && [ ! -f "$PROFILE/configLibrary/_meta.json" ]; then
  mkdir -p "$PROFILE/configLibrary"
  cp "$SEED"/* "$PROFILE/configLibrary/"
  echo "[anyclaude] gateway config missing -- restored from repo seed"
fi

# --foreground: become the app (used by the anyclaude.app wrapper — LaunchServices kills a bundle
# whose executable returns immediately). Otherwise background it and hand the shell back.
if [ "${1:-}" = "--foreground" ]; then
  exec env CLAUDE_USER_DATA_DIR="$PROFILE" CLAUDE_CONFIG_DIR="$CONFIG" "$BIN"
fi
CLAUDE_USER_DATA_DIR="$PROFILE" CLAUDE_CONFIG_DIR="$CONFIG" "$BIN" >/dev/null 2>&1 &
echo "anyclaude Claude Desktop starting with profile: $PROFILE"
