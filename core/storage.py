"""Original uploaded files live in S3; the DB keeps only the object key (documents.s3_key)."""
import re
import uuid

from core import config

_client = None


def enabled() -> bool:
    return bool(config.AWS_S3_BUCKET)


def _s3():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        # Regional endpoint + virtual addressing so presigned URLs don't bounce through the global endpoint.
        _client = boto3.client(
            "s3", region_name=config.AWS_REGION,
            endpoint_url=f"https://s3.{config.AWS_REGION}.amazonaws.com" if config.AWS_REGION else None,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"},
                          retries={"max_attempts": 3}))
    return _client


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "file"


def put(data: bytes, filename: str, content_type: str | None = None) -> str:
    """Uploads the file and returns its object key."""
    key = f"{config.S3_PREFIX}/{uuid.uuid4().hex}/{_safe(filename)}"
    _s3().put_object(Bucket=config.AWS_S3_BUCKET, Key=key, Body=data,
                     ContentType=content_type or "application/octet-stream",
                     ServerSideEncryption="AES256")
    return key


def delete(key: str) -> None:
    _s3().delete_object(Bucket=config.AWS_S3_BUCKET, Key=key)


def presigned_url(key: str, filename: str) -> str:
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": config.AWS_S3_BUCKET, "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{_safe(filename)}"'},
        ExpiresIn=config.S3_URL_EXPIRES)
