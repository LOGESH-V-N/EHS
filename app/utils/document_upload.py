import boto3
import uuid
from flask import current_app
from datetime import datetime
import re
import os
from botocore.exceptions import ClientError
 

def upload_to_s3(file_obj, filename,upload_status=None):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )


    # Clean filename
    safe_filename = re.sub(r"\s+", "_", filename)

    # Create date folder (YYYY-MM-DD)
    today_date = datetime.now().strftime("%d-%m-%Y")
    file_date= datetime.now().strftime("%d%m%y%H%M%S")

    # Unique filename
    unique_name = f"{file_date}--{safe_filename}"
    if upload_status==3:
        s3_key = f"{current_app.config['AWS_LISTENER_FOLDER']}/{today_date}/{unique_name}"
    else:
        s3_key = f"{current_app.config['AWS_APP_FOLDER']}/{today_date}/{unique_name}"

    # Final S3 key (THIS creates folder structure automatically)
    


    # Upload file
    s3.upload_fileobj(
        file_obj,
        current_app.config["AWS_BUCKET"],
        s3_key,
        ExtraArgs={"ContentType": "application/pdf"}
    )

    # Generate file URL
    file_url = f"https://{current_app.config['AWS_BUCKET']}.s3.{current_app.config['AWS_REGION']}.amazonaws.com/{s3_key}"

    return file_url

def upload_file_to_s3(file_obj, filename, content_type="application/octet-stream"):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"]
    )
    today_date = datetime.now().strftime("%d-%m-%Y")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_name = f"{timestamp}_{uuid.uuid4()}_{filename}"
    json_folder_name=current_app.config['AWS_JSON_FOLDER']
    s3_key = f"{json_folder_name}/{today_date}/{unique_name}"

    s3.upload_fileobj(
        file_obj,
        current_app.config["AWS_BUCKET"],
        s3_key,
        ExtraArgs={"ContentType": content_type}
    )

    file_url = (
        f"https://{current_app.config['AWS_BUCKET']}.s3."
        f"{current_app.config['AWS_REGION']}.amazonaws.com/{s3_key}"
    )
    return file_url


def mail_upload_to_s3(file_obj, filename,timestamp):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"],  # ✅ FIXED
    )


    bucket = current_app.config["AWS_BUCKET"]


    # ----------------------------
    # 1️⃣ Prepare Date Folder
    # ----------------------------
    today_date = datetime.now().strftime("%d-%m-%Y")

    # Your base path
    base_path = current_app.config["AWS_BUCKET_MAIL"]
    folder_path = f"{base_path}/{today_date}"
    print("folder_path",folder_path)

    # ----------------------------
    # 2️⃣ Safe filename
    # ----------------------------
    safe_filename = re.sub(r"\s+", "_", filename)

    name, ext = os.path.splitext(safe_filename)

    # ----------------------------
    # 3️⃣ Check existing file names
    # ----------------------------
    counter = 0
    dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    file_date = dt.strftime("%d%m%y%H%M%S")
    unique_name = f"{file_date}--{name}{ext}"

    while True:
        s3_key = f"{folder_path}/{unique_name}"

        try:
            s3.head_object(Bucket=bucket, Key=s3_key)
            # If exists → increment
            counter += 1
            unique_name = f"{name}-{counter}{ext}"
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                # File does NOT exist → safe to use
                break
            else:
                raise

    # ----------------------------
    # 4️⃣ Upload File
    # ----------------------------
    file_obj.seek(0)

    s3.upload_fileobj(
        file_obj,
        bucket,
        s3_key,
        ExtraArgs={"ContentType": "application/pdf"}
    )

    # ----------------------------
    # 5️⃣ Return File URL
    # ----------------------------
    file_url = f"https://{bucket}.s3.{current_app.config['AWS_REGION']}.amazonaws.com/{s3_key}"

    return file_url