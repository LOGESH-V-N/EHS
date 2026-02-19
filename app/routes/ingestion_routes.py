from flask import Blueprint, jsonify
import os
import imaplib
import email

from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from io import BytesIO
from flask import current_app
from app import db
from app.models.ehs_injestion import EmailIngestionState
from app.models.ehs_document import Document
from app.utils.document_upload import upload_to_s3
from app.utils.decode_file import decode_filename
from app.models.ehs_email_master import EhsEmailMaster
from PIL import Image
import hashlib
import io
import boto3


ingestion_bp = Blueprint("ingestion_bp", __name__, url_prefix="/ingestion")






@ingestion_bp.route("/import-from-email", methods=["POST"])
def import_documents_from_email():
    try:
        # ----------------------------
        # Load email configuration
        # ----------------------------
        email_db = EhsEmailMaster.query.filter_by(status_id=1).first()
        if not email_db:
            return jsonify({"status": "error", "message": "No email configuration found"}), 500

        EMAIL = email_db.sync_email
        PASSWORD = email_db.sync_password
        SERVER = email_db.sync_server

        # ----------------------------
        # Connect to IMAP
        # ----------------------------
        imap = imaplib.IMAP4_SSL(SERVER, 993, timeout=30)
        imap.login(EMAIL, PASSWORD)
        imap.select("INBOX")

        # ----------------------------
        # Get last ingestion state
        # ----------------------------
        last_state = (
            EmailIngestionState.query
            .order_by(
                EmailIngestionState.last_fetched_at.is_(None),
                EmailIngestionState.last_fetched_at.desc()
            )
            .first()
        )

        last_fetched_at = last_state.last_fetched_at if last_state else None

        if last_fetched_at:
            since_date = last_fetched_at.strftime("%d-%b-%Y")
            status, messages = imap.search(None, f'(SINCE "{since_date}")')
        else:
            status, messages = imap.search(None, "ALL")

        email_ids = messages[0].split()

        uploaded_docs = []
        newest_email_time = last_fetched_at
        total_new_docs = 0

        # ----------------------------
        # Process emails
        # ----------------------------
        for eid in email_ids:
            status, msg_data = imap.fetch(eid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            email_date = parsedate_to_datetime(msg.get("Date"))
            if not email_date:
                continue

            if email_date.tzinfo:
                email_date = email_date.astimezone(timezone.utc).replace(tzinfo=None)

            if last_fetched_at and email_date <= last_fetched_at:
                continue

            # ----------------------------
            # Process attachments
            # ----------------------------
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_disposition() != "attachment":
                        continue

                    raw_filename = part.get_filename()
                    if not raw_filename:
                        continue

                    filename = decode_filename(raw_filename).lower()
                    file_bytes = part.get_payload(decode=True)

                    if not file_bytes:
                        continue

                    try:
                        # ----------------------------
                        # PDF → upload directly
                        # ----------------------------
                        if filename.endswith(".pdf"):
                            upload_bytes = file_bytes
                            final_filename = filename

                        # ----------------------------
                        # Image → convert to PDF
                        # ----------------------------
                        elif filename.endswith((".tif", ".tiff", ".jpg", ".jpeg", ".png")):
                            image = Image.open(io.BytesIO(file_bytes))

                            pdf_pages = []
                            seen_hashes = set()
                            total_frames = getattr(image, "n_frames", 1)

                            for frame_index in range(total_frames):
                                image.seek(frame_index)
                                page = image.copy()

                                # Skip thumbnails / junk frames
                                if page.width < 500 or page.height < 500:
                                    continue

                                if page.mode != "RGB":
                                    page = page.convert("RGB")

                                # Deduplicate frames (scanner bug fix)
                                page_hash = hashlib.md5(page.tobytes()).hexdigest()
                                if page_hash in seen_hashes:
                                    continue

                                seen_hashes.add(page_hash)
                                pdf_pages.append(page)

                            if not pdf_pages:
                                continue

                            pdf_io = io.BytesIO()
                            pdf_pages[0].save(
                                pdf_io,
                                format="PDF",
                                save_all=True,
                                append_images=pdf_pages[1:]
                            )
                            pdf_io.seek(0)

                            upload_bytes = pdf_io.read()
                            final_filename = filename.rsplit(".", 1)[0] + ".pdf"

                        # ----------------------------
                        # Unsupported file → skip
                        # ----------------------------
                        else:
                            continue

                        # ----------------------------
                        # Upload to S3
                        # ----------------------------
                        file_stream = BytesIO(upload_bytes)
                        file_url = upload_to_s3(file_stream, final_filename)

                        # ----------------------------
                        # Save document
                        # ----------------------------
                        doc = Document(
                            doc_type_code="N/A",
                            doc_filename=final_filename,
                            doc_file_path=file_url,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                            doc_status=1,
                            delete_status=0
                        )

                        db.session.add(doc)

                        uploaded_docs.append({
                            "filename": final_filename,
                            "file_path": file_url
                        })

                        total_new_docs += 1

                    except Exception as e:
                        print(f"Attachment processing failed: {filename}, error: {e}")
                        continue

            # Track newest email timestamp
            if not newest_email_time or email_date > newest_email_time:
                newest_email_time = email_date

            imap.store(eid, "+FLAGS", "\\Seen")

        # ----------------------------
        # Commit documents
        # ----------------------------
        db.session.commit()

        # ----------------------------
        # Save ingestion state
        # ----------------------------
        ingestion_log = EmailIngestionState(
            last_fetched_at=newest_email_time,
            total_documents=total_new_docs,
            config_email_id=email_db.id
        )

        db.session.add(ingestion_log)
        db.session.commit()

        imap.close()
        imap.logout()

        return jsonify({
            "status": "success",
            "last_fetched_at": newest_email_time,
            "new_documents": total_new_docs,
            "data": uploaded_docs
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@ingestion_bp.route("/initiate", methods=["POST"])
def process_initiate():
    try:
        print("hello0")
        lambda_client = boto3.client("lambda",aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
        region_name=current_app.config["AWS_REGION"])
        print("hello1")

        response = lambda_client.invoke(
                FunctionName="fetch-all-documents",
                InvocationType="RequestResponse"
            )
        status_code = response.get("StatusCode")
        if status_code==200:
            return jsonify({"message":"sucuss ","status":1})
        else:
            return jsonify({"message":"error","status":0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ingestion_bp.route("/upload-from-folder", methods=["POST"])
def upload_documents_from_folder():
    try:
        FOLDER_PATH = r"C:\Users\LT1101\Desktop\process_files"  # CHANGE THIS

        if not os.path.exists(FOLDER_PATH):
            return jsonify({"error": "Folder not found"}), 400

        uploaded_docs = []
        deleted_files = []

        for original_filename in os.listdir(FOLDER_PATH):
            file_path = os.path.join(FOLDER_PATH, original_filename)

            if not os.path.isfile(file_path):
                continue

            lower_name = original_filename.lower()

            try:
                # ---------------- PDF ----------------
                if lower_name.endswith(".pdf"):
                    with open(file_path, "rb") as f:
                        pdf_file_bytes = f.read()
                    final_filename = original_filename

                # ---------------- IMAGE → PDF ----------------
                elif lower_name.endswith((".tif", ".tiff", ".jpg", ".jpeg", ".png")):
                    image = Image.open(file_path)

                    pdf_pages = []
                    seen_hashes = set()

                    total_frames = getattr(image, "n_frames", 1)

                    for frame_index in range(total_frames):
                        image.seek(frame_index)
                        page = image.copy()

                        if page.width < 500 or page.height < 500:
                            continue

                        if page.mode != "RGB":
                            page = page.convert("RGB")

                        page_hash = hashlib.md5(page.tobytes()).hexdigest()
                        if page_hash in seen_hashes:
                            continue

                        seen_hashes.add(page_hash)
                        pdf_pages.append(page)

                    if not pdf_pages:
                        continue

                    pdf_io = io.BytesIO()
                    pdf_pages[0].save(
                        pdf_io,
                        format="PDF",
                        save_all=True,
                        append_images=pdf_pages[1:]
                    )
                    pdf_io.seek(0)

                    pdf_file_bytes = pdf_io.read()
                    final_filename = original_filename.rsplit(".", 1)[0] + ".pdf"

                else:
                    continue

                # ---------------- Upload to S3 ----------------
                s3_path = upload_to_s3(io.BytesIO(pdf_file_bytes), final_filename)

                # ---------------- Save to DB ----------------
                doc = Document(
                    doc_type_code="N/A",
                    doc_filename=final_filename,
                    doc_file_path=s3_path,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )

                db.session.add(doc)
                db.session.flush()

                uploaded_docs.append({
                    "doc_id": doc.doc_id,
                    "filename": final_filename
                })

                # ---------------- DELETE LOCAL FILE ----------------
                os.remove(file_path)
                deleted_files.append(original_filename)

            except Exception as file_error:
                # Skip this file but continue others
                print(f"Failed processing {original_filename}: {file_error}")
                continue

        db.session.commit()

        return jsonify({
            "status": 1,
            "message": "Documents uploaded successfully",
            "uploaded_count": len(uploaded_docs),
            "deleted_files_count": len(deleted_files),
            "uploaded_documents": uploaded_docs,
            "deleted_files": deleted_files
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": 0,
            "error": str(e)
        }), 500






