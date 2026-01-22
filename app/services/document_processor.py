import boto3
from flask import current_app
import os
from datetime import datetime
from app.models.ehs_document import Document
from app.extensions import db
from app.models.ehs_log import Log
from botocore.exceptions import ClientError
from urllib.parse import urlparse
 
def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )
 
def extract_s3_key(s3_url: str) -> str:
    return urlparse(s3_url).path.lstrip("/")
 
 
def download_from_s3(doc: Document, local_dir="temp_s3_docs"):
    os.makedirs(local_dir, exist_ok=True)
 
    s3 = get_s3_client()
    bucket = current_app.config["AWS_BUCKET"]
 
    # STEP 1 — assume DB stored key correctly
    key = extract_s3_key(doc.doc_file_path)
    print(key)
    print("reachec")
 
    # STEP 2 — try direct match
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            raise FileNotFoundError(
                f"S3 object not found | bucket={bucket} | key={key}"
            )
        else:
            raise  # re-raise unexpected AWS errors
    print("no problem")
 
    # STEP 3 — download
    local_path = os.path.join(local_dir, doc.doc_filename)
    s3.download_file(bucket, key, local_path)
 
    return local_path
 
 
def add_log(doc_id, status):
    log = Log(doc_id=doc_id, doc_status=str(status),datatime=datetime.utcnow())
    db.session.add(log)
    db.session.commit()
 
 
 
def update_doc_status(doc, status):
    doc.doc_status = status
    doc.updated_at = datetime.utcnow()
    add_log(doc.doc_id, status)
 
def update_document_type(doc, document_type: str):
    """
    Update detected document type after processing
    """
    doc.doc_type_code = document_type