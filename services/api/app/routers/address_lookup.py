"""Address lookup integration endpoints.

Proxy Fetchify requests through the API to avoid exposing provider tokens
in the browser and to bypass cross-origin restrictions.
"""

import os
import re
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies import ActiveUserDep

router = APIRouter(prefix="/integrations/address", tags=["Address Lookup"])

DEFAULT_TIMEOUT = httpx.Timeout(8.0, connect=3.0)
FETCHIFY_RAPIDADDRESS_URL = "https://pcls1.craftyclicks.co.uk/json/rapidaddress"
STATUS_OK = "ok"
STATUS_NO_RESULTS = "no_results"
STATUS_UNAVAILABLE = "unavailable"
PROVIDER_ERROR_DETAIL = "Address provider request failed"


class AddressSuggestion(BaseModel):
    id: str
    address: str


class AddressAutocompleteResponse(BaseModel):
    suggestions: list[AddressSuggestion]
    status: str


class AddressDetailResponse(BaseModel):
    formatted_address: list[str]
    postcode: str | None = None


def _normalize_postcode(value: str) -> str:
    compact = value.strip().replace(" ", "").upper()
    match = re.match(r"^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})$", compact)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return compact


def _encode_query_value(value: str) -> str:
    return quote(value, safe="")


def _get_address_token() -> str:
    # Prefer server-only Fetchify env var. Legacy provider names remain
    # as temporary fallbacks for in-place migration.
    return (
        settings.fetchify_api_key
        or os.getenv("FETCHIFY_API_KEY", "")
        or settings.ideal_postcodes_api_key
        or settings.getaddress_io_api_key
        or os.getenv("IDEAL_POSTCODES_API_KEY", "")
        or os.getenv("GETADDRESS_IO_API_KEY", "")
        or os.getenv("VITE_GETADDRESS_IO_API_KEY", "")
    ).strip()


def _formatted_address_from_payload(payload: dict) -> list[str]:
    formatted = payload.get("formatted_address")
    if isinstance(formatted, list):
        return [str(part).strip() for part in formatted if str(part).strip()]

    parts = [
        payload.get("line_1"),
        payload.get("line_2"),
        payload.get("line_3"),
        payload.get("line_4"),
        payload.get("town_or_city"),
        payload.get("county"),
    ]
    return [str(part).strip() for part in parts if part and str(part).strip()]


def _build_fetchify_line_parts(
    delivery_point: dict[str, Any],
    town: str,
    county: str,
) -> list[str]:
    parts = [
        str(delivery_point.get("organisation_name", "")).strip(),
        str(delivery_point.get("department_name", "")).strip(),
        str(delivery_point.get("line_1", "")).strip(),
        str(delivery_point.get("line_2", "")).strip(),
        str(delivery_point.get("line_3", "")).strip(),
        town,
        county,
    ]
    seen: set[str] = set()
    unique_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        normalized = part.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_parts.append(part)
    return unique_parts


def _build_suggestion_id(postcode: str, index: int) -> str:
    return f"{postcode.replace(' ', '').upper()}:{index}"


def _parse_suggestion_id(suggestion_id: str) -> tuple[str, int] | None:
    match = re.match(r"^([A-Z0-9]{5,8}):(\d+)$", suggestion_id.strip().upper())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def _format_postcode_compact(compact_postcode: str) -> str:
    match = re.match(r"^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})$", compact_postcode)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return compact_postcode


def _extract_delivery_points(payload: dict) -> list[dict[str, Any]]:
    delivery_points = payload.get("delivery_points") if isinstance(payload, dict) else None
    if not isinstance(delivery_points, list):
        return []
    return [point for point in delivery_points if isinstance(point, dict)]


def _parse_suggestions(payload: dict) -> list[AddressSuggestion]:
    delivery_points = _extract_delivery_points(payload)
    postcode = str(payload.get("postcode", "")).strip()
    town = str(payload.get("town", "")).strip()
    county = str(payload.get("traditional_county") or payload.get("postal_county") or "").strip()
    suggestions: list[AddressSuggestion] = []
    for idx, point in enumerate(delivery_points):
        suggestion_id = _build_suggestion_id(postcode, idx)
        address_parts = _build_fetchify_line_parts(point, town=town, county=county)
        suggestion_address = ", ".join(address_parts)
        if suggestion_id and suggestion_address:
            suggestions.append(AddressSuggestion(id=suggestion_id, address=suggestion_address))
    return suggestions


def _status_from_provider_response(response: httpx.Response) -> str:
    if (
        response.status_code
        in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_402_PAYMENT_REQUIRED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_429_TOO_MANY_REQUESTS,
        }
        or response.status_code >= 500
    ):
        return STATUS_UNAVAILABLE
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return STATUS_NO_RESULTS
    if response.is_success:
        return STATUS_OK
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=PROVIDER_ERROR_DETAIL,
    )


@router.get("/autocomplete")
async def autocomplete_address(
    _: ActiveUserDep,
    postcode: str = Query(..., min_length=3),
) -> AddressAutocompleteResponse:
    token = _get_address_token()
    if not token:
        return AddressAutocompleteResponse(suggestions=[], status=STATUS_UNAVAILABLE)

    normalized = _normalize_postcode(postcode)
    encoded_postcode = _encode_query_value(normalized)
    encoded_token = _encode_query_value(token)
    url = (
        f"{FETCHIFY_RAPIDADDRESS_URL}"
        f"?key={encoded_token}&postcode={encoded_postcode}&response=data_formatted&sort=asc"
    )

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            return AddressAutocompleteResponse(suggestions=[], status=STATUS_UNAVAILABLE)

    provider_status = _status_from_provider_response(response)
    if provider_status != STATUS_OK:
        return AddressAutocompleteResponse(suggestions=[], status=provider_status)

    payload = response.json() if response.content else {}
    suggestions = _parse_suggestions(payload)

    if not suggestions:
        return AddressAutocompleteResponse(suggestions=[], status=STATUS_NO_RESULTS)

    return AddressAutocompleteResponse(suggestions=suggestions, status=STATUS_OK)


@router.get("/private-address/{address_id}")
async def resolve_private_address(
    _: ActiveUserDep,
    address_id: str,
) -> AddressDetailResponse:
    token = _get_address_token()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Address provider token not configured",
        )

    parsed_id = _parse_suggestion_id(address_id)
    if parsed_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid address id")

    compact_postcode, index = parsed_id
    normalized_postcode = _format_postcode_compact(compact_postcode)
    encoded_token = _encode_query_value(token)
    encoded_postcode = _encode_query_value(normalized_postcode)
    private_url = (
        f"{FETCHIFY_RAPIDADDRESS_URL}"
        f"?key={encoded_token}&postcode={encoded_postcode}&response=data_formatted&sort=asc"
    )

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(private_url)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=PROVIDER_ERROR_DETAIL,
            ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    if not response.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=PROVIDER_ERROR_DETAIL,
        )

    payload = response.json() if response.content else {}
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Address provider returned malformed response",
        )

    delivery_points = _extract_delivery_points(payload)
    if index < 0 or index >= len(delivery_points):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    town = str(payload.get("town", "")).strip()
    county = str(payload.get("traditional_county") or payload.get("postal_county") or "").strip()
    address_parts = _build_fetchify_line_parts(delivery_points[index], town=town, county=county)

    return AddressDetailResponse(
        formatted_address=address_parts,
        postcode=str(payload.get("postcode", "")).strip() or None,
    )
