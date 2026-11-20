#!/usr/bin/env python3
"""Apply the cost-safe, production-mirror variable set to the staging API.

This is intentionally idempotent and only changes variables explicitly named
below.  It never writes credentials or Paddle/LLM secrets.

Usage:
    RAILWAY_TOKEN=... RAILWAY_PROJECT_ID=... python3 scripts/ci/configure_staging.py

The pinned environment id used by CI can be supplied as RAILWAY_ENVIRONMENT_ID.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://backboard.railway.com/graphql/v2"

STAGING_API_VARIABLES = {
    "ENVIRONMENT": "staging",
    "REMINDER_SCHEDULER_ENABLED": "true",
    "REMINDER_TICK_SECONDS": "300",
    "ROLLUP_SCHEDULER_ENABLED": "true",
    "ROLLUP_TICK_SECONDS": "60",
    "ROLLUP_RUN_HOUR_UTC": "2",
    "ROLLUP_RUN_MINUTE_UTC": "30",
    "PADDLE_SANDBOX": "true",
    "LLM_MODEL": "openai/kimi-k2.6",
    "LLM_REFINE_MODEL": "openai/kimi-k2.6",
    "LLM_FOLLOWUP_MODEL": "openai/kimi-k2.6",
    "INTAKE_TRIAGE_MODEL": "openai/kimi-k2.6",
    "LLM_MAX_RETRIES": "1",
    "LLM_TIMEOUT_SECONDS": "60",
    "AI_BURST_LIMIT_PER_HOUR": "10",
    "AI_FAIR_USE_MONTHLY_THRESHOLD": "100",
    "SMS_REMINDERS_ENABLED": "false",
    "SEED_DEMO_ESTATE": "true",
}

STAGING_LANDING_VARIABLES = {
    "VITE_PADDLE_ENV": "sandbox",
}


def fail(msg: str, code: int = 1) -> None:
    print(f"configure_staging: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> None:
    token = os.environ.get("RAILWAY_TOKEN", "")
    project_id = os.environ.get("RAILWAY_PROJECT_ID", "")
    env_name = os.environ.get("RAILWAY_ENVIRONMENT_NAME", "staging")
    env_id = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")
    if not project_id and not env_id:
        cfg_path = os.path.expanduser("~/.railway/config.json")
        try:
            with open(cfg_path) as fh:
                projects = json.load(fh).get("projects", {})
            project_id = next(
                (p.get("project") for p in projects.values() if p.get("project")),
                "",
            )
        except (OSError, json.JSONDecodeError):
            project_id = ""
    if not token or (not project_id and not env_id):
        fail("RAILWAY_TOKEN and RAILWAY_PROJECT_ID (or RAILWAY_ENVIRONMENT_ID) are required")

    auth_scheme = "bearer"

    def gql(query: str, variables: dict | None = None) -> dict:
        nonlocal auth_scheme
        for attempt in range(2):
            scheme = (
                auth_scheme
                if attempt == 0
                else ("project-token" if auth_scheme == "bearer" else "bearer")
            )
            headers = {"Content-Type": "application/json", "User-Agent": "curl/8.0"}
            if scheme == "bearer":
                headers["Authorization"] = "******"
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
        fail("Railway API: Not Authorized with both bearer and project-access-token auth")

    if not env_id:
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
        nodes = [
            edge["node"] for edge in data["project"]["environments"]["edges"] if edge.get("node")
        ]
        env = next((node for node in nodes if node.get("name") == env_name), None)
        if env is None:
            fail(f"no environment named '{env_name}'", 3)
        env_id = env["id"]

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
        {"id": env_id},
    )
    instances = [
        edge["node"]
        for edge in data["environment"]["serviceInstances"]["edges"]
        if edge.get("node")
    ]

    for service_name, variables in (
        ("api", STAGING_API_VARIABLES),
        ("landing", STAGING_LANDING_VARIABLES),
    ):
        instance = next(
            (item for item in instances if item.get("serviceName") == service_name),
            None,
        )
        if instance is None or not instance.get("serviceId"):
            print(
                f"configure_staging: {service_name} service not present in staging - skipping",
                file=sys.stderr,
            )
            continue
        gql(
            """
            mutation ($input: VariableCollectionUpsertInput!) {
              variableCollectionUpsert(input: $input)
            }
            """,
            {
                "input": {
                    "environmentId": env_id,
                    "projectId": project_id,
                    "serviceId": instance["serviceId"],
                    "variables": variables,
                }
            },
        )
        print(f"configured {service_name}: {len(variables)} staging variables")


if __name__ == "__main__":
    main()
