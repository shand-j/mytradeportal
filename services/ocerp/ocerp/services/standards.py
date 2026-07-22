"""Supported regional estimating standards."""

from mtp_shared import StandardInfo, StandardsListResponse

_STANDARDS = [
    StandardInfo(code="nrm1", name="New Rules of Measurement 1 (NRM 1)", region="UK"),
    StandardInfo(code="nrm2", name="New Rules of Measurement 2 (NRM 2)", region="UK"),
    StandardInfo(code="csi", name="CSI MasterFormat", region="US"),
    StandardInfo(code="din276", name="DIN 276", region="DE"),
]


def list_standards(region: str | None = None) -> StandardsListResponse:
    """Return the list of supported estimating standards, optionally filtered by region."""
    standards = _STANDARDS
    if region:
        standards = [s for s in standards if s.region.lower() == region.lower()]
    return StandardsListResponse(standards=standards)
