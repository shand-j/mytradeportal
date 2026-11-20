"""Regression checks for payment-liability copy tied to ADR-003."""

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_payments_model_describes_destination_charge_liability() -> None:
    text = (_repo_root() / "docs" / "payments-model.md").read_text(encoding="utf-8")
    assert "Stripe processing fees and dispute fees are debited from the platform" in text
    assert "reverse_transfer=true" in text


def test_help_copy_matches_destination_charge_fee_ownership() -> None:
    text = (
        _repo_root()
        / "web"
        / "landing"
        / "new design"
        / "app"
        / "src"
        / "content"
        / "help"
        / "articles.ts"
    ).read_text(encoding="utf-8")
    assert "destination-charge setup" in text
    assert "fees are debited from the platform balance first" in text
