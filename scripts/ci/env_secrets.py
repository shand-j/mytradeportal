#!/usr/bin/env python3
"""Print selected variables of a Railway service as NAME=value lines.

Usage: scripts/ci/env_secrets.py <environment-name> <service-name> [--prefix P] KEY [KEY...]

Resolves the environment by exact name, reads the service's variables via
Railway's GraphQL API (same auth + UA workaround as scripts/ci/env_url.sh —
the Railway CLI rejects the project token used in CI), and prints one
``NAME=value`` line per requested key that exists. Missing keys are skipped
with a warning on stderr so callers can decide whether they are required.

Typical CI use (append to GITHUB_ENV so later steps get the values):

    python3 scripts/ci/env_secrets.py staging api \
        --prefix TEST_ STRIPE_WEBHOOK_SECRET PADDLE_WEBHOOK_SECRET >> "$GITHUB_ENV"

Auth: RAILWAY_TOKEN + RAILWAY_PROJECT_ID (CI), or the CLI's linked project
config for local use.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://backboard.railway.com/graphql/v2"


def fail(msg: str, code: int = 1) -> None:
    print(f"env_secrets: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 3:
        fail("usage: env_secrets.py <environment-name> <service-name> [--prefix P] KEY...", 2)
    env_name, service_name, rest = args[0], args[1], args[2:]
    prefix = ""
    if rest[:1] == ["--prefix"]:
        if len(rest) < 2:
            fail("--prefix requires a value", 2)
        prefix, rest = rest[1], rest[2:]
    keys = rest
    if not keys:
        fail("at least one variable name is required", 2)

    token = os.environ.get("RAILWAY_TOKEN", "")
    project_id = os.environ.get("RAILWAY_PROJECT_ID", "")
    if not project_id:
        cfg_path = os.path.expanduser("~/.railway/config.json")
        try:
            with open(cfg_path) as fh:
                projects = json.load(fh).get("projects", {})
            project_id = next((p.get("project") for p in projects.values() if p.get("project")), "")
        except (OSError, json.JSONDecodeError):
            project_id = ""
    if not token or not project_id:
        fail("RAILWAY_TOKEN and RAILWAY_PROJECT_ID are required (or a linked project locally)")

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
            fail(f"Railway API HTTP {exc.code}: {exc.read()[:200]!r}")
        except urllib.error.URLError as exc:
            fail(f"Railway API unreachable: {exc}")
        if payload.get("errors"):
            fail(f"Railway API error: {payload['errors']}")
        return payload["data"]

    data = gql(
        """
        query ($id: String!) {
          project(id: $id) {
            environments { edges { node { id name } } }
          }
        }
        """,
        {"id": project_id},
    )
    nodes = [e["node"] for e in data["project"]["environments"]["edges"] if e.get("node")]
    env = next((n for n in nodes if n.get("name") == env_name), None)
    if env is None:
        available = ", ".join(n.get("name", "?") for n in nodes) or "(none)"
        fail(f"no environment named '{env_name}'; available: {available}", 3)

    data = gql(
        """
        query ($id: String!) {
          environment(id: $id) {
            serviceInstances {
              edges { node { serviceId serviceName } }
            }
          }
        }
        """,
        {"id": env["id"]},
    )
    instances = [
        e["node"] for e in data["environment"]["serviceInstances"]["edges"] if e.get("node")
    ]
    inst = next((i for i in instances if i.get("serviceName") == service_name), None)
    if inst is None or not inst.get("serviceId"):
        fail(f"no service instance named '{service_name}' in environment '{env_name}'", 3)

    data = gql(
        """
        query ($env: String!, $proj: String!, $svc: String!) {
          variables(environmentId: $env, projectId: $proj, serviceId: $svc)
        }
        """,
        {"env": env["id"], "proj": project_id, "svc": inst["serviceId"]},
    )
    existing = data.get("variables") or {}
    for key in keys:
        value = existing.get(key)
        if value is None or value == "":
            print(
                f"env_secrets: {key} not set on {service_name}/{env_name} — skipping",
                file=sys.stderr,
            )
            continue
        print(f"{prefix}{key}={value}")


if __name__ == "__main__":
    main()
