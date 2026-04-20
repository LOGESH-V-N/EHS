from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.ehs_document import Document
from app.models.ehs_patient import DocumentListSchema as PatientModel
from app.models.ehs_log import Log
from app.models.ehs_doc_history import Ehs_Document_History
from app.services.s3_utils import assign_parent_doc_id
from app.utils.privilege_decorator import require_privilege
from datetime import datetime
import re
import boto3
import json
import io
import uuid
from flask import current_app


query_resolution_bp = Blueprint("query_resolution_bp", __name__)


# =============================================================================
# HELPER — Validate NHS Number Format
# =============================================================================

def _validate_nhs_number(nhs_number: str):
    """
    Validates NHS number format.
    Accepts with or without spaces: "485 777 3456" or "4857773456"
    Returns (is_valid: bool, cleaned_number: str)
    cleaned_number is always 10 digits with no spaces.
    """
    cleaned = nhs_number.replace(" ", "").strip()

    if not re.fullmatch(r"\d{10}", cleaned):
        return False, ""

    return True, cleaned


# =============================================================================
# HELPER — Read Patient Data from S3 JSON
# =============================================================================

def _read_patient_data_from_json(doc: Document) -> dict:
    """
    Reads patient_info fields from the already-extracted S3 JSON file.

    This JSON was created during AI processing but patient data was never
    saved to ehs_patient because the document failed at the NHS number check.
    The AI did extract name, DOB, phone, gender correctly — it just could
    not find the NHS number.

    Returns a dict with keys:
        full_name, mobile_number, landline_number,
        date_of_birth, gender, address
    Returns empty dict {} if JSON cannot be read for any reason.
    """
    if not doc.extract_file_url:
        return {}

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
            aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
            region_name=current_app.config["AWS_REGION"]
        )

        bucket = current_app.config["AWS_BUCKET"]
        key = doc.extract_file_url.split(".amazonaws.com/")[1]

        obj = s3.get_object(Bucket=bucket, Key=key)
        json_data = json.loads(obj["Body"].read().decode("utf-8"))

        # Handle both dict wrapper and plain list format
        if isinstance(json_data, dict):
            structured = json_data.get("structured_output", [])
        elif isinstance(json_data, list):
            structured = json_data
        else:
            return {}

        if not structured or len(structured) == 0:
            return {}

        patient_info = structured[0].get("patient_info", {})
        if not patient_info:
            return {}

        def clean(value):
            """Same cleaning logic as storing_patient_info() in s3_utils.py"""
            if not value or str(value).strip() in ["", "[redacted]"]:
                return None
            return str(value).strip()

        return {
            "full_name":       clean(patient_info.get("full_name")),
            "mobile_number":   clean(patient_info.get("mobile_number")),
            "landline_number": clean(patient_info.get("landline_number")),
            "date_of_birth":   clean(patient_info.get("date_of_birth")),
            "gender":          clean(patient_info.get("gender")),
            "address":         clean(patient_info.get("address")),
        }

    except Exception as e:
        print(f"⚠️ _read_patient_data_from_json failed: {e}")
        return {}


# =============================================================================
# HELPER — Read and Store Document Info from S3 JSON
# =============================================================================

def _store_document_info_from_json(doc: Document):
    """
    Reads sender_name, sender_department, hospital_name, event_date,
    letter_date from the already-extracted S3 JSON and saves them
    into the ehs_document table.

    This mirrors storing_document_info() in s3_utils.py but reads from
    the S3 JSON instead of the live cohere_result, because by the time
    we resolve a query document the cohere_result is no longer in memory.

    Only updates fields that are currently NULL on the document.
    Never overwrites a field that already has a value.

    Does NOT commit — the calling function handles the commit.
    """
    if not doc.extract_file_url:
        return

    # If all five fields already have values, nothing to do
    if all([
        doc.sender_name,
        doc.sender_department,
        doc.hospital_name,
        doc.event_date,
        doc.letter_date
    ]):
        return

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
            aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
            region_name=current_app.config["AWS_REGION"]
        )

        bucket = current_app.config["AWS_BUCKET"]
        key = doc.extract_file_url.split(".amazonaws.com/")[1]

        obj = s3.get_object(Bucket=bucket, Key=key)
        json_data = json.loads(obj["Body"].read().decode("utf-8"))

        # Handle both dict wrapper and plain list format
        if isinstance(json_data, dict):
            structured = json_data.get("structured_output", [])
        elif isinstance(json_data, list):
            structured = json_data
        else:
            return

        if not structured or len(structured) == 0:
            return

        service = structured[0]

        # Read exactly the same paths that storing_document_info() reads
        overview            = service.get("Overview", {})
        sender_information  = overview.get("sender_information", {})
        letter_issued_dates = overview.get("letter_issued_date", {})
        event_details       = overview.get("event_details", {})
        hospital_details    = overview.get("hospital_details", {})

        def clean(value):
            if not value or str(value).strip() in ["", "[redacted]"]:
                return None
            return str(value).strip()

        extracted_sender_name       = clean(sender_information.get("name"))
        extracted_sender_department = clean(sender_information.get("department"))
        extracted_letter_date       = clean(letter_issued_dates.get("date"))
        extracted_event_date        = clean(event_details.get("event_date"))
        extracted_hospital_name     = clean(hospital_details.get("hospital_name"))

        # Only update NULL fields — never overwrite existing values
        if not doc.sender_name and extracted_sender_name:
            doc.sender_name = extracted_sender_name

        if not doc.sender_department and extracted_sender_department:
            doc.sender_department = extracted_sender_department

        if not doc.hospital_name and extracted_hospital_name:
            doc.hospital_name = extracted_hospital_name

        if not doc.event_date and extracted_event_date:
            doc.event_date = extracted_event_date

        if not doc.letter_date and extracted_letter_date:
            doc.letter_date = extracted_letter_date

        # Flush only — commit is handled by the calling function
        db.session.flush()

    except Exception as e:
        # Log but never fail the resolution because of this
        print(f"⚠️ _store_document_info_from_json failed (non-critical): {e}")


# =============================================================================
# HELPER — Update NHS Number Inside S3 JSON File
# =============================================================================

def _update_nhs_in_extracted_json(doc: Document, nhs_number_clean: str):
    """
    Updates the nhs_number field inside the extracted JSON file on S3.

    Follows the same versioning pattern as /modify/update-json:
      - Saves the OLD file URL to Ehs_Document_History (activity_id=4)
      - Uploads as a NEW S3 file (does NOT overwrite old file)
      - Updates doc.extract_file_url to point to new file

    activity_id reference:
      1 = AI extraction (original)
      2 = manual JSON edit by reviewer
      3 = redacted PDF
      4 = NHS number correction

    Does NOT commit — the calling function handles the commit.
    """
    if not doc.extract_file_url:
        return

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=current_app.config["AWS_ACCESS_KEY"],
            aws_secret_access_key=current_app.config["AWS_SECRET_KEY"],
            region_name=current_app.config["AWS_REGION"]
        )

        bucket = current_app.config["AWS_BUCKET"]
        old_key = doc.extract_file_url.split(".amazonaws.com/")[1]

        # ── Step 1: Save current URL to history BEFORE changing anything ──
        old_history = Ehs_Document_History(
            doc_id=doc.doc_id,
            activity_id=4,
            s3_path=doc.extract_file_url,
            time_stamp=datetime.utcnow()
        )
        db.session.add(old_history)

        # ── Step 2: Download current JSON ─────────────────────────────────
        obj = s3.get_object(Bucket=bucket, Key=old_key)
        json_data = json.loads(obj["Body"].read().decode("utf-8"))

        # ── Step 3: Update NHS number inside JSON ──────────────────────────
        if isinstance(json_data, dict):
            structured = json_data.get("structured_output", [])
        elif isinstance(json_data, list):
            structured = json_data
        else:
            return

        if structured and len(structured) > 0:
            patient_info = structured[0].get("patient_info", {})
            if patient_info is not None:
                # Format as NHS standard display: XXX XXX XXXX
                formatted_nhs = (
                    f"{nhs_number_clean[:3]} "
                    f"{nhs_number_clean[3:6]} "
                    f"{nhs_number_clean[6:]}"
                )
                patient_info["nhs_number"] = formatted_nhs

        # ── Step 4: Upload as NEW file — never overwrite old file ──────────
        updated_json_str = json.dumps(json_data, indent=4, ensure_ascii=False)
        json_bytes = io.BytesIO(updated_json_str.encode("utf-8"))

        today_date = datetime.utcnow().strftime("%d-%m-%Y")
        original_filename = old_key.split("/")[-1]
        base_name = original_filename.rsplit(".", 1)[0]
        new_filename = f"{uuid.uuid4()}_{base_name}_nhs_corrected.json"
        new_key = (
            f"{current_app.config['AWS_JSON_FOLDER']}"
            f"/{today_date}/{new_filename}"
        )

        s3.upload_fileobj(
            json_bytes,
            bucket,
            new_key,
            ExtraArgs={"ContentType": "application/json"}
        )

        # ── Step 5: Update doc.extract_file_url to point to new file ───────
        new_url = (
            f"https://{bucket}.s3."
            f"{current_app.config['AWS_REGION']}.amazonaws.com/{new_key}"
        )
        doc.extract_file_url = new_url

        # Flush only — commit is handled by the calling function
        db.session.flush()

    except Exception as e:
        print(f"⚠️ _update_nhs_in_extracted_json failed (non-critical): {e}")


# =============================================================================
# ENDPOINT 1 — GET: Fetch Query Document for Resolution Screen
# =============================================================================

@query_resolution_bp.route("/query/get", methods=["POST"])
@require_privilege("USER")
def get_query_document():
    """
    Fetches a Query (status=7) document and returns everything the frontend
    needs to pre-populate the resolution screen form.

    Returns:
    - error_reason: why the document failed (e.g. "NHS number not found")
    - extracted_info: sender, hospital, dates already extracted by AI
    - ai_extracted_patient: patient name, DOB, phone, sex from AI extraction
      — pre-fill the form with these so reviewer only needs to add NHS number
    - patient_linked: whether a patient record is already linked
    - has_extracted_json: whether the S3 JSON exists

    Request:
        { "doc_id": 123 }

    Response:
        {
            "status": 1,
            "data": {
                "doc_id": 123,
                "doc_filename": "letter.pdf",
                "doc_status": 7,
                "error_reason": "NHS number not found",
                "doc_type_code": "Discharge_Summary",
                "extracted_info": { ... },
                "ai_extracted_patient": { ... },
                "patient_linked": false,
                "current_patient": null,
                "has_extracted_json": true
            }
        }
    """
    try:
        data = request.get_json()
        doc_id = data.get("doc_id")

        if not doc_id:
            return jsonify({"status": 0, "message": "doc_id is required"}), 200

        doc = Document.query.filter_by(
            doc_id=doc_id,
            delete_status=0
        ).first()

        if not doc:
            return jsonify({"status": 0, "message": "Document not found"}), 200

        if doc.doc_status != 7:
            return jsonify({
                "status": 0,
                "message": (
                    f"Document is not in Query status. "
                    f"Current status: {doc.doc_status}. "
                    f"Only Query (status 7) documents can be resolved here."
                )
            }), 200

        # Check if patient is already linked
        existing_patient = None
        if doc.patient_id:
            existing_patient = PatientModel.query.filter_by(
                id=doc.patient_id
            ).first()

        # Read AI extracted patient data from S3 JSON to pre-fill the form
        # This data was extracted successfully but never saved to DB
        extracted_patient_data = _read_patient_data_from_json(doc)

        return jsonify({
            "status": 1,
            "message": "Query document fetched successfully",
            "data": {
                "doc_id": doc.doc_id,
                "doc_filename": doc.doc_filename,
                "doc_status": doc.doc_status,
                "error_reason": doc.error_message or "NHS number not found",
                "doc_type_code": doc.doc_type_code,

                # Document-level info already extracted (may be NULL if
                # storing_document_info also never ran)
                "extracted_info": {
                    "sender_name":       doc.sender_name or "",
                    "sender_department": doc.sender_department or "",
                    "hospital_name":     doc.hospital_name or "",
                    "event_date":        doc.event_date or "",
                    "letter_date":       doc.letter_date or "",
                },

                # AI extracted patient data — pre-fill the form with these
                # Reviewer just needs to verify and type the NHS number
                "ai_extracted_patient": {
                    "patient_name": extracted_patient_data.get("full_name") or "",
                    "phone_no": (
                        extracted_patient_data.get("mobile_number")
                        or extracted_patient_data.get("landline_number")
                        or ""
                    ),
                    "dob":    extracted_patient_data.get("date_of_birth") or "",
                    "sex":    extracted_patient_data.get("gender") or "",
                },

                # Whether a patient record is already linked to this document
                "patient_linked": existing_patient is not None,

                # Existing patient details if already linked
                "current_patient": {
                    "patient_name": existing_patient.patient_name or "",
                    "nhs_no":       existing_patient.nhs_no or "",
                    "phone_no":     existing_patient.phone_no or "",
                    "dob":          existing_patient.dob or "",
                    "sex":          existing_patient.sex or "",
                } if existing_patient else None,

                # Whether the extracted JSON exists on S3
                # If true frontend can show the full clinical data panel
                "has_extracted_json": bool(doc.extract_file_url),
            }
        }), 200

    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200


# =============================================================================
# ENDPOINT 2 — POST: Resolve Query Document with Manual NHS Number
# =============================================================================

@query_resolution_bp.route("/resolve", methods=["POST"])
@require_privilege("USER")
def resolve_query_with_nhs():
    """
    Core resolution endpoint.

    Resolves a Query (status 7) document by accepting a manually entered
    NHS number from the reviewer.

    What this does:
    1. Validates the NHS number format (must be exactly 10 digits)
    2. Reads ALL patient data already extracted by AI from S3 JSON
       (name, DOB, phone, sex were extracted but never saved to DB)
    3. Reads document info (sender, hospital, dates) from S3 JSON
       (storing_document_info() also never ran for status 7 documents)
    4. Stores ehs_document fields: sender_name, sender_department,
       hospital_name, event_date, letter_date
    5. Creates patient record in ehs_patient with ALL available data:
       - NHS number from reviewer
       - name, DOB, phone, sex from AI extraction (or reviewer override)
    6. Links document.patient_id to the patient record
    7. Updates NHS number inside the S3 JSON file (new versioned file)
    8. Runs assign_parent_doc_id() to link related documents
    9. Moves document from status 7 → status 3 (Processed)
    10. Logs the status change

    Request:
    {
        "doc_id": 123,
        "nhs_number": "485 777 3456",   ← REQUIRED: reviewer manually typed
        "patient_name": "John Smith",   ← OPTIONAL: overrides AI extraction
        "phone_no": "07700900123",      ← OPTIONAL: overrides AI extraction
        "dob": "15/06/1972",            ← OPTIONAL: overrides AI extraction
        "sex": "Male"                   ← OPTIONAL: overrides AI extraction
    }

    Response:
    {
        "status": 1,
        "message": "Query resolved successfully...",
        "data": {
            "doc_id": 123,
            "nhs_number_saved": "4857773456",
            "patient_id": 45,
            "new_doc_status": 3,
            "patient_was_existing": false,
            "patient_data_saved": { ... },
            "document_info_saved": { ... }
        }
    }
    """
    try:
        data = request.get_json()
        doc_id               = data.get("doc_id")
        nhs_number_raw       = data.get("nhs_number", "").strip()
        patient_name_override= data.get("patient_name", "").strip()
        phone_no_override    = data.get("phone_no", "").strip()
        dob_override         = data.get("dob", "").strip()
        sex_override         = data.get("sex", "").strip()

        # ── Validation ────────────────────────────────────────────────────
        if not doc_id:
            return jsonify({"status": 0, "message": "doc_id is required"}), 200

        if not nhs_number_raw:
            return jsonify({"status": 0, "message": "nhs_number is required"}), 200

        is_valid, nhs_number_clean = _validate_nhs_number(nhs_number_raw)
        if not is_valid:
            return jsonify({
                "status": 0,
                "message": (
                    "Invalid NHS number format. "
                    "Must be exactly 10 digits (e.g. 485 777 3456)"
                )
            }), 200

        # ── Fetch document ────────────────────────────────────────────────
        doc = Document.query.filter_by(
            doc_id=doc_id,
            delete_status=0
        ).first()

        if not doc:
            return jsonify({"status": 0, "message": "Document not found"}), 200

        if doc.doc_status != 7:
            return jsonify({
                "status": 0,
                "message": (
                    f"Document is not in Query status. "
                    f"Current status: {doc.doc_status}. "
                    f"Only Query documents can be resolved this way."
                )
            }), 200

        # ── STEP 1: Read extracted patient data from S3 JSON ──────────────
        # The AI extracted all this data correctly. It was never saved to DB
        # because the function exited early when NHS number was missing.
        extracted_patient_data = _read_patient_data_from_json(doc)

        # ── STEP 2: Read and store document info from S3 JSON ─────────────
        # sender_name, sender_department, hospital_name, event_date,
        # letter_date were also never saved for the same reason.
        # This fills those columns on ehs_document now.
        _store_document_info_from_json(doc)

        # ── STEP 3: Build final patient data ──────────────────────────────
        # Priority: reviewer input > AI extracted data > None
        # NHS number always comes from reviewer only — never from AI
        final_patient_name = (
            patient_name_override
            or extracted_patient_data.get("full_name")
            or None
        )
        final_phone_no = (
            phone_no_override
            or extracted_patient_data.get("mobile_number")
            or extracted_patient_data.get("landline_number")
            or None
        )
        final_dob = (
            dob_override
            or extracted_patient_data.get("date_of_birth")
            or None
        )
        final_sex = (
            sex_override
            or extracted_patient_data.get("gender")
            or None
        )

        # ── STEP 4: Check if patient with this NHS number already exists ───
        existing_patient = PatientModel.query.filter_by(
            nhs_no=nhs_number_clean
        ).first()

        if existing_patient:
            # Patient already exists in ehs_patient with this NHS number
            # This means the same patient has another document already processed
            # Just link this document to the existing patient record
            # Only update empty fields — never overwrite existing data
            if not existing_patient.patient_name and final_patient_name:
                existing_patient.patient_name = final_patient_name
            if not existing_patient.phone_no and final_phone_no:
                existing_patient.phone_no = final_phone_no
            if not existing_patient.dob and final_dob:
                existing_patient.dob = final_dob
            if not existing_patient.sex and final_sex:
                existing_patient.sex = final_sex

            db.session.flush()
            doc.patient_id = existing_patient.id
            db.session.flush()

        else:
            # No existing patient with this NHS number
            # Create a brand new patient record with all available data
            new_patient = PatientModel(
                doc_id=doc_id,
                patient_name=final_patient_name,
                nhs_no=nhs_number_clean,
                phone_no=final_phone_no,
                dob=final_dob,
                sex=final_sex
            )
            db.session.add(new_patient)
            db.session.flush()  # flush to get new_patient.id before commit

            doc.patient_id = new_patient.id
            db.session.flush()

        # ── STEP 5: Update NHS number in S3 JSON ──────────────────────────
        # Creates a new versioned JSON file with the correct NHS number
        # Saves old file URL to Ehs_Document_History (activity_id=4)
        # Updates doc.extract_file_url to new file
        _update_nhs_in_extracted_json(doc, nhs_number_clean)

        # ── STEP 6: Link related documents for same patient ───────────────
        # Same logic as normal processing pipeline
        # Finds other documents from same sender+hospital+date combination
        # and links them via parent_doc_id
        try:
            assign_parent_doc_id(doc)
        except Exception as e:
            # Never fail the resolution because of parent linking error
            print(f"⚠️ assign_parent_doc_id failed (non-critical): {e}")

        # ── STEP 7: Move document from status 7 → status 3 (Processed) ────
        doc.doc_status = 3
        doc.error_message = None        # clear the error message
        doc.updated_at = datetime.utcnow()
        db.session.flush()

        # ── STEP 8: Log the status change ─────────────────────────────────
        log = Log(
            doc_id=doc_id,
            doc_status=3,
            datatime=datetime.utcnow()
        )
        db.session.add(log)

        # ── STEP 9: Single commit for everything ──────────────────────────
        db.session.commit()

        return jsonify({
            "status": 1,
            "message": (
                "Query resolved successfully. "
                "Document has been moved to Processed status."
            ),
            "data": {
                "doc_id": doc_id,
                "nhs_number_saved": nhs_number_clean,
                "patient_id": doc.patient_id,
                "new_doc_status": 3,
                "patient_was_existing": existing_patient is not None,

                # Confirm exactly what was saved in ehs_patient
                "patient_data_saved": {
                    "patient_name": final_patient_name,
                    "phone_no":     final_phone_no,
                    "dob":          final_dob,
                    "sex":          final_sex,
                    "nhs_no":       nhs_number_clean,
                    "source":       "ai_extracted + reviewer_nhs"
                },

                # Confirm what was saved in ehs_document
                "document_info_saved": {
                    "sender_name":       doc.sender_name,
                    "sender_department": doc.sender_department,
                    "hospital_name":     doc.hospital_name,
                    "event_date":        doc.event_date,
                    "letter_date":       doc.letter_date,
                }
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 0, "message": str(e)}), 200


# =============================================================================
# ENDPOINT 3 — POST: Update NHS Number on Already Processed Document
# =============================================================================

@query_resolution_bp.route("/query/update_nhs", methods=["POST"])
@require_privilege("USER")
def update_nhs_number():
    """
    Corrects the NHS number on an already processed document
    (status 3, 4, 5) where the NHS number extracted by AI was wrong.

    Does NOT change document status — only corrects the NHS number on
    the linked patient record and updates the S3 JSON file.

    Use case: Document was fully processed, but the AI extracted the
    wrong NHS number. Reviewer wants to correct it without reprocessing.

    If the new NHS number belongs to a different existing patient,
    this document is re-linked to that patient.

    Request:
    {
        "doc_id": 123,
        "nhs_number": "485 777 3456"
    }

    Response:
    {
        "status": 1,
        "data": {
            "doc_id": 123,
            "nhs_number_saved": "4857773456"
        }
    }
    """
    try:
        data = request.get_json()
        doc_id         = data.get("doc_id")
        nhs_number_raw = data.get("nhs_number", "").strip()

        if not doc_id or not nhs_number_raw:
            return jsonify({
                "status": 0,
                "message": "doc_id and nhs_number are both required"
            }), 200

        is_valid, nhs_number_clean = _validate_nhs_number(nhs_number_raw)
        if not is_valid:
            return jsonify({
                "status": 0,
                "message": (
                    "Invalid NHS number. "
                    "Must be exactly 10 digits (e.g. 485 777 3456)"
                )
            }), 200

        doc = Document.query.filter_by(
            doc_id=doc_id,
            delete_status=0
        ).first()

        if not doc:
            return jsonify({"status": 0, "message": "Document not found"}), 200

        # This endpoint is for already-processed documents only
        # For Query documents use /query/resolve instead
        if doc.doc_status == 7:
            return jsonify({
                "status": 0,
                "message": (
                    "This document is in Query status. "
                    "Use /query/resolve to resolve it properly."
                )
            }), 200

        if not doc.patient_id:
            return jsonify({
                "status": 0,
                "message": (
                    "No patient is linked to this document. "
                    "Use /query/resolve instead."
                )
            }), 200

        patient = PatientModel.query.filter_by(id=doc.patient_id).first()
        if not patient:
            return jsonify({
                "status": 0,
                "message": "Patient record not found for this document."
            }), 200

        # Check if another patient already has this NHS number
        conflicting_patient = PatientModel.query.filter_by(
            nhs_no=nhs_number_clean
        ).first()

        if conflicting_patient and conflicting_patient.id != patient.id:
            # A different patient record already owns this NHS number
            # Re-link this document to that existing patient
            doc.patient_id = conflicting_patient.id
            db.session.flush()
        else:
            # Update NHS number on the current linked patient record
            patient.nhs_no = nhs_number_clean
            db.session.flush()

        # Update S3 JSON with corrected NHS number (versioned, non-destructive)
        _update_nhs_in_extracted_json(doc, nhs_number_clean)

        doc.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            "status": 1,
            "message": "NHS number updated successfully",
            "data": {
                "doc_id": doc_id,
                "nhs_number_saved": nhs_number_clean,
                "patient_id": doc.patient_id,
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 0, "message": str(e)}), 200