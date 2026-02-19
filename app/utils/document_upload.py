import boto3
import uuid
from flask import current_app
from datetime import datetime
import re

def upload_to_s3(file_obj, filename):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )

    # Generate unique name
    safe_filename = re.sub(r"\s+", "_", filename)
    print(safe_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_name = f"{timestamp}_{uuid.uuid4()}_{safe_filename}"
 

    s3.upload_fileobj(
        file_obj,
        current_app.config["AWS_BUCKET"],
        unique_name,
        ExtraArgs={"ContentType": "application/pdf"}
    )

    file_url = f"https://{current_app.config['AWS_BUCKET']}.s3.{current_app.config['AWS_REGION']}.amazonaws.com/{unique_name}"
    return file_url

def upload_file_to_s3(file_obj, filename, content_type="application/octet-stream"):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_name = f"{timestamp}_{uuid.uuid4()}_{filename}"

    s3.upload_fileobj(
        file_obj,
        current_app.config["AWS_BUCKET"],
        unique_name,
        ExtraArgs={"ContentType": content_type}
    )

    file_url = (
        f"https://{current_app.config['AWS_BUCKET']}.s3."
        f"{current_app.config['AWS_REGION']}.amazonaws.com/{unique_name}"
    )
    return file_url
