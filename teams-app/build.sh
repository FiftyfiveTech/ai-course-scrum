#!/usr/bin/env bash
# Build teams-app/manifest.json from the template.
#
# Reads MICROSOFT_APP_ID and RAILWAY_DOMAIN from the environment (or .env).
# Writes manifest.json and zips the package as scrum-bot.zip.
#
# Usage:
#   MICROSOFT_APP_ID=<uuid> RAILWAY_DOMAIN=<host> ./teams-app/build.sh
#   # or load your .env first:
#   set -a && source .env && set +a && ./teams-app/build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- load .env if the caller hasn't already set the vars ---
if [[ -z "${MICROSOFT_APP_ID:-}" || -z "${RAILWAY_DOMAIN:-}" ]]; then
  ENV_FILE="${SCRIPT_DIR}/../.env"
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
fi

# --- validate required vars ---
: "${MICROSOFT_APP_ID:?MICROSOFT_APP_ID is not set}"
: "${RAILWAY_DOMAIN:?RAILWAY_DOMAIN is not set}"

# --- substitute and write manifest.json ---
sed \
  -e "s|\${MICROSOFT_APP_ID}|${MICROSOFT_APP_ID}|g" \
  -e "s|\${RAILWAY_DOMAIN}|${RAILWAY_DOMAIN}|g" \
  "${SCRIPT_DIR}/manifest.template.json" \
  > "${SCRIPT_DIR}/manifest.json"

echo "wrote teams-app/manifest.json"

# --- check icons are present ---
for ICON in color.png outline.png; do
  if [[ ! -f "${SCRIPT_DIR}/${ICON}" ]]; then
    echo "WARNING: ${ICON} is missing — add it before uploading to the Developer Portal (POC-17)"
  fi
done

# --- zip the package ---
cd "${SCRIPT_DIR}"
zip -j scrum-bot.zip manifest.json color.png outline.png 2>/dev/null \
  || zip -j scrum-bot.zip manifest.json  # icons missing — zip without them, still validates schema

echo "wrote teams-app/scrum-bot.zip"
echo ""
echo "Next: upload scrum-bot.zip to https://dev.teams.microsoft.com/apps and click 'Validate'"
