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
from app.utils.document_download import read_json_from_s3
from datetime import datetime


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
        formatted_date = date_obj.strftime("%Y-%m-%d")
        

        # ----------------------------
        # Base Query (MAIL DOCUMENTS FIRST)
        # ----------------------------
        query = Document.query.filter(
            Document.delete_status == 0,
            Document.upload_type == 2,
            Document.email_time_stamp.startswith(formatted_date)
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
            if doc.doc_type_code == "N/A":
                doc_code=""
            else:
                doc_code=doc.doc_type_code
            if doc.org_filename == "N/A":
                org_name=""
            else:
                org_name=doc.org_filename

            json_response = None
            if doc.extract_file_url:
                try:
                    json_response = read_json_from_s3(doc.extract_file_url)
                except Exception as ex:
                    json_response = {"error": str(ex)}

            # ----------------------------
            # Extract fields from structured output
            # ----------------------------
            event_date = ""
            letter_date = ""
            short_summary = ""
            hospital_name = ""  # ✅ Fixed: initialized before the block
            department = ""     # ✅ Fixed: initialized before the block

            if json_response and "error" not in json_response:
                try:
                    structured_output = json_response.get("structured_output", [])

                    if structured_output and isinstance(structured_output, list):
                        first_entry = structured_output[0]

                        hospital_name = (
                            first_entry
                            .get("Overview", {})
                            .get("hospital_details", {})
                            .get("hospital_name", "")
                        )

                        department = (
                            first_entry
                            .get("Overview", {})
                            .get("sender_information", {})
                            .get("department", "")
                        )

                        event_date = (
                            first_entry
                            .get("Overview", {})
                            .get("event_details", {})
                            .get("event_date", "")
                        )

                        letter_date = (
                            first_entry
                            .get("Overview", {})
                            .get("letter_issued_date", {})
                            .get("date", "")
                        )

                        short_summary = (
                            first_entry
                            .get("clinical_info", {})
                            .get("summary", {})
                            .get("short_summary", "")
                        )

                except Exception:
                    pass
            mail_formatted_date=datetime.strptime(doc.email_time_stamp, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M")
            results.append({
                "id": doc.doc_id,
                "document_name": doc.doc_filename,
                "org_doc_name":org_name,
                "email_sender": doc.email_sender if doc.email_sender else "",
                "email_time_stamp": mail_formatted_date,
                "doc_status": doc.doc_status,
                "doc_type": doc_code,
                "created_at": doc.created_at.strftime("%d %B %Y %H:%M") if doc.created_at else "",
                "hospital_name": hospital_name,
                "department": department,
                "event_date": event_date,
                "letter_date": letter_date,
                "short_summary": short_summary
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
