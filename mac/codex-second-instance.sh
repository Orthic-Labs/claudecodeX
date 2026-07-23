#!/bin/sh
# Second Codex Desktop instance, routed through the local claudecodeX proxy.
#
# Codex binds ONE model_provider per install and scopes chat history to it, so
# pointing your primary install at a proxy hides your existing chats and loses
# the subscription. CODEX_HOME gives the second instance its own config AND its
# own history, exactly like CLAUDE_USER_DATA_DIR does for Claude Desktop.
#
#   ./mac/codex-second-instance.sh --install    seed the isolated CODEX_HOME
#   ./mac/codex-second-instance.sh              launch the second instance
#   ./mac/codex-second-instance.sh --tui        terminal UI instead of the app
#
# Your primary Codex keeps its ChatGPT subscription, its 200+ chats, and its own
# model picker. Nothing here touches ~/.codex.
set -eu

PROFILE="${CODEX_PROXY_HOME:-$HOME/.codex-proxy}"
APP_BIN="/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"
CORE_BIN="/Applications/ChatGPT.app/Contents/Resources/codex"
PROXY_URL="${CLAUDECODEX_PROXY_URL:-http://127.0.0.1:8801/v1}"
SOURCE_CATALOG="$HOME/.codex/model-catalogs/claudecodex.json"

seed() {
  mkdir -p "$PROFILE"
  if [ -f "$SOURCE_CATALOG" ]; then
    cp "$SOURCE_CATALOG" "$PROFILE/catalog.json"
  fi
  # Never overwrite an existing config: in-app changes must stick.
  if [ ! -f "$PROFILE/config.toml" ]; then
    cat > "$PROFILE/config.toml" <<TOML
# Second Codex instance: every model comes from the local claudecodeX proxy.
# Your primary ~/.codex is untouched and keeps the ChatGPT subscription.
model = "MiniMax-M3"
model_provider = "claudecodex"
model_catalog_json = "$PROFILE/catalog.json"
approval_policy = "never"
sandbox_mode = "workspace-write"

[model_providers.claudecodex]
name = "claudecodeX (local proxy)"
base_url = "$PROXY_URL"
# A placeholder, not a secret: the real provider key lives in the proxy.
# env_key cannot be used here because GUI apps do not read shell profiles.
experimental_bearer_token = "proxy-dummy"
wire_api = "responses"
request_max_retries = 2
stream_max_retries = 2
stream_idle_timeout_ms = 300000
TOML
    echo "seeded $PROFILE/config.toml"
  else
    echo "kept existing $PROFILE/config.toml"
  fi
}

case "${1:-}" in
  --install)
    seed
    CODEX_HOME="$PROFILE" "$CORE_BIN" --strict-config doctor 2>&1 \
      | grep -E 'CODEX_HOME|default model provider|auth ' || true
    exit 0
    ;;
  --tui)
    shift
    seed
    exec env CODEX_HOME="$PROFILE" "$CORE_BIN" "$@"
    ;;
esac

# Codex Desktop enforces a single instance: launching the binary again just
# re-activates the existing window, so there is no second app window to give
# you. Verified on ChatGPT.app (bundle id com.openai.codex). The isolated
# CODEX_HOME still gives a complete second Codex in the terminal.
if pgrep -f "$APP_BIN" >/dev/null 2>&1; then
  echo "Codex Desktop is already running and only permits one instance." >&2
  echo "Your primary window keeps the ChatGPT subscription and its chat history." >&2
  echo "Run the isolated second Codex here instead:" >&2
  echo "  $0 --tui" >&2
  exit 1
fi

[ -x "$APP_BIN" ] || { echo "Codex Desktop not found at $APP_BIN" >&2; exit 1; }
seed

# Proof the proxy is up before opening a window that would only show errors.
if ! curl -fsS --max-time 3 "${PROXY_URL%/v1}/health" >/dev/null 2>&1; then
  echo "claudecodeX proxy is not answering on ${PROXY_URL%/v1}" >&2
  echo "start it, or check: launchctl list | grep claudecodex" >&2
  exit 1
fi

CODEX_HOME="$PROFILE" "$APP_BIN" >/dev/null 2>&1 &
echo "second Codex starting with CODEX_HOME=$PROFILE"
