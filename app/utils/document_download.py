import base64
import boto3
import io
import json
from flask import current_app

import base64
import boto3
import io
import mimetypes
from flask import current_app
import os
import datetime


def download_from_s3_as_base64(file_url):


    bucket = current_app.config["AWS_BUCKET"]
    key = file_url.split(".amazonaws.com/")[1]  # extract object key

    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )

    # Download file into memory
    file_stream = io.BytesIO()
    s3.download_fileobj(bucket, key, file_stream)
    file_stream.seek(0)
    file_bytes = file_stream.read()

    # Detect MIME type
    mime, _ = mimetypes.guess_type(key)
    mime = mime or "application/octet-stream"

    # Encode Base64
    b64 = base64.b64encode(file_bytes).decode("utf-8")

    # File name
    file_name = os.path.basename(key)

    # Last modified timestamp from S3
    head = s3.head_object(Bucket=bucket, Key=key)
    last_modified = int(head["LastModified"].timestamp())
    last_modified_iso = head["LastModified"].astimezone().isoformat()

    # FINAL OUTPUT FORMAT LIKE FRONTEND NEEDS
    return {
        "name": file_name,
        "size": head["ContentLength"],
        "type": mime,
        "lastModified": last_modified,
        "lastModifiedDate": last_modified_iso,
        "file": f"data:{mime};base64,{b64}"
    }




def read_json_from_s3(file_url):
    """
    Reads a JSON file from S3 using the same structure as download_from_s3_as_base64().
    """

    # Extract bucket name from config
    bucket = current_app.config["AWS_BUCKET"]

    # Extract key from URL
    # Example URL:
    # https://ems-test-uploads.s3.eu-west-2.amazonaws.com/folder/20251208_120203.json
    #
    # file_url.split(".amazonaws.com/")[1] → "folder/20251208_120203.json"
    try:
        key = file_url.split(".amazonaws.com/")[1]
    except Exception:
        raise Exception("Invalid S3 URL format. Cannot extract key.")

    # Create S3 client
    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )

    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)
    except Exception as e:
        raise Exception(f"Failed to fetch or parse JSON from S3: {str(e)}")


def download_from_s3(file_url):
    bucket = current_app.config["AWS_BUCKET"]

    # Extract object key from S3 URL
    key = file_url.split(".amazonaws.com/")[1]

    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )

    # Download into memory
    file_stream = io.BytesIO()
    s3.download_fileobj(bucket, key, file_stream)
    file_stream.seek(0)
    file_bytes = file_stream.read()

    # MIME type
    mime, _ = mimetypes.guess_type(key)
    mime = mime or "application/pdf"

    # Base64 encode
    b64 = base64.b64encode(file_bytes).decode("utf-8")

    # Metadata
    file_name = os.path.basename(key)
    head = s3.head_object(Bucket=bucket, Key=key)

    return {
        "name": file_name,
        "size": head["ContentLength"],
        "type": mime,
        "lastModified": int(head["LastModified"].timestamp()),
        "lastModifiedDate": head["LastModified"].astimezone().isoformat(),
        "file": f"data:{mime};base64,{b64}"
    }
