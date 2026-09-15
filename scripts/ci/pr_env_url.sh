#!/usr/bin/env bash
# Resolve the public URLs of a Railway PR environment for a GitHub PR.
#
# Usage: scripts/ci/pr_env_url.sh <pr-number>
#
# Resolution order (first hit wins), for both the api and landing services:
#   1. Explicit overrides: RAILWAY_PR_API_URL / RAILWAY_PR_LANDING_URL env vars.
#   2. Railway CLI discovery:
#        railway environment list --ephemeral --json   -> find the ephemeral
#          environment Railway's GitHub integration created for this PR
#          (named "pr-<number>" / "pr-<number>-<branch>"), then
#        railway domain list --service <svc> --environment <env> --json
#          -> first service-type domain (custom domains are ignored).
#
# Requires the Railway CLI (v3.5+) authenticated via RAILWAY_TOKEN (CI) or an
# interactive login (local). The project is resolved from the linked project
# directory (.railway) or RAILWAY_PROJECT_ID.
#
# Output (also appendable to GITHUB_OUTPUT):
#   api_url=<https://...>
#   landing_url=<https://...>
#
# Exit codes: 0 = resolved, 2 = usage error, 3 = no PR env found yet,
#             4 = PR env found but a service has no public domain.

set -euo pipefail

PR_NUMBER="${1:-${PR_NUMBER:-}}"
if [[ -z "$PR_NUMBER" ]]; then
  echo "usage: $0 <pr-number>  (or set PR_NUMBER)" >&2
  exit 2
fi

RAILWAY_BIN="${RAILWAY_BIN:-railway}"

service_domain() {
  # $1 = service name, $2 = environment name -> prints https://<domain>
  local service="$1" env_name="$2"
  local domains_json
  domains_json="$("$RAILWAY_BIN" domain list --service "$service" --environment "$env_name" --json)"
  DOMAINS_JSON="$domains_json" python3 - "$service" "$env_name" <<'PY'
import json
import os
import sys

service, env_name = sys.argv[1], sys.argv[2]
raw = os.environ["DOMAINS_JSON"].strip()
try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    print(f"could not parse domain list output for '{service}': {raw[:200]}", file=sys.stderr)
    sys.exit(4)
items = payload.get("domains", payload if isinstance(payload, list) else [])
for item in items:
    if isinstance(item, str):
        print(f"https://{item}")
        sys.exit(0)
    if item.get("type") == "service" and item.get("syncStatus") in (None, "ACTIVE"):
        print(f"https://{item['domain']}")
        sys.exit(0)
print(f"no active service domain for '{service}' in environment '{env_name}'", file=sys.stderr)
sys.exit(4)
PY
}

find_pr_environment() {
  # Prints the ephemeral environment name matching this PR number, or exits 3.
  local envs_json
  envs_json="$("$RAILWAY_BIN" environment list --ephemeral --json)"
  ENVS_JSON="$envs_json" PR_NUMBER="$PR_NUMBER" python3 <<'PY'
import json
import os
import re
import sys

pr_number = os.environ["PR_NUMBER"]
raw = os.environ["ENVS_JSON"].strip()
try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    print(f"could not parse 'railway environment list --json' output: {raw[:200]}", file=sys.stderr)
    sys.exit(3)

nodes = []
if isinstance(payload, list):
    nodes = payload
elif isinstance(payload, dict):
    if isinstance(payload.get("environments"), list):
        nodes = payload["environments"]
    else:
        edges = payload.get("environments", {}).get("edges", [])
        nodes = [e.get("node", {}) for e in edges]

# Railway names PR environments "pr-<number>" or "pr-<number>-<branch>".
pattern = re.compile(rf"^pr-{re.escape(pr_number)}(?:[-_.].*)?$", re.IGNORECASE)
matches = [n["name"] for n in nodes if isinstance(n, dict) and n.get("name") and pattern.match(n["name"])]
if matches:
    print(sorted(matches)[0])
    sys.exit(0)
available = ", ".join(n.get("name", "?") for n in nodes) or "(none)"
print(
    f"no ephemeral PR environment found for PR #{pr_number}; available: {available}. "
    "Railway creates it when the PR opens - re-run shortly.",
    file=sys.stderr,
)
sys.exit(3)
PY
}

API_URL="${RAILWAY_PR_API_URL:-}"
LANDING_URL="${RAILWAY_PR_LANDING_URL:-}"

if [[ -z "$API_URL" || -z "$LANDING_URL" ]]; then
  ENV_NAME="$(find_pr_environment)"
  echo "resolved Railway PR environment: $ENV_NAME" >&2
  if [[ -z "$API_URL" ]]; then
    API_URL="$(service_domain api "$ENV_NAME")"
  fi
  if [[ -z "$LANDING_URL" ]]; then
    LANDING_URL="$(service_domain landing "$ENV_NAME")"
  fi
fi

{
  echo "api_url=$API_URL"
  echo "landing_url=$LANDING_URL"
}
