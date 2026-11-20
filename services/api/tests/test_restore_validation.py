import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_restore  # noqa: E402


def test_require_ok_rejects_http_error():
    try:
        validate_restore._require_ok("check", 503, b'{"status":"not_ready"}')
    except RuntimeError as exc:
        assert "HTTP 503" in str(exc)
    else:
        raise AssertionError("HTTP 503 should fail validation")


def test_validate_ready_accepts_ready_payload():
    payload = json.dumps(
        {
            "status": "ready",
            "checks": {"postgres": "ok", "storage": "ok"},
        }
    ).encode()
    with patch.object(validate_restore, "_http", return_value=(200, payload, {})):
        result = validate_restore.validate_ready("https://isolated.example")
    assert result["status"] == "ready"


def test_validate_ready_rejects_not_ready_payload():
    payload = json.dumps(
        {
            "status": "not_ready",
            "checks": {"postgres": "error", "storage": "ok"},
        }
    ).encode()
    with patch.object(validate_restore, "_http", return_value=(503, payload, {})):
        try:
            validate_restore.validate_ready("https://isolated.example")
        except RuntimeError as exc:
            assert "/ready: HTTP 503" in str(exc)
            assert "not_ready" in str(exc)
        else:
            raise AssertionError("not_ready should fail validation")
