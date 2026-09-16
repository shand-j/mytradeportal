#!/usr/bin/env bash
# Resolve the public URLs of a named Railway environment (e.g. "staging").
#
# Usage: scripts/ci/env_url.sh <environment-name>
#
# Resolution order (first hit wins), for both the api and landing services:
#   1. Explicit overrides: RAILWAY_ENV_API_URL / RAILWAY_ENV_LANDING_URL env vars.
#   2. Railway GraphQL API discovery: match the environment by exact name,
#      then list each service's service domains and pick the first ACTIVE
#      Railway-generated (.up.railway.app) domain, oldest first.
#
# Auth: RAILWAY_TOKEN (a Railway account/workspace API token) sent as
# `Authorization: Bearer`. Note: recent Railway CLI versions (observed on
# v5.28) reject newer workspace tokens with "Invalid RAILWAY_TOKEN", which is
# why this script talks to the GraphQL API directly instead of shelling out.
# The project is resolved from RAILWAY_PROJECT_ID (CI) or the CLI's linked
# project config (.railway/config.json, local use).
#
# Output (also appendable to GITHUB_OUTPUT):
#   api_url=<https://...>
#   landing_url=<https://...>
#
# Exit codes: 0 = resolved, 2 = usage error, 3 = environment not found or
#             Railway API unreachable, 4 = environment found but a service
#             has no public domain.

set -euo pipefail

ENV_NAME="${1:-${ENV_NAME:-}}"
if [[ -z "$ENV_NAME" ]]; then
  echo "usage: $0 <environment-name>  (or set ENV_NAME)" >&2
  exit 2
fi

API_URL="${RAILWAY_ENV_API_URL:-}"
LANDING_URL="${RAILWAY_ENV_LANDING_URL:-}"

if [[ -z "$API_URL" || -z "$LANDING_URL" ]]; then
  ENV_NAME="$ENV_NAME" python3 <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

env_name = os.environ["ENV_NAME"]
token = os.environ.get("RAILWAY_TOKEN", "")
project_id = os.environ.get("RAILWAY_PROJECT_ID", "")
if not token:
    print("RAILWAY_TOKEN is not set", file=sys.stderr)
    sys.exit(3)
if not project_id:
    cfg_path = os.path.expanduser("~/.railway/config.json")
    try:
        with open(cfg_path) as fh:
            projects = json.load(fh).get("projects", {})
        project_id = next(
            (p.get("project") for p in projects.values() if p.get("project")), ""
        )
    except (OSError, json.JSONDecodeError):
        project_id = ""
if not project_id:
    print(
        "no project: set RAILWAY_PROJECT_ID or link a project (railway link)",
        file=sys.stderr,
    )
    sys.exit(3)

API = "https://backboard.railway.com/graphql/v2"


def gql(query: str, variables: dict | None = None) -> dict:
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # Cloudflare on backboard blocks the default Python-urllib UA (1010).
            "User-Agent": "curl/8.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read()[:200].decode(errors="replace")
        print(f"Railway API HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(3)
    except urllib.error.URLError as exc:
        print(f"Railway API unreachable: {exc}", file=sys.stderr)
        sys.exit(3)
    if payload.get("errors"):
        print(f"Railway API error: {payload['errors']}", file=sys.stderr)
        sys.exit(3)
    return payload["data"]


# 1. Find the named environment.
data = gql(
    """
    query ($id: String!) {
      project(id: $id) {
        environments { edges { node { id name isEphemeral } } }
      }
    }
    """,
    {"id": project_id},
)
nodes = [e["node"] for e in data["project"]["environments"]["edges"] if e.get("node")]
envs = [n for n in nodes if n.get("name") == env_name]
if not envs:
    available = ", ".join(n.get("name", "?") for n in nodes) or "(none)"
    print(
        f"no environment named '{env_name}'; available: {available}",
        file=sys.stderr,
    )
    sys.exit(3)
env = envs[0]

# 2. List service domains in that environment.
data = gql(
    """
    query ($id: String!) {
      environment(id: $id) {
        serviceInstances {
          edges { node { serviceName domains { serviceDomains { domain targetPort syncStatus createdAt } } } }
        }
      }
    }
    """,
    {"id": env["id"]},
)
instances = [
    e["node"] for e in data["environment"]["serviceInstances"]["edges"] if e.get("node")
]


def service_url(service: str) -> str | None:
    for inst in instances:
        if inst.get("serviceName") != service:
            continue
        domains = (inst.get("domains") or {}).get("serviceDomains") or []
        active = [
            d
            for d in domains
            if d.get("domain")
            and d["domain"].endswith(".up.railway.app")
            and d.get("syncStatus") in (None, "ACTIVE")
        ]
        if active:
            active.sort(key=lambda d: d.get("createdAt") or "")
            return f"https://{active[0]['domain']}"
    return None


missing = []
for svc, var in (("api", "api_url"), ("landing", "landing_url")):
    override = os.environ.get(f"RAILWAY_ENV_{var.upper()}", "")
    if override:
        print(f"{var}={override}")
        continue
    url = service_url(svc)
    if not url:
        missing.append(svc)
        continue
    print(f"{var}={url}")

if missing:
    print(
        f"no active Railway service domain for: {', '.join(missing)} "
        f"in environment '{env['name']}'",
        file=sys.stderr,
    )
    sys.exit(4)
PY
fi
