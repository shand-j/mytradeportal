"""Fail-fast, secret-free preflight for live security audit tenants."""

import httpx

from security.config import config


def validate_target() -> None:
    config.validate()

    credentials = (
        ("primary", config.tenant_slug, config.admin_email, config.admin_password),
        (
            "secondary",
            config.secondary_tenant_slug,
            config.secondary_admin_email,
            config.secondary_admin_password,
        ),
    )

    with httpx.Client(base_url=config.api_base_url, follow_redirects=False) as client:
        for label, tenant_slug, email, password in credentials:
            response = client.post(
                "/auth/login",
                data={
                    "tenant_slug": tenant_slug,
                    "email": email,
                    "password": password,
                },
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"{label} security tenant login failed with HTTP {response.status_code}"
                )
            print(f"{label.capitalize()} security tenant access OK")


if __name__ == "__main__":
    validate_target()
