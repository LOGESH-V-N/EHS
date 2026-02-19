from flask import Blueprint, jsonify,request
from app import db
from app.models.ehs_document import Document
from app.utils.document_download import download_from_s3_as_base64, read_json_from_s3
from app.models.ehs_patient import DocumentListSchema as PatientModel
from app.models.document import DocTypeMaster 
from app.models.ehs_count_master import Count
from app.schemas.ehs_document_list_schema import DocumentListSchema as DocumentSchema
from app.utils.date_formatter import format_datetime
from flask import request, jsonify
from sqlalchemy import func
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.ehs_count_master import Count
from app.utils.document_upload import upload_to_s3
from app.utils.document_delete import delete_from_s3
from app.utils.decode_file import decode_filename
from datetime import datetime
from app.models.ehs_document import Document
from app.models.user import User
from app.models.ehs_log import Log
from app.utils.date_formatter import format_datetime
from app.models.ehs_count_master import Count
import imaplib
import email
from email.header import decode_header
import os
from datetime import datetime
from io import BytesIO
from PIL import Image
import io
from app.models.ehs_doc_assignee import EhsDocumentAssignee
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.ehs_document import Document
from app.models.ehs_doc_priority import Ehs_Doc_Priority
import hashlib
from app.models.ehs_doc_task import EhsDocumentTask
from app.utils.privilege_decorator import require_privilege
import subprocess
import tempfile




document_list_bp = Blueprint("document_list_bp", __name__)





@document_list_bp.route("/view", methods=["POST"])
def get_document_with_base64_and_json():
    try:
        body = request.get_json()
        doc_id = body.get("id")

        if not doc_id:
            return jsonify({"status": 0, "message": "doc_id is required"}), 200

        # -------------------------------------
        # Fetch document
        # -------------------------------------
        doc = db.session.query(Document).filter(Document.doc_id == doc_id).first()

        if not doc:
            return jsonify({"status": 0, "message": "Document not found"}), 200

        # -------------------------------------
        # Fetch patient
        # -------------------------------------
        patient = db.session.query(
            PatientModel.patient_name,
            PatientModel.phone_no
        ).first()

        patient_info = (
            f"{patient.patient_name} {patient.phone_no}"
            if doc.doc_status in [3, 4, 5, 6] and patient
            else ""
        )

        # -------------------------------------
        # Letter Type
        # -------------------------------------
        doc_type = (
            db.session.query(DocTypeMaster.doc_type_name)
            .filter(DocTypeMaster.doc_type_code == doc.doc_type_code)
            .first()
        )
        letter_type = doc_type.doc_type_name if doc_type else ""

        # -------------------------------------
        # Status
        # -------------------------------------
        status_row = (
            db.session.query(Count.name, Count.color_code)
            .filter(Count.id == doc.doc_status)
            .first()
        )

        document_status = status_row.name if status_row else ""
        color_code = status_row.color_code if status_row else "#000000"

        # -------------------------------------
        # BASE64 FILE
        # -------------------------------------
        file_base64 = download_from_s3_as_base64(doc.doc_file_path)

        # -------------------------------------
        # JSON FILE
        # -------------------------------------
        json_response = None
        if doc.extract_file_url:
            try:
                json_response = read_json_from_s3(doc.extract_file_url)
            except Exception as ex:
                json_response = {"error": str(ex)}
        doc_attach_status=doc.doc_attach_status

        # -------------------------------------
        # Processed Date
        # -------------------------------------
        processed_date = ""
        if doc.doc_status in [3, 4, 5, 6]:
            processed_log = (
                db.session.query(Log.datatime)
                .filter(
                    Log.doc_id == doc.doc_id,
                    Log.doc_status.in_([3, 4, 5, 6])
                )
                .order_by(Log.datatime.desc())
                .first()
            )
            if processed_log:
                processed_date = format_datetime(processed_log.datatime)

        # =====================================================
        # ✅ ASSIGNEE + PRIORITY (NEW ADDITION)
        # =====================================================
        assignee_name = ""
        assigned_date = ""
        priority_name = ""
        priority_color_code = ""

        assignee_row = (
            db.session.query(
                EhsDocumentAssignee.assignee_id,
                EhsDocumentAssignee.priority_id,
                EhsDocumentAssignee.created_at
            )
            .filter(EhsDocumentAssignee.doc_id == doc.doc_id)
            .first()
        )

        if assignee_row:
            assigned_date = format_datetime(assignee_row.created_at)

            # --- Assignee Name ---
            user = (
                db.session.query(
                    User.first_name,
                    User.middle_name,
                    User.last_name
                )
                .filter(User.uid == assignee_row.assignee_id)
                .first()
            )

            if user:
                assignee_name = " ".join(
                    filter(None, [
                        user.first_name,
                        user.middle_name,
                        user.last_name
                    ])
                )

            # --- Priority Name ---
            priority = (
                db.session.query(Ehs_Doc_Priority)
                .filter(Ehs_Doc_Priority.id == assignee_row.priority_id)
                .first()
            )
            priority_name = priority.name if priority else ""
            priority_color_code = priority.color_code if priority else ""

        # -------------------------------------
        # Final Output
        # -------------------------------------
        result = {
            "id": doc.doc_id,
            "document_name": doc.doc_filename,
            "patient_info": patient_info,
            "letter_type": letter_type,
            "letter_type_code": doc.doc_type_code,
            "document_status": document_status,
            "document_status_id": doc.doc_status,
            "document_status_color": color_code,
            "created_at": format_datetime(doc.created_at),
            "updated_at": format_datetime(doc.updated_at),
            "processed_date": processed_date,

            # ✅ NEW FIELDS
            "assigned_to": assignee_name,
            "assigned_date": assigned_date,
            "priority": priority_name,
            "priority_color_code": priority_color_code,

            "file_format": file_base64,
            "file_content": json_response,
            "doc_attach_status": doc_attach_status
        }

        return jsonify({"status": 1, "data": result}), 200

    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200



@document_list_bp.route("/summary", methods=["POST"])
def get_summary_count():
    try:
        data = request.get_json()
        user_id = data.get("id")
 
        summary = []
 
        # ------------------------------------------------
        # Assigned to Me (Document-level assignment)
        # ------------------------------------------------
        assigned_to_me = (
            db.session.query(Document.doc_id)
            .filter(
                Document.assign_to == user_id,
                Document.delete_status == 0
            )
            .count()
        )
 
        # ------------------------------------------------
        # Task Assigned to Me (TASK-level assignment)
        # DISTINCT doc_id is IMPORTANT
        # ------------------------------------------------
        task_assigned_to_me = (
            db.session.query(Document.doc_id)
            .join(
                EhsDocumentTask,
                EhsDocumentTask.doc_id == Document.doc_id
            )
            .filter(
                EhsDocumentTask.assign_to == user_id,
                Document.delete_status == 0
            )
            .distinct()
            .count()
        )
 
        # ------------------------------------------------
        # All Count (EXISTING LOGIC – UNCHANGED)
        # ------------------------------------------------
        total_docs = (
            db.session.query(Document.doc_id)
            .filter(Document.delete_status == 0)
            .count()
        )
 
        all_count = total_docs + assigned_to_me
 
        summary.append({
            "count": all_count,
            "label": "All",
            "id": "",
            "filter_by": "status"
        })
 
        # ------------------------------------------------
        # Status-based counts
        # ------------------------------------------------
        all_status_rows = Count.query.order_by(Count.id).all()
 
        for status in all_status_rows:
 
            status_count = (
                db.session.query(Document.doc_id)
                .filter(
                    Document.doc_status == status.id,
                    Document.delete_status == 0
                )
                .count()
            )
 
            summary.append({
                "count": status_count,
                "label": status.name,
                "id": str(status.id),
                "filter_by": "status"
            })
 
            # ⭐ Insert "Assigned to Me" & "Task Assigned to Me"
            # immediately after status id = 4
            if str(status.id) == "4":
 
                # Assigned to Me
                summary.append({
                    "count": assigned_to_me,
                    "label": "Assigned to Me",
                    "id": user_id,
                    "filter_by": "other",
                    "filter_by_type": "assigned-to-me"
                })
 
                # Task Assigned to Me
                summary.append({
                    "count": task_assigned_to_me,
                    "label": "Task Assigned to Me",
                    "id": user_id,
                    "filter_by": "other",
                    "filter_by_type": "task-assigned-to-me"
                })
 
        return jsonify({
            "status": 1,
            "message": "Summary generated",
            "data": summary
        }), 200
 
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200
 
    

 
 
@document_list_bp.route("/assignee/all", methods=["POST"])
def get_assigned_users():
    try:
        # Fetch all users
        users = db.session.query(
            User.uid,
            User.first_name,
            User.middle_name,
            User.last_name
        ).order_by(User.first_name.asc()).all()
 
        user_list = []
 
        for user in users:
            # Build full name
            name_parts = []
 
            if user.first_name:
                name_parts.append(user.first_name)
            if user.middle_name:
                name_parts.append(user.middle_name)
            if user.last_name:
                name_parts.append(user.last_name)
 
            full_name = " ".join(name_parts)
 
            user_list.append({
                "id": user.uid,
                "name": full_name
            })
 
        return jsonify({
            "status": 1,
            "data": user_list
        }), 200
 
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200
 
 
   
 
@document_list_bp.route("/letter_type/all", methods=["POST"])
def get_document_type_list():
    try:
        doc_type_rows = db.session.query(
            DocTypeMaster.doc_type_id,
            DocTypeMaster.doc_type_name
        ).filter_by(del_status=0).all()
 
        doc_type_list = [
            {
                "id": row.doc_type_id,
                "name": row.doc_type_name
            }
            for row in doc_type_rows
        ]
 
        return jsonify({
            "status": 1,
            "data": doc_type_list
        }), 200
 
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200
 

    

@document_list_bp.route("/list", methods=["POST"])
def get_document_list():
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
        filterSummaryData = data.get("filterSummaryData", {})
 
        letter_type_id = filterData.get("letter_type")
        filter_assignee = filterData.get("assignee")
        filter_status_from_filterdata = filterData.get("document_status")
 
        summary_filter_by = filterSummaryData.get("filter_by")
        filter_by_type = filterSummaryData.get("filter_by_type")
        filter_status_from_summary = filterSummaryData.get("id")
 
        # ----------------------------
        # Base Query (ONLY NON-DELETED)
        # ----------------------------
        query = db.session.query(
            Document.doc_id.label("document_id"),
            Document.doc_filename.label("document_name"),
            Document.doc_type_code,
            Document.doc_status,
            Document.created_at,
            Document.updated_at,
            Document.assign_to,
            Document.parent_doc_id,
            Document.doc_attach_status,
            Document.error_message
        ).filter(
            Document.delete_status == 0
        )
 
        # ----------------------------
        # Letter Type Filter
        # ----------------------------
        if letter_type_id:
            type_row = (
                db.session.query(DocTypeMaster.doc_type_code)
                .filter(DocTypeMaster.doc_type_id == int(letter_type_id))
                .first()
            )
            if type_row:
                query = query.filter(
                    Document.doc_type_code == type_row.doc_type_code
                )
 
        # ----------------------------
        # Assignee Filter (Document)
        # ----------------------------
        if filter_assignee:
            query = query.filter(Document.assign_to == int(filter_assignee))
 
        # ----------------------------
        # Summary Filters
        # ----------------------------
        task_mode = False
 
        if summary_filter_by == "other" and filter_by_type == "assigned-to-me" and filter_status_from_summary:
            query = query.filter(Document.assign_to == int(filter_status_from_summary))
 
        elif summary_filter_by == "other" and filter_by_type == "task-assigned-to-me" and filter_status_from_summary:
            task_mode = True
            query = (
                query.join(
                    EhsDocumentTask,
                    EhsDocumentTask.doc_id == Document.doc_id
                )
                .filter(
                    EhsDocumentTask.assign_to == int(filter_status_from_summary)
                )
                .distinct(Document.doc_id)
            )
 
        # ----------------------------
        # Status Filter
        # ----------------------------
        final_status_filter = None
        if summary_filter_by == "status" and filter_status_from_summary:
            final_status_filter = int(filter_status_from_summary)
        elif filter_status_from_filterdata:
            final_status_filter = int(filter_status_from_filterdata)
 
        if final_status_filter is not None:
            query = query.filter(Document.doc_status == final_status_filter)
 
        # ----------------------------
        # Total Count
        # ----------------------------
        total_documents = query.count()
 
        # ----------------------------
        # Fetch Documents
        # ----------------------------
        documents = (
            query.order_by(Document.doc_id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
 
        # ----------------------------
        # Patient (single)
        # ----------------------------
        patient = db.session.query(
            PatientModel.patient_name,
            PatientModel.phone_no
        ).first()
 
        results = []
 
        for doc in documents:
 
            # ----------------------------
            # Patient Info
            # ----------------------------
            patient_info = (
                f"{patient.patient_name} {patient.phone_no}"
                if doc.doc_status in [3, 4, 5, 6] and patient
                else ""
            )
 
            # ----------------------------
            # Letter Type
            # ----------------------------
            doc_type = (
                db.session.query(DocTypeMaster.doc_type_name)
                .filter(DocTypeMaster.doc_type_code == doc.doc_type_code)
                .first()
            )
            letter_type = doc_type.doc_type_name if doc_type else ""
 
            # ----------------------------
            # Status Info
            # ----------------------------
            status_row = (
                db.session.query(Count.name, Count.color_code)
                .filter(Count.id == doc.doc_status)
                .first()
            )
            document_status = status_row.name if status_row else ""
            color_code = status_row.color_code if status_row else "#000000"
 
            # ----------------------------
            # Assigned To (DOCUMENT or TASK)
            # ----------------------------
            assigned_name = ""
 
            if task_mode:
                task_user = (
                    db.session.query(
                        User.first_name,
                        User.middle_name,
                        User.last_name
                    )
                    .join(
                        EhsDocumentTask,
                        EhsDocumentTask.assign_to == User.uid
                    )
                    .filter(
                        EhsDocumentTask.doc_id == doc.document_id,
                        EhsDocumentTask.assign_to == int(filter_status_from_summary)
                    )
                    .first()
                )
 
                if task_user:
                    assigned_name = " ".join(
                        filter(None, [
                            task_user.first_name,
                            task_user.middle_name,
                            task_user.last_name
                        ])
                    )
 
            else:
                if doc.assign_to:
                    user = (
                        db.session.query(
                            User.first_name,
                            User.middle_name,
                            User.last_name
                        )
                        .filter(User.uid == doc.assign_to)
                        .first()
                    )
                    if user:
                        assigned_name = " ".join(
                            filter(None, [
                                user.first_name,
                                user.middle_name,
                                user.last_name
                            ])
                        )
 
            # ----------------------------
            # Processed Date
            # ----------------------------
            processed_date = ""
            if doc.doc_status in [3, 4, 5, 6]:
                processed_log = (
                    db.session.query(Log.datatime)
                    .filter(
                        Log.doc_id == doc.document_id,
                        Log.doc_status == doc.doc_status
                    )
                    .order_by(Log.datatime.desc())
                    .first()
                )
                if processed_log:
                    processed_date = format_datetime(processed_log.datatime)
 
            # ----------------------------
            # Flags
            # ----------------------------
            duplicate_status = 1 if doc.parent_doc_id else 0
            error_message = doc.error_message if doc.doc_status == 7 else ""
 
            results.append({
                "id": doc.document_id,
                "document_name": doc.document_name,
                "patient_info": patient_info,
                "letter_type": letter_type,
                "document_status": document_status,
                "document_status_id": doc.doc_status,
                "document_status_color": color_code,
                "assigned_to": assigned_name,   # ✅ TASK USER NAME HERE
                "created_at": format_datetime(doc.created_at),
                "updated_at": format_datetime(doc.updated_at),
                "processed_date": processed_date,
                "duplicate_status": duplicate_status,
                "doc_attach_status": doc.doc_attach_status,
                "error_message": error_message
            })
 
        return jsonify({
            "status": 1,
            "data": results,
            "total": total_documents
        }), 200
 
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200
 

    


@document_list_bp.route("/status/all", methods=["POST"])
def get_status_list():
    try:
        status_rows = db.session.query(
            Count.id,
            Count.name,
            Count.color_code
        ).all()
 
        status = [
            {
                "id": row.id,
                "name": row.name,
                "status_color": row.color_code
            }
            for row in status_rows
        ]
       
 
        return jsonify({
            "status": 1,
            "data": status
        }), 200
 
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200
    

@document_list_bp.route("/most-recent", methods=["POST"])
def get_recent_documents():
    try:
        # Fetch last 5 recent documents
        documents = db.session.query(
            Document.doc_type_code,
            Document.created_at,
            Document.doc_id
        ).order_by(Document.created_at.desc()) \
         .limit(5).all()
 
        results = []
        now = datetime.now()
 
        for doc in documents:
 
            # created_at taken directly from DB (NO parse_date_safe)
            created_at = doc.created_at  
 
            # Fetch doc type name
            doc_type_row = db.session.query(
                DocTypeMaster.doc_type_name
            ).filter(
                DocTypeMaster.doc_type_code == doc.doc_type_code
            ).first()
 
            doc_type_name = doc_type_row.doc_type_name if doc_type_row else ""
 
            # Time difference calculation
            if created_at:
                diff = now - created_at
                seconds = diff.total_seconds()
 
                if seconds < 60:
                    time_ago = f"{int(seconds)}s"
                elif seconds < 3600:
                    time_ago = f"{int(seconds // 60)}m"
                elif seconds < 86400:
                    time_ago = f"{int(seconds // 3600)}h"
                else:
                    time_ago = f"{int(seconds // 86400)}d"
            else:
                time_ago = ""
 
            # Format created_at using your function
            created_at_formatted = format_datetime(created_at)
 
            results.append({
                "id": doc.doc_id,
                "name": doc_type_name,
                "doc_type_code": doc.doc_type_code,
                "created_at": created_at_formatted,
                "since_created": time_ago
            })
 
        return jsonify({
            "status": 1,
            "data": results
        }), 200
 
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200
    

@document_list_bp.route("/upload", methods=["POST"])
def add_document():
    try:
        file = request.files.get("file")
 
        if not file:
            return jsonify({"error": "File is required"}), 200
 
        filename = file.filename.lower()
 
        # Check if file is already PDF
        if filename.endswith(".pdf"):
            pdf_file_bytes = file.read()
        # If file is an image, convert to PDF
        elif filename.endswith((".tif", ".tiff", ".jpg", ".jpeg", ".png")):
            image = Image.open(file)
 
            pdf_pages = []
            seen_hashes = set()
 
            # Safely get frame count
            total_frames = getattr(image, "n_frames", 1)
            
            try:
                for frame_index in range(total_frames):
                    image.seek(frame_index)
 
                    # IMPORTANT: copy frame to avoid PIL reusing buffer
                    page = image.copy()
 
                    # 🚫 Skip thumbnails / invalid frames
                    if page.width < 500 or page.height < 500:
                        continue
 
                    # Convert to RGB (PDF safe)
                    if page.mode != "RGB":
                        page = page.convert("RGB")
 
                    # 🔁 Deduplicate identical frames (scanner bug fix)
                    # OPTIMIZED: Use resize for hash to reduce memory usage
                    # Create small thumbnail for comparison instead of full image bytes
                    thumbnail = page.copy()
                    thumbnail.thumbnail((100, 100), Image.Resampling.LANCZOS)
                    page_hash = hashlib.md5(thumbnail.tobytes()).hexdigest()
                    del thumbnail  # Free memory immediately
                    
                    if page_hash in seen_hashes:
                        continue
 
                    seen_hashes.add(page_hash)
                    pdf_pages.append(page)
 
            except Exception as e:
                return jsonify({"error": "Failed to process image file"}), 200
 
            if not pdf_pages:
                return jsonify({"error": "No valid image pages found"}), 200
 
            # Save multi-page PDF in memory
            pdf_bytes_io = io.BytesIO()
            pdf_pages[0].save(
                pdf_bytes_io,
                format="PDF",
                save_all=True,
                append_images=pdf_pages[1:],
                quality=85,  # Reduce quality slightly to speed up processing
                optimize=False  # Skip optimization to reduce processing time
            )
            pdf_bytes_io.seek(0)
 
            pdf_file_bytes = pdf_bytes_io.read()
            
            # Clean up memory
            del pdf_pages
            del pdf_bytes_io
            
            filename = filename.rsplit(".", 1)[0] + ".pdf"
            
        elif filename.endswith((".doc", ".docx")):

            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:
                temp_docx.write(file.read())
                temp_docx_path = temp_docx.name

            temp_dir = tempfile.gettempdir()

            base_name = os.path.splitext(os.path.basename(temp_docx_path))[0]
            temp_pdf_path = os.path.join(temp_dir, base_name + ".pdf")

            try:
                subprocess.run(
                    [
                        "soffice",  # ✅ no full path
                        "--headless",
                        "--convert-to", "pdf",
                        "--outdir", temp_dir,
                        temp_docx_path,
                    ],
                    check=True,
                )

                # 🔥 Wait until file exists (Windows sometimes delays)
                if not os.path.exists(temp_pdf_path):
                    raise Exception("PDF conversion failed. File not created.")

                with open(temp_pdf_path, "rb") as pdf_file:
                    pdf_file_bytes = pdf_file.read()
            except Exception as e:
                return jsonify({"error": str(e)}), 200

            finally:
                if os.path.exists(temp_docx_path):
                    os.remove(temp_docx_path)

                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)

            filename = os.path.splitext(filename)[0] + ".pdf"

        else:
            return jsonify({"error": "Only PDF or image files are allowed"}), 200
 
        # Upload to S3
        s3_path = upload_to_s3(io.BytesIO(pdf_file_bytes), filename)
 
        # Save to DB
        doc = Document(
            doc_type_code="N/A",
            doc_filename=filename,
            doc_file_path=s3_path,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            doc_attach_status=0
        )
        db.session.add(doc)
        db.session.commit()
 
        return jsonify({
            "status": "1",
            "message": "File uploaded successfully",
            "doc_id": doc.doc_id
        }), 200
 
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 200

@document_list_bp.route("/log", methods=["POST"])
def ehs_doc_log():
    try:
        data=request.get_json()
        doc_id=data.get("doc_id")
        if not doc_id:
            return jsonify({"error":"Missing doc_id"}),200
        doc_log=Log.query.filter_by(doc_id=doc_id).all()
        log_list=[]
        for doc in doc_log:
            log_list.append({
                "log_id":doc.log_id,
                "doc_id":doc.doc_id,
                "doc_status":doc.doc_status,
                "doc_status_label":Count.query.filter_by(id=doc.doc_status).first().name,
                "date_time":format_datetime(doc.datatime)
            })
       
        return jsonify({
            "status": 1,
            "message": "Document log fetched successfully",
            "data": log_list
        }), 200
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200
    
# Delete a document do soft delete
@document_list_bp.route("/delete", methods=["POST"])
@require_privilege("ADMIN")
def delete_document():
    try:
        data=request.get_json()
        doc_ids=data.get("doc_ids",[])
        if not doc_ids:
            return jsonify({"error":"Missing document_ids","status":0}),200
        for doc_id in doc_ids:
    # STEP 1: Fetch the document
            document = Document.query.filter_by(doc_id=doc_id, delete_status=0).first()
    

             
    # STEP 3: Soft delete in DB
            document.delete_status = 1
            document.updated_at = datetime.utcnow()
            db.session.commit()
 
        return jsonify({
            "status": 1,
            "message": "Document deleted successfully"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e),"status":0}), 200