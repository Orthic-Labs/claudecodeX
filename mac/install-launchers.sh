#!/bin/sh
# Install the two second-instance launchers: claudeX and codex.
#
#   ./mac/install-launchers.sh
#
# Why this deploys a copy instead of pointing at the checkout:
#
# A GUI app launched from Finder or the Dock does NOT inherit your Terminal's
# "Files and Folders" access. If this repository lives on an external volume,
# the launcher exits 126 (cannot execute) with a bare "The command exited with a
# non-zero status" dialog and no window ever appears. Running the same script
# from a terminal works, which makes the failure look impossible to reproduce.
# Copying the launcher and the files it reads onto the internal disk removes the
# whole class of problem.
#
# The copy keeps the repository's own layout, because claudecodex-macos.sh
# resolves config.json and the gateway seed relative to its parent directory.
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEST="$HOME/.local/share/claudecodex"
ICONS="$REPO/assets/icons"
PROFILE="${CLAUDECODEX_PROFILE:-$HOME/ClaudeProfiles/claudecodex-profile}"

[ "$(uname -s)" = "Darwin" ] || { echo "macOS only" >&2; exit 2; }
[ -f "$REPO/config.json" ] || {
  echo "config.json not found. Copy one from examples/ first (see README.md)." >&2
  exit 1
}

mkdir -p "$DEST/mac" "$DEST/configLibrary"
cp "$REPO/mac/claudecodex-macos.sh" "$REPO/mac/codex-second-instance.sh" "$DEST/mac/"
chmod +x "$DEST/mac"/*.sh
cp "$REPO/config.json" "$DEST/config.json"
# Copy the CONTENTS: `cp -R dir dest` nests when dest exists, and the launcher
# then fails on "configLibrary is a directory (not copied)" under `set -e`.
cp "$REPO/configLibrary/"*.json "$DEST/configLibrary/"

install_applet() {
  name="$1"; script="$2"; icon="$3"; env_prefix="$4"; bundle_id="$5"
  app="/Applications/$name.app"
  rm -rf "$app"
  # No `&`: `do shell script` returns immediately and the exec'd app is torn
  # down with the shell, so the window never appears. The wrapper must block.
  # Absolute paths only: single quotes stop $HOME expanding, which silently
  # builds a bogus profile and opens a SUBSCRIPTION window instead.
  osacompile -o "$app" -e \
    "do shell script \"${env_prefix}'$DEST/mac/$script' --foreground > /dev/null 2>&1\"" >/dev/null
  # osacompile leaves CFBundleIdentifier EMPTY. Two applets with no identifier
  # are the same app to LaunchServices, so `open` on the second one silently
  # re-activates the first and the second window never appears. Each launcher
  # needs its own id.
  /usr/libexec/PlistBuddy -c "Set :CFBundleName $name" \
    -c "Add :CFBundleDisplayName string $name" \
    -c "Set :CFBundleIdentifier $bundle_id" \
    "$app/Contents/Info.plist" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $bundle_id" \
    "$app/Contents/Info.plist" >/dev/null 2>&1 || true
  [ -f "$ICONS/$icon.icns" ] && cp "$ICONS/$icon.icns" "$app/Contents/Resources/applet.icns"
  rm -f "$app/Contents/Resources/Assets.car"
  touch "$app"
  echo "installed $app"
}

# NOTE: the bundle cannot be named "codex.app". macOS already claims that
# name (ChatGPT ships Codex (GPU).app and Codex (Alerts).app, and the codex
# CLI is on PATH), and LaunchServices silently refuses to launch it: `open`
# returns success, the applet never runs, and nothing is logged. codexX
# launches normally and matches the claudeX name.
install_applet claudeX claudecodex-macos.sh claudecodex-claude "CLAUDECODEX_PROFILE='$PROFILE' " com.orthiclabs.claudecodex.claude
install_applet codexX codex-second-instance.sh claudecodex-codex "" com.orthiclabs.claudecodex.codex

/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f /Applications/claudeX.app /Applications/codexX.app >/dev/null 2>&1 || true

echo
echo "claudeX  second Claude Desktop, routed to your provider"
echo "codexX   second Codex Desktop, routed to your provider"
echo "Re-run this after changing config.json or either launcher."
