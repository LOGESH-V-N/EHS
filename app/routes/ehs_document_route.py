from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.ehs_document import Document
from app.utils.document_upload import upload_to_s3
from app.utils.document_delete import delete_from_s3
from app.utils.decode_file import decode_filename
from datetime import datetime
from app.models.ehs_log import Log
from app.utils.date_formatter import format_datetime
from app.models.ehs_count_master import Count
from app.models.ehs_doc_priority import Ehs_Doc_Priority
from app.models.ehs_doc_assignee import EhsDocumentAssignee
import imaplib
import email
from email.header import decode_header
import os
from datetime import datetime
from io import BytesIO
from app.utils.document_download import download_from_s3

document_bp = Blueprint("document_bp", __name__)




# = Blueprint("delete_doc_bp", __name__)

@document_bp.route("/delete-document/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id):

    # STEP 1: Fetch the document
    document = Document.query.filter_by(doc_id=doc_id, delete_status=0).first()

    if not document:
        return jsonify({"error": "Document not found or already deleted"}), 404

    # STEP 2: Delete file from S3
    try:
        delete_from_s3(document.doc_file_path)
    except Exception as e:
        return jsonify({
            "error": "Failed to delete file from S3",
            "details": str(e)
        }), 500

    # STEP 3: Soft delete in DB
    try:
        document.delete_status = 1
        document.updated_at = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        return jsonify({
            "error": "S3 file deleted but DB update failed",
            "details": str(e)
        }), 500

    return jsonify({
        "status": "success",
        "message": "Document deleted successfully",
        "data":{"doc_id": doc_id}
    }), 200


# Import documents from email

@document_bp.route("/import-from-email", methods=["POST"])
def import_documents_from_email():

    # Step 1: Connect to email
    EMAIL = os.getenv("Email")
    PASSWORD = os.getenv("Password")    
    SERVER = os.getenv("Server")

    try:
        imap = imaplib.IMAP4_SSL(SERVER)
        imap.login(EMAIL, PASSWORD)
        imap.select("INBOX")
    except Exception as e:
        return jsonify({"status": "error", "message": f"Email connection failed: {str(e)}"}), 500

    # Search all emails
    status, messages = imap.search(None, "UNSEEN")
    email_ids = messages[0].split()

    uploaded_docs = []
    

    for eid in email_ids:
        status, msg_data = imap.fetch(eid, "(RFC822)")
        message = email.message_from_bytes(msg_data[0][1])

        if message.is_multipart():
            for part in message.walk():

                if part.get_content_disposition() == "attachment":

                    filename = part.get_filename()
                    filename = decode_filename(filename)

                    file_bytes = part.get_payload(decode=True)
                    file_stream = BytesIO(file_bytes)

                    # Upload to S3 using your existing utility
                    file_url = upload_to_s3(file_stream, filename)

                    # Insert into DB using your model
                    doc = Document(
                        doc_type_code="N/A",
                        doc_filename=filename,
                        doc_file_path=file_url,
                        created_at=datetime.utcnow(),
                        doc_status=1,
                        delete_status=0,
                        updated_at=datetime.utcnow()
                    )
                    db.session.add(doc)
                    db.session.commit()

                    uploaded_docs.append({
                        "filename": filename,
                        "file_path": file_url
                    })

        # mark email as read
        imap.store(eid, '+FLAGS', '\\Seen')

    imap.close()
    imap.logout()

    return jsonify({
        "status": "success",
        "message": "Documents imported successfully from email",
        "data": uploaded_docs
    }), 200


@document_bp.route("/assignee", methods=["POST"])
def assignee():
    try:
        data=request.get_json()
        doc_ids=data.get("doc_ids",[])
        assign_to=data.get("assign_to")
        due_date=data.get("due_date")
        priority_id=data.get("priority_id")
        if due_date=="":
            due_date=None
        if not doc_ids or not assign_to or not priority_id:
            return jsonify({"status":0,"message":"doc_ids and assign_to are required"}),200
        for doc_id in doc_ids:
            doc=Document.query.filter_by(doc_id=doc_id).first()
           
            if doc:
                assignee=EhsDocumentAssignee(
                    assignee_id=assign_to,
                    doc_id=doc_id,
                    priority_id=priority_id,
                    due_date=due_date,
                    created_by=2
                )
                db.session.add(assignee)
                db.session.commit()
 
            else:
                return jsonify({"status":0,"message":"Document not found"}),200
            change_doc_status=Document.query.filter_by(doc_id=doc_id).first()
            change_doc_status.doc_status=4
            change_doc_status.assign_to=assign_to
            db.session.commit()
            log=Log(
                doc_id=doc_id,
                doc_status=4,
                datatime=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
 
               
        return jsonify({"status":1,"message":"Document assigned successfully"}),200
    except Exception as e:
        return jsonify({"status":0,"message":str(e)}),200
 
 

@document_bp.route("/archive", methods=["POST"])
def archived():
    try:
        data=request.get_json()
        doc_ids=data.get("doc_ids",[])
        if not doc_ids:
            return jsonify({"status":0,"message":"doc_ids are required"}),200
        for doc_id in doc_ids:
            doc=Document.query.filter_by(doc_id=doc_id).first()
            if doc:
                doc.doc_status=6
                db.session.commit()
            else:
                return jsonify({"status":0,"message":"Document not found"}),200
            log=Log(
                doc_id=doc_id,
                doc_status=6,
                datatime=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
               
        return jsonify({"status":1,"message":"Document archived successfully"}),200
    except Exception as e:
        return jsonify({"status":0,"message":str(e)}),200

# Unarchive a document 
@document_bp.route("/unarchive", methods=["POST"])
def unarchived():
    try:
        data=request.get_json()
        doc_ids=data.get("doc_ids",[])
        if not doc_ids:
            return jsonify({"status":0,"message":"doc_ids are required"}),200
        for doc_id in doc_ids:
            doc=Document.query.filter_by(doc_id=doc_id).first()
            if doc:
                doc.doc_status=5
                db.session.commit()
            else:
                return jsonify({"status":0,"message":"Document not found"}),200
            log=Log(
                doc_id=doc_id,
                doc_status=5,
                datatime=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
               
        return jsonify({"status":1,"message":"Document unarchived successfully"}),200
    except Exception as e:
        return jsonify({"status":0,"message":str(e)}),200
 
 

            
@document_bp.route("/priority", methods=["POST"])
def priority_api():
    try:
        priority = Ehs_Doc_Priority.query.all()
        priority_list = []
        for pri in priority:
            priority = {
                "id": pri.id,
                "name": pri.name
            }
            priority_list.append(priority)
        return jsonify({"status": 1,"message":"Priority list fetched successfully", "data": priority_list}), 200
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200

@document_bp.route("/download", methods=["POST"])
def download_document():
    try:
        data = request.get_json()
        doc_id = data.get("doc_id")

        if not doc_id:
            return jsonify({
                "status": 0,
                "message": "doc_id is required"
            }), 400

        # Fetch document
        document = Document.query.filter_by(
            doc_id=doc_id,
            delete_status=0
        ).first()

        if not document or not document.doc_file_path:
            return jsonify({
                "status": 0,
                "message": "Document or file path not found"
            }), 404

        # Download from S3
        file_data = download_from_s3(document.doc_file_path)

        return jsonify({
            "status": 1,
            "message": "File downloaded successfully",
            "data": file_data
        }), 200

    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 500
        
        