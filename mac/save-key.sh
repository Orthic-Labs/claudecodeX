#!/bin/sh
# Save a provider key into the macOS login Keychain, and optionally expose it as
# an environment variable.
#
#   ./mac/save-key.sh CLAUDECODEX_MINIMAX_API_KEY
#   ./mac/save-key.sh CLAUDECODEX_MINIMAX_API_KEY MINIMAX_API_KEY
#
# The first argument is the Keychain SERVICE name. Put the same string in your
# config.json as the provider's "keychain" field.
#
# The optional second argument is an environment variable name. It does NOT
# write a second copy of the key: it appends a line to ~/.zprofile that reads
# the value back out of the Keychain at shell start. One stored secret, two ways
# to reach it, so rotating the Keychain item rotates the variable too.
#
# The Keychain item lives in ~/Library/Keychains/login.keychain-db on your
# internal disk. It has nothing to do with where this script or the repository
# is stored, and it survives unmounting any external volume.
#
# `-T /usr/bin/security` grants the `security` tool access up front, so the proxy
# reads the item without a Keychain prompt on every start.
set -eu

SERVICE="${1:-}"
ENV_NAME="${2:-}"
if [ -z "$SERVICE" ]; then
  echo "usage: $0 KEYCHAIN_SERVICE [ENV_VAR_NAME]" >&2
  echo "example: $0 CLAUDECODEX_MINIMAX_API_KEY MINIMAX_API_KEY" >&2
  exit 2
fi
for name in "$SERVICE" ${ENV_NAME:+"$ENV_NAME"}; do
  case "$name" in
    *[!A-Za-z0-9_]*) echo "invalid name: $name" >&2; exit 2 ;;
  esac
done

[ "$(uname -s)" = "Darwin" ] || {
  echo "this helper is macOS only; on Windows use windows\\save-key.ps1" >&2
  exit 2
}

ACCOUNT="${CLAUDECODEX_KEY_ACCOUNT:-$USER}"

printf 'Paste the value for %s (input hidden): ' "$SERVICE" >&2
stty -echo 2>/dev/null || true
IFS= read -r VALUE
stty echo 2>/dev/null || true
printf '\n' >&2

if [ -z "$VALUE" ]; then
  echo "no value entered, nothing written" >&2
  exit 1
fi

# -U updates an existing item instead of failing with "already exists".
security add-generic-password \
  -U -a "$ACCOUNT" -s "$SERVICE" \
  -T /usr/bin/security \
  -D "claudecodex provider key" \
  -w "$VALUE"

# Prove it reads back before reporting success, without printing the value.
if [ "$(security find-generic-password -s "$SERVICE" -a "$ACCOUNT" -w)" != "$VALUE" ]; then
  echo "wrote the item but could not read it back; check Keychain Access" >&2
  exit 1
fi
echo "Keychain: service '$SERVICE', account '$ACCOUNT'." >&2

if [ -n "$ENV_NAME" ]; then
  # ~/.zshenv, not ~/.zprofile: zprofile is read only by LOGIN shells, so a
  # plain `zsh -c` or a subshell would not see the variable. The ${VAR:-...}
  # guard means only the outermost shell pays for the Keychain lookup;
  # children inherit the exported value.
  PROFILE="$HOME/.zshenv"
  LINE="export ${ENV_NAME}=\"\${${ENV_NAME}:-\$(security find-generic-password -s ${SERVICE} -a ${ACCOUNT} -w 2>/dev/null)}\""
  touch "$PROFILE"
  TMP="$(mktemp "${TMPDIR:-/tmp}/claudecodex-key.XXXXXX")"
  trap 'rm -f "$TMP"' EXIT
  grep -v "^export ${ENV_NAME}=" "$PROFILE" > "$TMP" || true
  printf '%s\n' "$LINE" >> "$TMP"
  cat "$TMP" > "$PROFILE"
  echo "Environment: \$${ENV_NAME} in ${PROFILE}, read from the Keychain at shell start." >&2
  echo "Load it into this shell with:  . ${PROFILE}" >&2
fi

echo "Then restart the proxy:  launchctl kickstart -k gui/\$(id -u)/com.adrian.claudecodex-proxy" >&2
