#!/bin/sh
# Second Codex Desktop instance, routed through the local claudecodeX proxy.
#
# Codex Desktop looks single-instance, but it is Chromium based (see
# "Codex Framework.framework", whose version is a Chromium version, and its
# Codex (GPU).app helper). The single-instance lock lives in the Chromium
# userData directory, NOT in the app bundle, exactly like Claude Desktop. Give
# the second instance its own --user-data-dir and both windows run at once. No
# copy of the 1.4 GB bundle is needed, so the second instance keeps the real
# code signature and follows normal app updates.
#
# Two separate isolations are in play:
#   --user-data-dir  Chromium profile. This is what permits a second window.
#   CODEX_HOME       Codex config, auth, and chat history. This is what points
#                    the instance at the proxy and keeps your 200+ subscription
#                    chats out of it.
#
#   ./mac/codex-second-instance.sh --install-app   add a Codex Proxy launcher
#   ./mac/codex-second-instance.sh                 launch the second instance
#   ./mac/codex-second-instance.sh --tui           terminal UI instead
set -eu

PROFILE="${CODEX_PROXY_HOME:-$HOME/.codex-proxy}"
USER_DATA="$PROFILE/chrome"
APP="/Applications/ChatGPT.app"
APP_BIN="$APP/Contents/MacOS/ChatGPT"
CORE_BIN="$APP/Contents/Resources/codex"
LAUNCHER="${CODEX_PROXY_APP:-/Applications/Codex Proxy.app}"
PROXY_URL="${CLAUDECODEX_PROXY_URL:-http://127.0.0.1:8801/v1}"
SOURCE_CATALOG="$HOME/.codex/model-catalogs/claudecodex.json"

seed() {
  mkdir -p "$PROFILE" "$USER_DATA"
  [ -f "$SOURCE_CATALOG" ] && cp "$SOURCE_CATALOG" "$PROFILE/catalog.json"
  # Never overwrite an existing config: in-app changes must stick.
  [ -f "$PROFILE/config.toml" ] && return 0
  cat > "$PROFILE/config.toml" <<TOML
# Second Codex instance: every model comes from the local claudecodeX proxy.
# Your primary ~/.codex is untouched and keeps the ChatGPT subscription.
model = "MiniMax-M3"
model_provider = "claudecodex"
model_catalog_json = "$PROFILE/catalog.json"

[model_providers.claudecodex]
name = "claudecodeX (local proxy)"
base_url = "$PROXY_URL"
# A placeholder, not a secret: the real provider key lives in the proxy.
# env_key cannot be used because GUI apps do not read shell profiles.
experimental_bearer_token = "proxy-dummy"
wire_api = "responses"
request_max_retries = 2
stream_max_retries = 2
stream_idle_timeout_ms = 300000
TOML
  echo "seeded $PROFILE/config.toml"
}

case "${1:-}" in
  --install-app)
    self=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
    seed
    rm -rf "$LAUNCHER"
    # osacompile, for the same reason as the Claude launcher: LaunchServices
    # rejects a hand-rolled bundle whose executable exits immediately.
    osacompile -o "$LAUNCHER" -e "do shell script \"'$self' > /dev/null 2>&1 &\""
    /usr/libexec/PlistBuddy -c 'Set :CFBundleName Codex Proxy' \
      -c 'Add :CFBundleDisplayName string Codex Proxy' \
      "$LAUNCHER/Contents/Info.plist" >/dev/null 2>&1 || true
    cp "$APP/Contents/Resources/app.icns" "$LAUNCHER/Contents/Resources/applet.icns" 2>/dev/null || true
    rm -f "$LAUNCHER/Contents/Resources/Assets.car"
    touch "$LAUNCHER"
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
      -f "$LAUNCHER" >/dev/null 2>&1 || true
    echo "installed $LAUNCHER"
    exit 0
    ;;
  --tui)
    shift
    seed
    exec env CODEX_HOME="$PROFILE" "$CORE_BIN" "$@"
    ;;
esac

[ -x "$APP_BIN" ] || { echo "Codex Desktop not found at $APP_BIN" >&2; exit 1; }
seed

# Proof the proxy is up before opening a window that could only show errors.
if ! curl -fsS --max-time 3 "${PROXY_URL%/v1}/health" >/dev/null 2>&1; then
  echo "claudecodeX proxy is not answering on ${PROXY_URL%/v1}" >&2
  echo "check: launchctl list | grep claudecodex" >&2
  exit 1
fi

CODEX_HOME="$PROFILE" "$APP_BIN" --user-data-dir="$USER_DATA" >/dev/null 2>&1 &
echo "second Codex starting (CODEX_HOME=$PROFILE)"
