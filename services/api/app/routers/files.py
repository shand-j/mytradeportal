"""File upload/download endpoints.

MinIO is private-network-only (no public domain): devices never talk to it
directly. Uploads POST multipart to this API, which stores the object; reads
stream through GET /files/download. Keys are tenant-prefixed
(``tenants/{tenant_id}/{uuid}/{filename}``) and downloads verify the prefix
against the caller's tenant.
"""

import uuid
from typing import Annotated
from uuid import UUID

import boto3
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import ActiveUserDep, CurrentUserDep

router = APIRouter(prefix="/files", tags=["Files"])
DbDep = Annotated[AsyncSession, Depends(get_db)]

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB per photo is generous


def s3_client() -> boto3.client:
    """Return a boto3 S3 client for MinIO on the private network.

    MinIO has no public domain — this client is only ever used server-side, so
    the endpoint is the private host and http (no TLS inside the network).
    """
    scheme = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{scheme}://{settings.minio_endpoint}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name="us-east-1",
        config=BotoConfig(signature_version="s3v4"),
    )


def store_upload(tenant_id: UUID, file: UploadFile, content: bytes) -> dict[str, str]:
    """Store an uploaded object for the tenant and return key + proxy URL."""
    safe_name = (file.filename or "upload").split("/")[-1][:120]
    key = f"tenants/{tenant_id}/{uuid.uuid4()}/{safe_name}"
    s3_client().put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )
    return {"key": key, "url": f"/files/download?key={key}"}


def stream_download(tenant_id: UUID, key: str) -> StreamingResponse:
    """Stream an object back to the caller, tenant-prefix checked."""
    if not key.startswith(f"tenants/{tenant_id}/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    try:
        obj = s3_client().get_object(Bucket=settings.minio_bucket, Key=key)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        ) from None
    return StreamingResponse(
        obj["Body"].iter_chunks(64 * 1024),
        media_type=obj.get("ContentType") or "application/octet-stream",
    )


@router.post("/upload")
async def upload_file(
    file: UploadFile,
    current_user: ActiveUserDep,
) -> dict[str, str]:
    """Upload a file to tenant-scoped storage (staff)."""
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large"
        )
    try:
        return store_upload(current_user.tenant_id, file, content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not store file: {exc}",
        ) from exc


@router.get("/download")
async def download_file(key: str, current_user: CurrentUserDep) -> Response:
    """Stream a stored file back (staff, tenant-prefix enforced)."""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return stream_download(current_user.tenant_id, key)
