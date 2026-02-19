from app.utils.document_download import download_from_s3_as_base64
from app.models.ehs_document import Document
from app.utils.logger_util import get_logger
from app.extensions import db
from flask import jsonify,request,Blueprint

duplicate_bp = Blueprint("duplicate_bp", __name__)
logger = get_logger("duplicate_bp", log_dir="logs")






@duplicate_bp.route("/view", methods=["POST"])
def view_duplicate():
    try:
        data = request.get_json()
        doc_id = data.get("doc_id")
        doc = Document.query.filter_by(doc_id=doc_id).first()
        if not doc:
            return jsonify({"message": "Document not found","status":0}), 200
        parent_doc_id = doc.parent_doc_id
        if not parent_doc_id:
            return jsonify({"message": "No parent document found","status":0}), 200
        parent_doc = Document.query.filter_by(doc_id=parent_doc_id).first()
        duplicate_file_path=doc.doc_file_path
        parent_file_path=parent_doc.doc_file_path
        duplicate_file_base64 = download_from_s3_as_base64(duplicate_file_path)
        parent_file_base64 = download_from_s3_as_base64(parent_file_path)
        return jsonify({"status": 1,"message":"Duplicate documents found","data":{"duplicate_file": {"file_base64": duplicate_file_base64, "file_name": doc.doc_filename,"id":doc.doc_id}, "parent_file": {"file_base64": parent_file_base64, "file_name": parent_doc.doc_filename,"id":parent_doc.doc_id}}}), 200
    except Exception as e:
        logger.exception(
            f"Document duplicate view failed | doc_id={doc_id} | error={str(e)}"
        )
        return jsonify({"status": 0,"message":"Document duplicate view failed","error":str(e)}), 200

@duplicate_bp.route("/delete", methods=["POST"])
def delete_duplicate():
    try:
        data = request.get_json()
        doc_id = data.get("doc_id")
        delete_status=data.get("delete_status")
        if delete_status==0:
            doc = Document.query.filter_by(doc_id=doc_id).first()
            if not doc:
                return jsonify({"message": "Document not found","status":0}), 200
            doc.delete_status=0
            doc.parent_doc_id=None
            db.session.commit()
            return jsonify({"message": "Document changed to non duplicate","status":1}), 200
        elif delete_status==1:
            doc = Document.query.filter_by(doc_id=doc_id).first()
            doc.delete_status=1
            db.session.commit()
            return jsonify({"message": "Document deleted","status":1}), 200

    except Exception as e:
        logger.exception(
            f"Document duplicate delete failed | doc_id={doc_id} | error={str(e)}"
        )
        return jsonify({"status": 0,"message":"Document duplicate delete failed","error":str(e)}), 200





