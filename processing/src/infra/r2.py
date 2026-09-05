import boto3


def client(account_id: str, access_key_id: str, secret_access_key: str):
    """A boto3 S3 client pointed at a Cloudflare R2 account. R2 is
    S3-API-compatible, so the standard S3 client works against it directly
    given the account-scoped endpoint and `region_name="auto"`.

    Credential-parameterized rather than reading `config` directly, because
    two independent credential sets use it: the models set (R2ModelStore,
    read-only against goodgorithm-models) and the corpus set (CorpusStore,
    read/write against goodgorithm-corpus)."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )
