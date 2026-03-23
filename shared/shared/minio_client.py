"""MinIO (S3-compatible) client for storing and retrieving crawled HTML pages."""

from __future__ import annotations

import hashlib
import io
import logging
from urllib.parse import urlparse

from miniopy_async import Minio

logger = logging.getLogger(__name__)


def create_minio(
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool = False,
) -> Minio:
    """Create a MinIO async client."""
    return Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


async def ensure_bucket(client: Minio, bucket: str) -> None:
    """Create the bucket if it doesn't exist."""
    if not await client.bucket_exists(bucket):
        await client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)


def html_object_path(url: str) -> str:
    """Generate a deterministic MinIO object path from a URL.

    Format: {domain}/{sha256_hash}.html
    This is used by both the crawler (write) and parser (read) to ensure consistency.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.replace(":", "_")
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{domain}/{url_hash}.html"


async def upload_html(client: Minio, bucket: str, url: str, html: bytes) -> str:
    """Upload HTML content to MinIO and return the object path."""
    path = html_object_path(url)
    data = io.BytesIO(html)
    await client.put_object(
        bucket,
        path,
        data,
        length=len(html),
        content_type="text/html",
    )
    logger.debug("Uploaded %d bytes to %s/%s", len(html), bucket, path)
    return path


async def download_html(client: Minio, bucket: str, path: str) -> bytes:
    """Download HTML content from MinIO."""
    response = await client.get_object(bucket, path)
    try:
        data = await response.read()
    finally:
        response.close()
        await response.release()
    return data
