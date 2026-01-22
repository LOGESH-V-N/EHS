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
 
json_doc_bp = Blueprint("json_doc_bp", __name__)
 
@json_doc_bp.route("/update-json", methods=["POST"])
def upload_json_api():
    try:
        data = request.get_json()
 
        doc_id = data.get("id")
        json_data = data.get("json")
 
        if not doc_id or json_data is None:
            return jsonify({"message": "id and json are required"}), 200
 
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
 
        # ---- Delete old JSON file ----

 
        # ---- Convert JSON to BytesIO ----
        json_str = json.dumps(json_data, indent=4, ensure_ascii=False)
        json_bytes = io.BytesIO(json_str.encode("utf-8"))
 
        # ---- New filename ----
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{timestamp}_{uuid.uuid4()}.json"
 
        # ---- Upload to S3 ----
        try:
            s3.upload_fileobj(
                json_bytes,
                current_app.config["AWS_BUCKET"],
                file_name,
                ExtraArgs={"ContentType": "application/json"}
            )
        except Exception as e:
            return jsonify({"status": 0, "message": str(e)}), 200
 
        # ---- Generate URL ----
        file_url = (
            f"https://{current_app.config['AWS_BUCKET']}.s3."
            f"{current_app.config['AWS_REGION']}.amazonaws.com/{file_name}"
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
