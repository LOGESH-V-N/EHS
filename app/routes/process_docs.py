from flask import Blueprint, jsonify

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
)
from app.models.document import DocTypeMaster
from app.extensions import db
from app.utils.logger_util import get_logger
import time
from datetime import datetime
from app.services.s3_utils import snomed_mapping


process_docs_bp = Blueprint("process_docs", __name__)
logger = get_logger("document_processor", log_dir="logs")


@process_docs_bp.route("/process-documents", methods=["POST"])
def process_documents():
    docs = (
        get_pending_documents()
    )  # we want to see in the ehs_document(model) there we have written that doc_status=1 and doc_delete_status=0

    if not docs:
        return jsonify({"message": "No pending documents"}), 200

    results = []

    for doc in docs:
        # ✅ Log initial pending state
        add_log(doc.doc_id, 1)

        try:
            # Move to in-progress ✅ logs automatically
            update_doc_status(doc, 2)

            # Download from S3
            local_path = download_from_s3(doc)

            # OCR & Processing (reuse existing pipeline)
            if local_path.lower().endswith(".pdf"):
                image_paths = process_pdf(local_path)
            else:
                image_paths = [local_path]

            extracted_texts = extract_texts_from_images(image_paths)
            print(f"extracted_texts:{extracted_texts}")
            combined_text = "\n".join(
                [t for t in extracted_texts if isinstance(t, str)]
            )

            cohere_result = post_process_with_cohere(combined_text)
            print(f"cohere_result:{cohere_result}")
            cohere_result_with_snomed = snomed_mapping(cohere_result)
            print(f"cohere_result_with_snomed:{cohere_result_with_snomed}")

            # ✅ Extract detected document type
            detected_doc_type = extract_document_type(cohere_result_with_snomed)

            # ✅ Update document type in DB
            update_document_type(doc, detected_doc_type)

            # Save JSON output file
            filename_wo_ext = os.path.splitext(doc.doc_filename)[0]
            json_file = save_json(cohere_result_with_snomed, filename_wo_ext)

            # Mark complete
            update_doc_status(doc, 3)

            results.append(
                {
                    "status": 1,
                    "message": "Document processed successfully",
                    "data": {
                        "doc_id": doc.doc_id,
                        "file": doc.doc_filename,
                        "json_output": json_file,
                    },
                }
            )

        except Exception as e:
            print("Processing failed:", e)

            # mark failed ✅ logs automatically
            update_doc_status(doc, 4)

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
def manual_process_documents():
    data = request.get_json()
    print(data)
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
        logger.info(
            f"OCR complete | doc_id={doc.doc_id} | pages={len(extracted_texts)}"
        )
        if not extracted_texts:
            logger.error(f"No text extracted from document | doc_id={doc.doc_id}")
            update_doc_status(doc, 7)
            return (
                jsonify({"message": "No text extracted from document", "status": 0}),
                200,
            )
        combined_text = "\n".join([t for t in extracted_texts if isinstance(t, str)])

        cohere_result = post_process_with_cohere(combined_text)
        #print(f"cohere_result_for_AS:{cohere_result}")
        if not cohere_result:
            logger.error(f"Cohere post-processing failed | doc_id={doc.doc_id}")
            update_doc_status(doc, 7)
            return (
                jsonify({"message": "No text extracted from document", "status": 0}),
                200,
            )
        logger.info(f"Cohere processing success | doc_id={doc.doc_id}")
        cohere_result_with_snomed = snomed_mapping(cohere_result)
        #print(f"cohere_result_with_snomed_AS:{cohere_result_with_snomed}")
        
        # ✅ NEW: Save JSON locally
        local_json_path = save_json_locally(
            cohere_result_with_snomed,
            doc_id=doc.doc_id
        )
        logger.info(
            f"JSON saved locally | doc_id={doc.doc_id} | path={local_json_path}"
        )

        # Save JSON output file
        document_type = cohere_result.get("structured_output", [])[0].get(
            "document_type"
        )
        
        if not document_type:
            logger.error(f"Document type not found | doc_id={doc.doc_id}")
            update_doc_status(doc, 7)
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
            update_doc_status(doc, 7)
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

        # Mark complete ✅ logs automatically
        update_doc_status(doc, 3)
        logger.info(f"Document processed successfully | doc_id={doc.doc_id}")
        return jsonify({"message": "Document processed successfully", "status": 1}), 200

    except Exception as e:
        # mark failed ✅ logs automatically
        logger.exception(
            f"Document processing failed | doc_id={doc_id} | error={str(e)}"
        )
        update_doc_status(doc, 7)
        return jsonify({"message": "Document processing failed", "status": 0}), 200




import os
import json
from datetime import datetime

def save_json_locally(data: dict, doc_id: str, base_dir="local_json_outputs"):
    """
    Save processed JSON locally in a structured way.
    Example path:
    local_json_outputs/2026-01-13/doc_<doc_id>.json
    """
    date_folder = datetime.utcnow().strftime("%Y-%m-%d")
    output_dir = os.path.join(base_dir, date_folder)
    os.makedirs(output_dir, exist_ok=True)

    file_path = os.path.join(output_dir, f"doc_{doc_id}.json")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return file_path
