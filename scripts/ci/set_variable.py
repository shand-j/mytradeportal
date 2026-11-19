#!/usr/bin/env python3
"""Set one variable on a Railway service via the GraphQL API.

The Railway CLI (v5.28+) rejects the newer project tokens used in CI with
"Invalid RAILWAY_TOKEN" (same reason scripts/ci/env_secrets.py and
pr_env_url.sh talk GraphQL directly), so workflows must not shell out to
``railway variable set``.

Usage: scripts/ci/set_variable.py <environment-name> <service-name> <KEY> <VALUE>

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
    print(f"set_variable: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> None:
    args = sys.argv[1:]
    if len(args) != 4:
        fail("usage: set_variable.py <environment-name> <service-name> <KEY> <VALUE>", 2)
    env_name, service_name, key, value = args

    token = os.environ.get("RAILWAY_TOKEN", "")
    project_id = os.environ.get("RAILWAY_PROJECT_ID", "")
    # Environment-scoped tokens cannot run project(id); pin the environment
    # id directly instead of discovering it via the project.
    pinned_env_id = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")
    if not project_id and not pinned_env_id:
        cfg_path = os.path.expanduser("~/.railway/config.json")
        try:
            with open(cfg_path) as fh:
                projects = json.load(fh).get("projects", {})
            project_id = next((p.get("project") for p in projects.values() if p.get("project")), "")
        except (OSError, json.JSONDecodeError):
            project_id = ""
    if not token or (not project_id and not pinned_env_id):
        fail("RAILWAY_TOKEN and RAILWAY_PROJECT_ID (or RAILWAY_ENVIRONMENT_ID) are required")

    # Account/workspace tokens authenticate as Bearer; project tokens (the
    # environment-scoped CI tokens) must use the Project-Access-Token header.
    # Try Bearer first and fall back once on "Not Authorized", remembering
    # the scheme that worked for the rest of the process.
    auth_scheme = "bearer"

    def gql(query: str, variables: dict | None = None) -> dict:
        nonlocal auth_scheme
        for attempt in range(2):
            scheme = (
                auth_scheme
                if attempt == 0
                else ("project-token" if auth_scheme == "bearer" else "bearer")
            )
            headers = {
                "Content-Type": "application/json",
                # Cloudflare on backboard blocks the default Python-urllib UA (1010).
                "User-Agent": "curl/8.0",
            }
            if scheme == "bearer":
                headers["Authorization"] = f"Bearer {token}"
            else:
                headers["project-access-token"] = token
            req = urllib.request.Request(
                API,
                data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.load(resp)
            except urllib.error.HTTPError as exc:
                fail(f"Railway API HTTP {exc.code}: {exc.read()[:200]!r}")
            except urllib.error.URLError as exc:
                fail(f"Railway API unreachable: {exc}")
            errors = payload.get("errors") or []
            if any("Not Authorized" in str(e.get("message", "")) for e in errors):
                continue
            if errors:
                fail(f"Railway API error: {errors}")
            auth_scheme = scheme
            return payload["data"]
        fail("Railway API: Not Authorized with both Bearer and project-access-token auth")

    if pinned_env_id:
        env = {"id": pinned_env_id, "name": env_name}
    else:
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

    gql(
        """
        mutation ($input: VariableCollectionUpsertInput!) {
          variableCollectionUpsert(input: $input)
        }
        """,
        {
            "input": {
                "environmentId": env["id"],
                "projectId": project_id,
                "serviceId": inst["serviceId"],
                "variables": {key: value},
            }
        },
    )
    print(f"set {key} on {service_name}/{env_name}")


if __name__ == "__main__":
    main()
