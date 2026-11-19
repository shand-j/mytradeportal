"""Shared primitives for My Trade Portal V2."""

from .config import InsecureProductionConfigError, Settings, get_settings
from .embeddings import EMBEDDING_DIMENSIONS, get_embedding_dimension
from .models import TenantBase, TenantScopedModel
from .ocerp import (
    BoQGenerateRequest,
    BoQGenerateResponse,
    BoQLineItem,
    CustomerSummaryLine,
    MarginIndicator,
    PriceLookupRequest,
    PriceLookupResponse,
    QuoteAnalysis,
    RegulatoryCitation,
    RetrievalEvidence,
    StandardInfo,
    StandardsListResponse,
)
from .tenancy import TenantContext, get_tenant, require_tenant, set_tenant

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "BoQGenerateRequest",
    "BoQGenerateResponse",
    "BoQLineItem",
    "CustomerSummaryLine",
    "InsecureProductionConfigError",
    "MarginIndicator",
    "PriceLookupRequest",
    "PriceLookupResponse",
    "QuoteAnalysis",
    "RegulatoryCitation",
    "RetrievalEvidence",
    "Settings",
    "StandardInfo",
    "StandardsListResponse",
    "TenantBase",
    "TenantContext",
    "TenantScopedModel",
    "get_embedding_dimension",
    "get_settings",
    "get_tenant",
    "require_tenant",
    "set_tenant",
]
