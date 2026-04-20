from flask import Blueprint, request, jsonify
from app.models.ehs_document import Document
from app.extensions import db
import boto3
import io
import json
import uuid
from datetime import datetime
from flask import current_app
from app.models.ehs_doc_history import Ehs_Document_History
from app.models.ehs_log import Log
import re
import os
from app.utils.privilege_decorator import require_privilege

 
json_doc_bp = Blueprint("json_doc_bp", __name__)
 
@json_doc_bp.route("/update-json", methods=["POST"])
@require_privilege("USER")
def upload_json_api():
    try:
        data = request.get_json()
        doc_id = data.get("doc_id")
        document_name=data.get("document_name")
        event_date=data.get("event_date")
        letter_date=data.get("letter_date")
        sender_name=data.get("sender_name")
        consultant_name=data.get("consultant_name")
        department_name=data.get("department_name")
        attach_document_status=data.get("attach_document_status")
        json_data = data.get("json_data",{})
 
        if not doc_id:
            return jsonify({"message": "doc_id is required"}), 200
        if not json_data:
            return jsonify({"message": "json_data is required"}), 200

        
 
        # Fetch Document record
        doc = Document.query.get(doc_id)
        if not doc:
            return jsonify({"message": "Document not found", "status": 0}), 200
 
        s3 = boto3.client(
            "s3",
            aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
            aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
            region_name=current_app.config["AWS_REGION"]
        )
        #------------storing changed data ----------------
        doc.sender_name = consultant_name if consultant_name else doc.sender_name
        doc.event_date = event_date if event_date else doc.event_date
        doc.hospital_name = sender_name if sender_name else doc.hospital_name
        doc.letter_date = letter_date if letter_date else doc.letter_date
        doc.doc_attach_status=attach_document_status
 
        # ---- Convert JSON to BytesIO ----
        json_str = json.dumps(json_data, indent=4, ensure_ascii=False)
        json_bytes = io.BytesIO(json_str.encode("utf-8"))
 
        # ---- New filename ----
        today_date = datetime.now().strftime("%d-%m-%Y")
        base_name = os.path.splitext(document_name)[0]  # remove old extension
        safe_filename = re.sub(r"\s+", "_", base_name) + ".json"
        unique_name = f"{uuid.uuid4()}_{safe_filename}"
        s3_key = f"{current_app.config['AWS_JSON_FOLDER']}/{today_date}/{unique_name}"

 
        # ---- Upload to S3 ----
        try:
            s3.upload_fileobj(
                json_bytes,
                current_app.config["AWS_BUCKET"],
                s3_key,
                ExtraArgs={"ContentType": "application/octet-stream"}
            )
        except Exception as e:
            return jsonify({"status": 0, "message": str(e)}), 200
 
        # ---- Generate URL ----
        file_url = (
        f"https://{current_app.config['AWS_BUCKET']}.s3."
        f"{current_app.config['AWS_REGION']}.amazonaws.com/{s3_key}"
        )
 
 
        # ---- Update Database ----
        doc.extract_file_url = file_url
        db.session.commit()
        pf= Ehs_Document_History(
            doc_id=doc.doc_id,
            activity_id=2,
            s3_path=file_url,
            time_stamp=datetime.utcnow()
        )

        db.session.add(pf)
        db.session.commit()

 


       
 
        return jsonify({
            "status": 1,
            "message": "JSON uploaded successfully",
            "file_url": file_url
        }), 200
   
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200
 
 
@json_doc_bp.route("/replace_path", methods=["POST"])
@require_privilege("USER")
def replace_path():
    try:
        data = request.get_json()
        doc_id = data.get("doc_id")
        status_id=data.get("status")
        doc=Document.query.filter_by(doc_id=doc_id).first()
        history=Ehs_Document_History.query.filter_by(doc_id=doc_id,activity_id=status_id).order_by(Ehs_Document_History.time_stamp.desc()).first()
        print(history.s3_path)
        return jsonify({"status": 1, "message": "Path replaced successfully"}), 200
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200

 
 
@json_doc_bp.route("/doc_attachment_status", methods=["POST"])
@require_privilege("USER")
def doc_attachment_status():
    try:
        data=request.get_json()
        doc_id=data.get("doc_id")
        attach_status=data.get("status")

        doc=Document.query.filter_by(doc_id=doc_id).first()
        doc.doc_attach_status=attach_status
        db.session.commit()
        return jsonify({
            "status": 1,
            "message": "Document attachment status updated successfully"
        }), 200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200
        