import runpy
from pathlib import Path
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parents[3]


class StagingConfig(TypedDict):
    api: dict[str, str]
    landing: dict[str, str]


def _load_staging_config() -> StagingConfig:
    namespace = runpy.run_path(str(ROOT / "scripts" / "ci" / "configure_staging.py"))
    return {
        "api": cast(dict[str, str], namespace["STAGING_API_VARIABLES"]),
        "landing": cast(dict[str, str], namespace["STAGING_LANDING_VARIABLES"]),
    }


def test_staging_mirror_uses_sandbox_and_safe_llm_caps() -> None:
    config = _load_staging_config()
    api = config["api"]

    assert api["ENVIRONMENT"] == "staging"
    assert api["PADDLE_SANDBOX"] == "true"
    assert api["LLM_MODEL"] == "openai/kimi-k2.6"
    assert api["LLM_MAX_RETRIES"] == "1"
    assert api["AI_BURST_LIMIT_PER_HOUR"] == "10"


def test_staging_mirror_enables_worker_and_rollup_schedules() -> None:
    api = _load_staging_config()["api"]

    assert api["REMINDER_SCHEDULER_ENABLED"] == "true"
    assert api["REMINDER_TICK_SECONDS"] == "300"
    assert api["ROLLUP_SCHEDULER_ENABLED"] == "true"
    assert api["ROLLUP_TICK_SECONDS"] == "60"
    assert api["SEED_DEMO_ESTATE"] == "true"


def test_staging_landing_forces_paddle_sandbox() -> None:
    landing = _load_staging_config()["landing"]

    assert landing["VITE_PADDLE_ENV"] == "sandbox"
