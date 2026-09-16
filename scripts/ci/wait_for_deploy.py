#!/usr/bin/env python3
"""Wait until a Railway service's latest deployment (freshly triggered) is live.

The staging E2E workflows race the Railway build: on a push to main the
deployed suite would otherwise assert against the *previous* deployment while
the new image is still building (observed 2026-09-16 — three write-suite
failures that all passed against a PR env running the same commit). This
script polls the service's deployments until one created after the workflow
started reaches SUCCESS, or exits non-zero if it FAILS/CRASHES.

Usage: scripts/ci/wait_for_deploy.py <environment-name> <service-name> [timeout-seconds]

Env:
  RAILWAY_TOKEN + RAILWAY_PROJECT_ID (CI), or the CLI's linked project locally.
  DEPLOY_SINCE   ISO-8601 timestamp; deployments older than this are ignored.
                 Defaults to roughly "now" at script start.
  POLL_SECONDS   Polling interval (default 20).

Exit codes: 0 = fresh deployment live, 1 = deployment failed/crashed,
            3 = environment/service not found, 4 = timed out.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

API = "https://backboard.railway.com/graphql/v2"

TERMINAL_BAD = {"FAILED", "CRASHED"}
TERMINAL_GOOD = {"SUCCESS"}


def fail(msg: str, code: int = 1) -> None:
    print(f"wait_for_deploy: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        fail("usage: wait_for_deploy.py <environment-name> <service-name> [timeout-seconds]", 2)
    env_name, service_name = args[0], args[1]
    timeout_s = int(args[2]) if len(args) > 2 else 900
    poll_s = int(os.environ.get("POLL_SECONDS", "20"))
    since_raw = os.environ.get("DEPLOY_SINCE", "")
    if since_raw:
        since = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
    else:
        since = datetime.now(UTC) - timedelta(seconds=30)

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
    service_id = inst["serviceId"]

    query = """
        query ($env: String!, $svc: String!) {
          deployments(first: 1, input: {environmentId: $env, serviceId: $svc}) {
            edges { node { id status createdAt } }
          }
        }
    """
    deadline = time.monotonic() + timeout_s
    attempt = 0
    while True:
        attempt += 1
        data = gql(query, {"env": env["id"], "svc": service_id})
        edges = (data.get("deployments") or {}).get("edges") or []
        node = edges[0]["node"] if edges else None
        if node is not None:
            created = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))
            status = str(node.get("status") or "")
            fresh = created >= since
            print(
                f"[wait_for_deploy] latest deployment {node['id'][:8]} "
                f"status={status} created={node['createdAt']} fresh={fresh}"
            )
            if fresh and status in TERMINAL_GOOD:
                print(f"[wait_for_deploy] fresh deployment {node['id']} is live")
                return
            if fresh and status in TERMINAL_BAD:
                fail(f"fresh deployment {node['id']} terminated with status {status}", 1)
        else:
            print("[wait_for_deploy] no deployments yet")
        if time.monotonic() > deadline:
            fail(
                f"no fresh successful deployment within {timeout_s}s (since {since.isoformat()})",
                4,
            )
        time.sleep(poll_s)


if __name__ == "__main__":
    main()
