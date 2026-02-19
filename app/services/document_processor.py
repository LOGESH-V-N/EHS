import boto3
from flask import current_app
import os
from datetime import datetime
from app.models.ehs_document import Document
from app.extensions import db
from app.models.ehs_log import Log
from urllib.parse import urlparse
 

def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )


def download_from_s3(doc: Document, local_dir="temp_s3_docs"):
    os.makedirs(local_dir, exist_ok=True)

    s3 = get_s3_client()
    bucket = current_app.config["AWS_BUCKET"]

    # STEP 1 — assume DB stored key correctly
    key = urlparse(doc.doc_file_path).path.lstrip("/")

    # STEP 2 — try direct match
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except:
        # fallback: search for any key containing filename (handles UUID prefix)
        resp = s3.list_objects_v2(Bucket=bucket)
        found = False
        if "Contents" in resp:
            for obj in resp["Contents"]:
                if doc.doc_filename in obj["Key"]:
                    key = obj["Key"]
                    found = True
                    break

        if not found:
            raise FileNotFoundError(f"S3 object not found for {doc.doc_filename}")

    # STEP 3 — download
    local_path = os.path.join(local_dir, doc.doc_filename)
    s3.download_file(bucket, key, local_path)

    return local_path


def add_log(doc_id, status):
    log = Log(doc_id=doc_id, doc_status=str(status),datatime=datetime.utcnow())
    db.session.add(log)
    db.session.commit()



def update_doc_status(doc, status,error=None):
    doc.doc_status = status
    doc.updated_at = datetime.utcnow()
    if status == 7:
        doc.error_message = error
    add_log(doc.doc_id, status)
    db.session.commit()

def update_document_type(doc, document_type: str):
    """
    Update detected document type after processing
    """
    doc.doc_type_code = document_type
    
