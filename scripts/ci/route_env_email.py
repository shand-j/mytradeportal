#!/usr/bin/env python3
"""Route a Railway environment's api email transport from Resend to Mailpit.

Usage: scripts/ci/route_env_email.py <environment-id>

PR/staging environments are throwaway forks of production whose api would
otherwise send real email through Resend during E2E (cost + quota). The api's
email helper prefers Resend whenever RESEND_API_KEY is set and falls back to
SMTP otherwise, so routing is: delete the api's RESEND_API_KEY, upsert the
SMTP_* vars pointing at the shared staging Mailpit instance.

Talks to Railway's GraphQL API directly (same auth + UA workaround as
scripts/ci/pr_env_url.sh) because the Railway CLI rejects the project token
used in CI. Triggers a single api redeploy via the upsert's default
(skipDeploys=false).

Config comes from the environment:
  MAILPIT_SMTP       "host:port" of Mailpit's public SMTP endpoint
  MAILPIT_BASIC_AUTH "user:password" (SMTP auth == UI basic auth user/pass)
  RAILWAY_TOKEN / RAILWAY_PROJECT_ID  (same as pr_env_url.sh; falls back to
                      the CLI's linked project config for local use)

SMTP_FROM_EMAIL / SMTP_FROM_NAME are fixed to the platform quotes@ identity.
Exits 0 even when RESEND_API_KEY is already absent (idempotent re-runs).
"""

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://backboard.railway.com/graphql/v2"


def fail(msg: str, code: int = 1) -> None:
    print(f"route_env_email: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> None:
    env_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RAILWAY_ENV_ID", "")
    if not env_id:
        fail("usage: route_env_email.py <environment-id>", 2)

    mailpit_smtp = os.environ.get("MAILPIT_SMTP", "")
    mailpit_auth = os.environ.get("MAILPIT_BASIC_AUTH", "")
    if ":" not in mailpit_smtp or ":" not in mailpit_auth:
        fail("MAILPIT_SMTP (host:port) and MAILPIT_BASIC_AUTH (user:pass) are required")
    smtp_host, smtp_port = mailpit_smtp.rsplit(":", 1)
    smtp_user, smtp_pass = mailpit_auth.split(":", 1)

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

    # 1. Find the api service instance in this environment.
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
        e["node"] for e in data["environment"]["serviceInstances"]["edges"] if e.get("node")
    ]
    api_inst = next((i for i in instances if i.get("serviceName") == "api"), None)
    if api_inst is None or not api_inst.get("serviceId"):
        fail(f"no api service instance found in environment {env_id}")
    service_id = api_inst["serviceId"]

    # 2. Delete RESEND_API_KEY if present (delete of a missing var is an error,
    #    so look before leaping).
    data = gql(
        """
        query ($env: String!, $proj: String!, $svc: String!) {
          variables(
            environmentId: $env
            projectId: $proj
            serviceId: $svc
          )
        }
        """,
        {"env": env_id, "proj": project_id, "svc": service_id},
    )
    existing = data.get("variables") or {}
    if "RESEND_API_KEY" in existing:
        gql(
            """
            mutation ($input: VariableDeleteInput!) {
              variableDelete(input: $input)
            }
            """,
            {
                "input": {
                    "environmentId": env_id,
                    "projectId": project_id,
                    "serviceId": service_id,
                    "name": "RESEND_API_KEY",
                }
            },
        )
        print("deleted RESEND_API_KEY")
    else:
        print("RESEND_API_KEY not present - email already routed")

    # 3. Upsert the SMTP vars (one mutation -> one api redeploy).
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
                "serviceId": service_id,
                "variables": {
                    "SMTP_HOST": smtp_host,
                    "SMTP_PORT": smtp_port,
                    "SMTP_USE_TLS": "false",
                    "SMTP_USERNAME": smtp_user,
                    "SMTP_PASSWORD": smtp_pass,
                    "SMTP_FROM_EMAIL": "quotes@mytradeportal.co.uk",
                    "SMTP_FROM_NAME": "My Trade Portal",
                },
            }
        },
    )
    print(f"api email in environment {env_id} routed to Mailpit ({smtp_host}:{smtp_port})")


if __name__ == "__main__":
    main()
