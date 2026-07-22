"""File upload endpoints."""

import uuid

import boto3
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.dependencies import ActiveUserDep
from app.schemas import PresignedUploadRequest, PresignedUploadResponse

router = APIRouter(prefix="/files", tags=["Files"])


def _s3_client() -> boto3.client:
    """Return a boto3 S3 client configured for MinIO/S3-compatible storage.

    Presigned URLs are handed to the browser, so the scheme must match how
    clients reach the endpoint — HTTPS in production (``MINIO_USE_SSL=true``)
    to avoid mixed-content blocking.
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


@router.post("/presigned-upload")
async def presigned_upload(
    data: PresignedUploadRequest,
    current_user: ActiveUserDep,
) -> PresignedUploadResponse:
    """Generate a presigned POST URL for uploading a file to tenant-scoped storage."""
    key = f"tenants/{current_user.tenant_id}/{uuid.uuid4()}/{data.filename}"

    try:
        client = _s3_client()
        presigned = client.generate_presigned_post(
            Bucket=settings.minio_bucket,
            Key=key,
            Fields={"Content-Type": data.content_type or "application/octet-stream"},
            Conditions=[["starts-with", "$Content-Type", ""]],
            ExpiresIn=300,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate presigned upload URL: {exc}",
        ) from exc

    return PresignedUploadResponse(
        url=presigned["url"],
        fields=presigned["fields"],
        key=key,
    )
