from flask import Blueprint, jsonify, current_app

from app.services.document_processor import download_from_s3, update_doc_status
from app.services.s3_utils import (
    process_pdf,
    extract_texts_from_images,
    post_process_with_cohere,
    save_json,
)
import os
from app.models.ehs_document import get_pending_documents
from app.services.document_processor import add_log
from app.services.document_processor import update_document_type
from app.services.s3_utils import extract_document_type
from flask import Blueprint, jsonify, request
from app.models.ehs_document import Document
from app.services.s3_utils import (
    process_pdf,
    extract_texts_from_images,
    post_process_with_cohere,
    upload_json_data_to_s3,
    storing_document_info,
    assign_parent_doc_id,
    storing_patient_info

)
from app.models.document import DocTypeMaster
from app.extensions import db
from app.utils.logger_util import get_logger
import time
from datetime import datetime
from app.services.s3_utils import snomed_mapping
from app.models.ehs_doc_history import Ehs_Document_History
from app.utils.document_upload import upload_to_s3, mail_upload_to_s3
import io
from app.models.ehs_injestion import EmailIngestionState
import subprocess
import tempfile
from PIL import Image, ImageFile, ImageSequence
import io, hashlib, traceback
import boto3
from app.utils.privilege_decorator import require_privilege









process_docs_bp = Blueprint("process_docs", __name__)
logger = get_logger("document_processor", log_dir="logs")

@process_docs_bp.route("/pending_document_ids", methods=["POST"])
@require_privilege("USER")
def pending_document_ids():

    docs=Document.query.filter_by(doc_status=1, delete_status=0).all()
    doc_ids=[]
    for doc in docs:
        if doc.message_id == "":
            message_id=None
        else:
            message_id=doc.message_id
        if doc.upload_type == 3:
            upload_type="folder"
        elif doc.upload_type == 2:
            upload_type="email"
        else:
            upload_type=""

        doc_ids.append({"doc_id":doc.doc_id,"message_id":message_id,"upload_type":upload_type,"file_name":doc.doc_filename,"s3_path":doc.doc_file_path})
    if not docs:
        logger.warning(f"No pending documents found")
        return jsonify({"doc_id":doc.doc_id,"message_id":message_id,"upload_type":upload_type,"file_name":doc.doc_filename,"s3_path":doc.doc_file_path}), 200
    
    return jsonify({"doc_ids": doc_ids}), 200
   


@process_docs_bp.route("/process-documents", methods=["POST"])
@require_privilege("USER")
def process_documents():
    docs = (
        get_pending_documents()
    )  # we want to see in the ehs_document(model) there we have written that doc_status=1 and doc_delete_status=0

    if not docs:
        logger.warning(f"No pending documents found")
        return jsonify({"message": "No pending documents"}), 200

    results = []

    for doc in docs:
        # ✅ Log initial pending state
        add_log(doc.doc_id, 1)

        try:
            # Move to in-progress ✅ logs automatically
            update_doc_status(doc, 2)
            logger.info(f"Status updated to IN-PROGRESS | doc_id={doc.doc_id}")

            # Download from S3
            local_path = download_from_s3(doc)
            logger.info(f"Downloaded file from S3 | doc_id={doc.doc_id} | path={local_path}")

            # OCR & Processing (reuse existing pipeline)
            if local_path.lower().endswith(".pdf"):
                image_paths = process_pdf(local_path)
            else:
                image_paths = [local_path]
            logger.info(f"Processed images | doc_id={doc.doc_id} | images={len(image_paths)}")

            extracted_texts = extract_texts_from_images(image_paths)
            logger.info(
            f"OCR complete | doc_id={doc.doc_id} | pages={len(extracted_texts)}"
            )
            if not extracted_texts:
                logger.error(f"No text extracted from document | doc_id={doc.doc_id}")
                update_doc_status(doc, 7,"No text extracted from document")
                return (
                    jsonify({"message": "No text extracted from document", "status": 0}),
                    200,
                )
            combined_text = "\n".join(
                [t for t in extracted_texts if isinstance(t, str)]
            )

            cohere_result = post_process_with_cohere(combined_text)
            if not cohere_result:
                logger.error(f"Cohere post-processing failed | doc_id={doc.doc_id}")
                update_doc_status(doc, 7,"Cohere post-processing failed")
                return (
                    jsonify({"message": "No text extracted from document", "status": 0}),
                    200,
            )
            logger.info(f"Cohere processing success | doc_id={doc.doc_id}")
            cohere_result_with_snomed = snomed_mapping(cohere_result)
            

            cohere_res = cohere_result.get("structured_output", [])[0]
            document_type = cohere_res.get("document_type")
            patient_info_dict = cohere_res.get("patient_info",{})
            nhs_number = patient_info_dict.get("nhs_number")
            if not nhs_number or nhs_number=="[redacted]":
                logger.error(f"NHS number not found | doc_id={doc.doc_id}")
                update_doc_status(doc, 7)
                return jsonify({"message": "No NHS number found", "status": 0}), 200
            
            if not document_type:
                logger.error(f"Document type not found | doc_id={doc.doc_id}")
                update_doc_status(doc, 7,"Document type not found")
                return jsonify({"message": "No document type found", "status": 0}), 200
            logger.info(
                f"Document type identified | doc_id={doc.doc_id} | type={document_type}"
            )
            doc_type_name = DocTypeMaster.query.filter_by(
                doc_type_code=document_type
            ).first()
            if not doc_type_name:
                logger.error(
                    f"Doc type master not found | doc_id={doc.doc_id} | type={document_type}"
                )
                update_doc_status(doc, 7,"Doc type master not found")
                return jsonify({"message": "No document type found", "status": 0}), 200

            # print(doc_type_code)
            doc.doc_type_code = doc_type_name.doc_type_code
            db.session.commit()
            logger.info(
                f"Document type updated in DB | doc_id={doc.doc_id} | code={doc.doc_type_code}"
            )

            filename_wo_ext = os.path.splitext(doc.doc_filename)[0]
            json_file_url = upload_json_data_to_s3(
                cohere_result_with_snomed, filename_wo_ext
            )
            doc.extract_file_url = json_file_url
            db.session.commit()
            logger.info(f"JSON uploaded to S3 | doc_id={doc.doc_id} | url={json_file_url}")
            Ehs_Document_History(doc_id=doc.doc_id,activity_id=1,s3_path=json_file_url)
            db.session.commit()
            if not nhs_number or nhs_number=="[redacted]":
                logger.error(f"NHS number not found | doc_id={doc.doc_id}")
                update_doc_status(doc, 7,"NHS number not found")
                return jsonify({"message": "No NHS number found", "status": 0}), 200


            storing_document_info(cohere_result_with_snomed,doc)
            storing_patient_info(cohere_result_with_snomed,doc)
            assign_parent_doc_id(doc)
            


            # Mark complete
            update_doc_status(doc, 3)

            results.append(
                {
                    "status": 1,
                    "message": "Document processed successfully",
                    "data": {
                        "doc_id": doc.doc_id,
                        "file": doc.doc_filename
                    },
                }
            )

        except Exception as e:
            print("Processing failed:", e)

            # mark failed ✅ logs automatically
            update_doc_status(doc, 7,str(e))

            results.append(
                {
                    "doc_id": doc.doc_id,
                    "file": doc.doc_filename,
                    "status": 0,
                    "error": str(e),
                }
            )

    return jsonify({"results": results})


@process_docs_bp.route("/manual-documents", methods=["POST"])
@require_privilege("USER")
def manual_process_documents():
    data = request.get_json()
 
    doc_id = data.get("doc_id")
    logger.info(f"Manual processing started | doc_id={doc_id}")
    doc = Document.query.filter_by(doc_id=doc_id).first()
    logger.info(f"Document fetched: {doc}")

    if not doc:
        logger.warning(f"No pending document found | doc_id={doc_id}")
        return jsonify({"message": "No pending documents", "status": 0}), 200

    # ✅ Log initial pending state
    add_log(doc.doc_id, 1)

    try:
        # Move to in-progress ✅ logs automatically
        update_doc_status(doc, 2)
        logger.info(f"Status updated to IN-PROGRESS | doc_id={doc.doc_id}")

        # Download from S3
        local_path = download_from_s3(doc)
        logger.info(
            f"Downloaded file from S3 | doc_id={doc.doc_id} | path={local_path}"
        )

        # OCR & Processing (reuse existing pipeline)
        if local_path.lower().endswith(".pdf"):
            image_paths = process_pdf(local_path)
        else:
            image_paths = [local_path]

        logger.info(
            f"Processing images | doc_id={doc.doc_id} | images={len(image_paths)}"
        )
        extracted_texts = extract_texts_from_images(image_paths)
        print("extracted_texts",extracted_texts)
        logger.info(
            f"OCR complete | doc_id={doc.doc_id} | pages={len(extracted_texts)}"
        )
        if not extracted_texts:
            logger.error(f"No text extracted from document | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"No text extracted from document")
            return (
                jsonify({"message": "No text extracted from document", "status": 0}),
                200,
            )
        combined_text = "\n".join([t for t in extracted_texts if isinstance(t, str)])

        cohere_result = post_process_with_cohere(combined_text)
        
        if not cohere_result:
            logger.error(f"Cohere post-processing failed | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"Cohere post-processing failed")
            return (
                jsonify({"message": "No text extracted from document", "status": 0}),
                200,
            )
        logger.info(f"Cohere processing success | doc_id={doc.doc_id}")
        cohere_result_with_snomed = snomed_mapping(cohere_result)
        #print(f"cohere_result_with_snomed_AS:{cohere_result_with_snomed}")
        


        # Save JSON output file
        cohere_res = cohere_result.get("structured_output", [])[0]
        document_type = cohere_res.get("document_type")
        patient_info_dict = cohere_res.get("patient_info",{})
        nhs_number = patient_info_dict.get("nhs_number")
        
        
        if not document_type:
            logger.error(f"Document type not found | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"Document type not found")
            return jsonify({"message": "No document type found", "status": 0}), 200
        logger.info(
            f"Document type identified | doc_id={doc.doc_id} | type={document_type}"
        )
        doc_type_name = DocTypeMaster.query.filter_by(
            doc_type_code=document_type
        ).first()
        if not doc_type_name:
            logger.error(
                f"Doc type master not found | doc_id={doc.doc_id} | type={document_type}"
            )
            update_doc_status(doc, 7,"Doc type master not found")
            return jsonify({"message": "No document type found", "status": 0}), 200

        # print(doc_type_code)
        doc.doc_type_code = doc_type_name.doc_type_code
        db.session.commit()
        logger.info(
            f"Document type updated in DB | doc_id={doc.doc_id} | code={doc.doc_type_code}"
        )

        filename_wo_ext = os.path.splitext(doc.doc_filename)[0]
        json_file_url = upload_json_data_to_s3(
            cohere_result_with_snomed, filename_wo_ext
        )
        doc.extract_file_url = json_file_url
        db.session.commit()
        logger.info(f"JSON uploaded to S3 | doc_id={doc.doc_id} | url={json_file_url}")
        history=Ehs_Document_History(doc_id=doc.doc_id,activity_id=1,s3_path=json_file_url)
        db.session.add(history)
        db.session.commit()
        if not nhs_number or nhs_number=="[redacted]":
            logger.error(f"NHS number not found | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"NHS number not found")
            return jsonify({"message": "No NHS number found", "status": 0}), 200

        storing_document_info(cohere_result_with_snomed,doc)
        storing_patient_info(cohere_result_with_snomed,doc)
        assign_parent_doc_id(doc)



        # Mark complete ✅ logs automatically
        update_doc_status(doc, 3)
        logger.info(f"Document processed successfully | doc_id={doc.doc_id}")
        return jsonify({"message": "Document processed successfully", "status": 1}), 200

    except Exception as e:
        # mark failed ✅ logs automatically
        logger.exception(
            f"Document processing failed | doc_id={doc_id} | error={str(e)}"
        )
        update_doc_status(doc, 7,str(e))
        return jsonify({"message": "Document processing failed", "status": 0,"error":str(e)}), 200


@process_docs_bp.route("/uploads", methods=["POST"])
@require_privilege("USER")
def add_document():
    try:
        sender = request.form.get("sender")
        timestamp = str(request.form.get("timestamp"))
        message_id = request.form.get("message_id")
        document_count = int(request.form.get("attachment_count"))
        start_date = request.form.get("start_date")
        file = request.files.get("file")  # client may still call it 'pdf'
 
        if not file:
            return jsonify({"error": "File is required"}), 200

        
 
        filename = file.filename.lower()
 
        # Check if file is already PDF
        if filename.endswith(".pdf"):
            pdf_file_bytes = file.read()  # Read file bytes directly
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
                    page_hash = hashlib.md5(page.tobytes()).hexdigest()
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
                append_images=pdf_pages[1:]
            )
            pdf_bytes_io.seek(0)
 
            pdf_file_bytes = pdf_bytes_io.read()
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
        s3_path = mail_upload_to_s3(io.BytesIO(pdf_file_bytes), filename,timestamp)
 
        # Save to DB
        doc = Document(
            doc_type_code="N/A",
            doc_filename=filename,
            doc_file_path=s3_path,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            upload_type=2,
            email_sender=sender,
            email_time_stamp=timestamp,
            message_id=message_id,
            doc_attach_status=0            
        )
        db.session.add(doc)
        db.session.commit()
        last_state = (
            EmailIngestionState.query
            .order_by(
                EmailIngestionState.id.desc()
            )
            .first()
        )
        should_insert = True


        if last_state:
            db_time = last_state.last_fetched_at if last_state.last_fetched_at else None

            if db_time == start_date and last_state.total_documents == document_count:
                should_insert = False

        if should_insert:
            time_stamp = EmailIngestionState(
                last_fetched_at=start_date,
                total_documents=document_count,
                config_email_id=1
            )
            db.session.add(time_stamp)
            db.session.commit()
        
        return jsonify({
            "status": "1",
            "message": "File uploaded successfully",
            "doc_id": doc.doc_id
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@process_docs_bp.route("/mail-documents", methods=["POST"])
@require_privilege("USER")
def mail_process_documents():
    data = request.get_json()
 
    doc_id = data.get("doc_id")
    logger.info(f"Manual processing started | doc_id={doc_id}")
    doc = Document.query.filter_by(doc_id=doc_id).first()
    logger.info(f"Document fetched: {doc}")

    if not doc:
        logger.warning(f"No pending document found | doc_id={doc_id}")
        return jsonify({"message": "No pending documents", "status": 0}), 404

    # ✅ Log initial pending state
    add_log(doc.doc_id, 1)

    try:
        # Move to in-progress ✅ logs automatically
        update_doc_status(doc, 2)
        logger.info(f"Status updated to IN-PROGRESS | doc_id={doc.doc_id}")

        # Download from S3
        local_path = download_from_s3(doc)
        logger.info(
            f"Downloaded file from S3 | doc_id={doc.doc_id} | path={local_path}"
        )

        # OCR & Processing (reuse existing pipeline)
        if local_path.lower().endswith(".pdf"):
            image_paths = process_pdf(local_path)
            if not image_paths:
                logger.error(f"No images extracted from document | doc_id={doc.doc_id}")
                update_doc_status(doc, 7,"No images extracted from document")
                return (
                    jsonify({"message": "No images extracted from document", "status": 0}),
                    400,
                )
        else:
            image_paths = [local_path]

        logger.info(
            f"Processing images | doc_id={doc.doc_id} | images={len(image_paths)}"
        )
        extracted_texts = extract_texts_from_images(image_paths)
        logger.info(
            f"OCR complete | doc_id={doc.doc_id} | pages={len(extracted_texts)}"
        )
        if not extracted_texts:
            logger.error(f"No text extracted from document | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"No text extracted from document")
            return (
                jsonify({"message": "No text extracted from document", "status": 0}),
                400,
            )
        combined_text = "\n".join([t for t in extracted_texts if isinstance(t, str)])

        cohere_result = post_process_with_cohere(combined_text)
        
        if not cohere_result:
            logger.error(f"Cohere post-processing failed | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"Cohere post-processing failed")
            return (
                jsonify({"message": "No text extracted from document", "status": 0}),
                400,
            )
        logger.info(f"Cohere processing success | doc_id={doc.doc_id}")
        cohere_result_with_snomed = snomed_mapping(cohere_result)
        #print(f"cohere_result_with_snomed_AS:{cohere_result_with_snomed}")
        


        # Save JSON output file
        cohere_res = cohere_result.get("structured_output", [])[0]
        document_type = cohere_res.get("document_type")
        patient_info_dict = cohere_res.get("patient_info",{})
        nhs_number = patient_info_dict.get("nhs_number")
        
        
        if not document_type:
            logger.error(f"Document type not found | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"Document type not found")
            return jsonify({"message": "No document type found", "status": 0}), 400
        logger.info(
            f"Document type identified | doc_id={doc.doc_id} | type={document_type}"
        )
        doc_type_name = DocTypeMaster.query.filter_by(
            doc_type_code=document_type
        ).first()
        if not doc_type_name:
            logger.error(
                f"Doc type master not found | doc_id={doc.doc_id} | type={document_type}"
            )
            update_doc_status(doc, 7,"Doc type master not found")
            return jsonify({"message": "No document type found", "status": 0}), 400

        # print(doc_type_code)
        doc.doc_type_code = doc_type_name.doc_type_code
        db.session.commit()
        logger.info(
            f"Document type updated in DB | doc_id={doc.doc_id} | code={doc.doc_type_code}"
        )

        filename_wo_ext = os.path.splitext(doc.doc_filename)[0]
        json_file_url = upload_json_data_to_s3(
            cohere_result_with_snomed, filename_wo_ext
        )
        doc.extract_file_url = json_file_url
        db.session.commit()
        logger.info(f"JSON uploaded to S3 | doc_id={doc.doc_id} | url={json_file_url}")
        history=Ehs_Document_History(doc_id=doc.doc_id,activity_id=1,s3_path=json_file_url)
        db.session.add(history)
        db.session.commit()
        if not nhs_number or nhs_number=="[redacted]":
            logger.error(f"NHS number not found | doc_id={doc.doc_id}")
            update_doc_status(doc, 7,"NHS number not found")
            return jsonify({"message": "No NHS number found", "status": 0}), 400

        storing_document_info(cohere_result_with_snomed,doc)
        storing_patient_info(cohere_result_with_snomed,doc)
        assign_parent_doc_id(doc)



        # Mark complete ✅ logs automatically
        update_doc_status(doc, 3)
        logger.info(f"Document processed successfully | doc_id={doc.doc_id}")
        return jsonify({"message": "Document processed successfully", "status": 1}), 200

    except Exception as e:
        # mark failed ✅ logs automatically
        logger.exception(
            f"Document processing failed | doc_id={doc_id} | error={str(e)}"
        )
   
        update_doc_status(doc, 7,str(e))
        return jsonify({"message": "Document processing failed", "status": 0,"error":str(e)}), 400



 
@process_docs_bp.route("/upload", methods=["POST"])
@require_privilege("USER")
def upload_attachment():
    try:
        print("test2")
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        print("test1")
        file = request.files["file"]
        time_stamp=request.form.get("timestamp")
        filename = file.filename
        if not filename:
            return jsonify({"error": "Filename missing"}), 400
        
        # Convert ISO string to datetime object
        dt = datetime.strptime(time_stamp, "%Y-%m-%dT%H:%M:%SZ")
        file_date = dt.strftime("%d%m%y%H%M%S")
        unique_name=f"{file_date}--{filename}"

        # Extract only date
        date = dt.date()

 
        S3_BUCKET = current_app.config["AWS_BUCKET"]
        s3 = boto3.client("s3")

        # Get today's date folder
        mail_folder = current_app.config["AWS_BUCKET_MAIL"]
        today_folder = datetime.utcnow().strftime("%Y-%m-%d")
        # Construct S3 key
        s3_key = f"{mail_folder}/{date}/{unique_name}"
      

        # Upload to S3
        s3.upload_fileobj(
            file,
            S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": file.content_type}
        )
        return jsonify({
            "status": "success",
            "bucket": S3_BUCKET,
            "path": s3_key
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500