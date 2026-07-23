#!/bin/sh
# Save a provider key into the macOS login Keychain.
#
#   ./mac/save-key.sh ANYCLAUDE_MINIMAX_API_KEY
#   ./mac/save-key.sh ANYCLAUDE_DASHSCOPE_API_KEY
#
# The name you pass is the Keychain SERVICE name. Put the same string in your
# config.json as the provider's "keychain" field and the proxy reads it from
# there, so the key never lives in a dotfile, a plist, your shell history, or
# `ps` output. Re-running updates the stored value in place.
#
# `-T /usr/bin/security` grants the `security` tool access up front, so the proxy
# reads the item without a Keychain prompt on every start.
set -eu

SERVICE="${1:-}"
if [ -z "$SERVICE" ]; then
  echo "usage: $0 KEYCHAIN_SERVICE_NAME" >&2
  echo "example: $0 ANYCLAUDE_MINIMAX_API_KEY" >&2
  exit 2
fi
ACCOUNT="${2:-$USER}"

[ "$(uname -s)" = "Darwin" ] || {
  echo "this helper is macOS only; on Windows use windows\\save-key.ps1" >&2
  exit 2
}

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
  -D "anyclaude provider key" \
  -w "$VALUE"

# Prove it reads back before reporting success, without printing the value.
if [ "$(security find-generic-password -s "$SERVICE" -a "$ACCOUNT" -w)" = "$VALUE" ]; then
  echo "Saved to Keychain: service '$SERVICE', account '$ACCOUNT'." >&2
  echo "Add \"keychain\": \"$SERVICE\" to that provider in config.json, then restart the proxy." >&2
else
  echo "wrote the item but could not read it back; check Keychain Access" >&2
  exit 1
fi
