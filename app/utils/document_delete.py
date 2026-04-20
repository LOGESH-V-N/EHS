import boto3
from flask import current_app

def delete_from_s3(file_path):
    """
    file_path = full S3 URL  
    we must extract the object key from the URL
    """
    bucket = current_app.config["AWS_BUCKET"]
    region = current_app.config["AWS_REGION"]

    # Example URL:
    # https://bucket.s3.region.amazonaws.com/uuid_filename.pdf
    prefix = f"https://{bucket}.s3.{region}.amazonaws.com/"
    key = file_path.replace(prefix, "")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )

    s3.delete_object(Bucket=bucket, Key=key)
    return True
