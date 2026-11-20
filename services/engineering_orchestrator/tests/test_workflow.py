from pathlib import Path

import yaml


def test_hotfix_workflow_has_staging_and_rollback_gates() -> None:
    workflow_path = Path(__file__).parents[3] / ".github" / "workflows" / "hotfix.yml"
    workflow = yaml.safe_load(workflow_path.read_text())
    jobs = workflow["jobs"]
    assert jobs["staging"]["needs"] == "verify"
    assert jobs["production"]["needs"] == "staging"
    assert "always()" in jobs["rollback"]["if"]
    text = workflow_path.read_text()
    assert "--service" in text
    assert "railway down" in text
    assert "agent:ready" not in text
