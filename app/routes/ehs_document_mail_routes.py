from flask import Blueprint, jsonify, Response, request
from app import db
from app.models.ehs_document import Document
from app.models.document import DocTypeMaster
from app.models.ehs_doc_task import EhsDocumentTask
from app.models.ehs_patient import DocumentListSchema as PatientModel
from app.models.ehs_count_master import Count
from app.models.user import User
import requests
from datetime import datetime
from app.models.ehs_log import Log
from app.utils.date_formatter import format_datetime
from app.utils.privilege_decorator import require_privilege

mail_list_bp = Blueprint("mail_list_bp", __name__)


        


@mail_list_bp.route("/list", methods=["POST"])
@require_privilege("USER")
def get_mail_document_list():
    try:
        data = request.get_json()

        # ----------------------------
        # Pagination
        # ----------------------------
        page = int(data.get("page", 1))
        limit = int(data.get("pageSize", 10))
        offset = (page - 1) * limit

        # ----------------------------
        # Filters
        # ----------------------------
        filterData = data.get("filterData", {})
        mail_date = filterData.get("date")
        letter_type = filterData.get("letter_type")
        document_status = filterData.get("document_status")

        if not mail_date:
            return jsonify({
                "status": 0,
                "message": "date is required"
            }), 200

        # Convert 12/12/2026 -> 12/12/26
        date_obj = datetime.strptime(mail_date, "%d/%m/%Y")
        formatted_date = date_obj.strftime("%m/%d/%y")

        # ----------------------------
        # Base Query (MAIL DOCUMENTS FIRST)
        # ----------------------------
        query = Document.query.filter(
            Document.delete_status == 0,
            Document.upload_type == 2,
            Document.email_time_stamp == formatted_date
        )

        # ----------------------------
        # Letter Type Filter (Optional)
        # ----------------------------
        if letter_type:
            type_row = DocTypeMaster.query.filter_by(
                doc_type_id=int(letter_type)
            ).first()

            if type_row:
                query = query.filter(
                    Document.doc_type_code == type_row.doc_type_code
                )

        # ----------------------------
        # Document Status Filter (Optional)
        # ----------------------------
        if document_status:
            query = query.filter(
                Document.doc_status == int(document_status)
            )

        # ----------------------------
        # Count
        # ----------------------------
        total = query.count()

        documents = (
            query.order_by(Document.doc_id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        if not documents:
            return jsonify({
                "status": 0,
                "message": "No mail documents found",
                "data": [],
                "total": 0
            }), 200

        results = []

        for doc in documents:
            results.append({
                "id": doc.doc_id,
                "document_name": doc.doc_filename,
                "email_sender": doc.email_sender,
                "email_time_stamp": doc.email_time_stamp,
                "doc_status": doc.doc_status,
                "doc_type_code": doc.doc_type_code,
                "created_at": doc.created_at.strftime("%d %B %Y %H:%M") if doc.created_at else ""
            })

        return jsonify({
            "status": 1,
            "data": results,
            "total": total
        }), 200

    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 500

@mail_list_bp.route("/zip_download", methods=["POST"])
@require_privilege("USER")
def mail_zip_download():
    try:
        body = request.get_json()
        date = body.get("date")
     

        if not date:
            return jsonify({"status": 0, "message": "date is required"}), 200
        date_obj = datetime.strptime(date, "%d/%m/%Y")
        formatted_date = date_obj.strftime("%Y-%m-%d")
        

        external_url = "https://docemail.patientsurvey.ai/create-zip-by-date"

        # Call external API
        response = requests.post(
            external_url,
            json={"date": formatted_date},
            stream=True
        )
        

        # If error from external API
        if response.status_code != 200:
            return jsonify({
                "status": 0,
                "message": "Failed to fetch ZIP file"
            }), 500

        # Return blob directly to frontend
        return Response(
            response.content,
            content_type=response.headers.get("Content-Type", "application/zip"),
            headers={
                "Content-Disposition": "attachment; filename=mail_documents.zip"
            }
        )

    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 500
