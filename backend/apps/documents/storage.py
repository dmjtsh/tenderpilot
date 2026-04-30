import io
import logging
from typing import Iterator

from django.conf import settings
from minio import Minio
from minio.deleteobjects import DeleteObject

logger = logging.getLogger(__name__)

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
    return _client


def ensure_bucket() -> None:
    client = _get_client()
    bucket = settings.MINIO_BUCKET_DOCUMENTS
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)


def upload_file(s3_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    client = _get_client()
    ensure_bucket()
    client.put_object(
        settings.MINIO_BUCKET_DOCUMENTS,
        s3_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    logger.info("Uploaded %s (%d bytes)", s3_key, len(data))


def download_file(s3_key: str) -> bytes:
    client = _get_client()
    response = client.get_object(settings.MINIO_BUCKET_DOCUMENTS, s3_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_prefix(prefix: str) -> int:
    client = _get_client()
    bucket = settings.MINIO_BUCKET_DOCUMENTS
    objects = client.list_objects(bucket, prefix=prefix, recursive=True)
    delete_list = [DeleteObject(obj.object_name) for obj in objects]
    if not delete_list:
        return 0
    errors = list(client.remove_objects(bucket, delete_list))
    if errors:
        logger.warning("MinIO delete errors: %s", errors)
    count = len(delete_list)
    logger.info("Deleted %d objects with prefix %s", count, prefix)
    return count
