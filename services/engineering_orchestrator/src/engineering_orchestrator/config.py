from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ENGINEERING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: str = "dry_run"
    database_url: str = "sqlite:///./engineering-orchestrator.db"
    repository: str = "shand-j/mytradeportal"
    base_branch: str = "main"
    worker_count: int = 1
    api_auth_token: SecretStr = SecretStr("")

    github_api_url: str = "https://api.github.com"
    github_token: SecretStr = SecretStr("")
    sandbox_github_token: SecretStr = SecretStr("")
    github_app_id: str = ""
    github_app_installation_id: str = ""
    github_app_private_key: SecretStr = SecretStr("")
    github_webhook_secret: SecretStr = SecretStr("")
    alert_webhook_secret: SecretStr = SecretStr("")
    testflight_webhook_secret: SecretStr = SecretStr("")

    model: str = "openai/gpt-4.1-mini"
    llm_timeout_seconds: int = 90

    railway_project: str = ""
    railway_environment: str = "engineering"
    sandbox_checkpoint: str = "mtp-engineering-base"
    sandbox_idle_timeout_minutes: int = 60
    sandbox_command_timeout_seconds: int = 900
    sandbox_private_network: bool = False
    sandbox_workspace: str = "/workspace/mytradeportal"
    kimi_model: str = "kimi-code/kimi-for-coding"
    kimi_model_api_key: SecretStr = SecretStr("")
    kimi_model_base_url: str = ""
    kimi_max_steps: int = 80
    verify_commands: list[str] = Field(
        default_factory=lambda: [
            "ruff check .",
            "ruff format --check .",
            "pytest services/engineering_orchestrator/tests -q -o addopts=''",
        ]
    )

    hotfix_enabled: bool = False
    hotfix_workflow: str = "hotfix.yml"
    hotfix_staging_health_url: str = ""
    hotfix_production_health_url: str = ""
    hotfix_allowed_services: list[str] = Field(default_factory=list)
    hotfix_allowed_path_prefixes: list[str] = Field(default_factory=list)
    hotfix_max_changed_files: int = 5
    hotfix_max_diff_lines: int = 200
    hotfix_wait_seconds: int = 1800
    hotfix_poll_seconds: int = 15

    testflight_enabled: bool = False
    testflight_poll_seconds: int = 300
    appstore_api_url: str = "https://api.appstoreconnect.apple.com"
    appstore_app_id: str = ""
    appstore_key_id: str = ""
    appstore_issuer_id: str = ""
    appstore_private_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "ENGINEERING_APPSTORE_PRIVATE_KEY",
            "ENGINEERING_APPSTORE_PRIVATE_KEY_PATH",
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        if self.mode not in {"dry_run", "live"}:
            raise ValueError("ENGINEERING_MODE must be 'dry_run' or 'live'")
        if "/" not in self.repository:
            raise ValueError("ENGINEERING_REPOSITORY must use owner/name format")

    @model_validator(mode="after")
    def validate_live_configuration(self) -> Settings:
        if self.mode != "live":
            return self
        if not self.github_token.get_secret_value() and not self.github_app_id:
            raise ValueError("Live mode requires a GitHub token or GitHub App configuration")
        if not self.sandbox_checkpoint:
            raise ValueError("Live mode requires ENGINEERING_SANDBOX_CHECKPOINT")
        controller_token = self.github_token.get_secret_value()
        sandbox_token = self.sandbox_github_token.get_secret_value()
        if controller_token and (not sandbox_token or sandbox_token == controller_token):
            raise ValueError(
                "Live static-token mode requires a distinct sandbox GitHub token without Actions permission"
            )
        if not self.github_webhook_secret.get_secret_value():
            raise ValueError("Live mode requires ENGINEERING_GITHUB_WEBHOOK_SECRET")
        if not self.api_auth_token.get_secret_value():
            raise ValueError("Live mode requires ENGINEERING_API_AUTH_TOKEN")
        if self.hotfix_enabled and (
            not self.hotfix_allowed_services or not self.hotfix_allowed_path_prefixes
        ):
            raise ValueError("Autonomous hotfixes require explicit service and path allow-lists")
        return self

    def appstore_key(self) -> str:
        value = self.appstore_private_key.get_secret_value()
        if value.startswith("-----BEGIN"):
            return value.replace("\\n", "\n")
        if value:
            from pathlib import Path

            return Path(value).expanduser().read_text()
        return ""

    def public_config(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "repository": self.repository,
            "base_branch": self.base_branch,
            "hotfix_enabled": self.hotfix_enabled,
            "testflight_enabled": self.testflight_enabled,
            "sandbox_checkpoint": self.sandbox_checkpoint,
        }

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)
