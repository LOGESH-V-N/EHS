import os
import base64
import shutil
import requests
import json
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from pdf2image import convert_from_path
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter
import pandas as pd
import numpy as np
import cv2
import cohere
import re
from mistralai import Mistral
import mimetypes
from app.schemas.prompt_schema import schema
from string import Template
from flask import current_app
from app.utils.document_upload import upload_file_to_s3
from datetime import timedelta
from app.models.ehs_patient import DocumentListSchema
from app.models.ehs_document import Document
from app.services.document_processor import update_doc_status
from app.extensions import db


load_dotenv()

# --- Pricing (USD) from environment ---
COHERE_INPUT_PER_1K_USD  = float(os.getenv("COHERE_INPUT_PER_1K_USD", "0.0"))
COHERE_OUTPUT_PER_1K_USD = float(os.getenv("COHERE_OUTPUT_PER_1K_USD", "0.0"))
MISTRAL_OCR_PER_PAGE_USD = float(os.getenv("MISTRAL_OCR_PER_PAGE_USD", "0.0"))

def _usd(x: float) -> float:
    return round(float(x), 6)

def cost_from_tokens(input_tokens: int, output_tokens: int,
                     input_rate_per_1k: float, output_rate_per_1k: float) -> float:
    it = max(0, int(input_tokens or 0))
    ot = max(0, int(output_tokens or 0))
    return _usd((it / 1000.0) * input_rate_per_1k + (ot / 1000.0) * output_rate_per_1k)

def cost_from_ocr_pages(pages: int, per_page_usd: float) -> float:
    return _usd(max(0, int(pages or 0)) * float(per_page_usd))

API_KEY = os.getenv("MISTRAL_API_KEY")
mistral_client = Mistral(api_key=API_KEY)

COHERE_API_KEY = os.getenv("COHERE_API_KEY")
co = cohere.Client(COHERE_API_KEY)

TEMP_DIR = "temp_process"
OUTPUT_DIR = "output_log"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def resize_and_compress_image(image_path, max_width=1000):
    try:
        img = Image.open(image_path)
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        img.save(image_path, "JPEG", quality=70)
    except Exception as e:
        print(f"Image resize error: {e}")

def process_pdf(pdf_path):
    temp_img_dir = os.path.join(os.path.dirname(pdf_path), "temp_images")
    os.makedirs(temp_img_dir, exist_ok=True)

    images = convert_from_path(pdf_path, dpi=300)
    image_paths = []

    for i, img in enumerate(images):
        # grayscale
        img_gray = img.convert('L')

        # denoise / sharpen
        img_blur = img_gray.filter(ImageFilter.GaussianBlur(radius=0.5))
        img_sharp = img_blur.filter(ImageFilter.UnsharpMask(radius=2.2, percent=163, threshold=3))

        # contrast boost
        img_contrast = ImageEnhance.Contrast(img_sharp).enhance(1.8)

        # adaptive binarization (threshold)
        img_np = np.array(img_contrast)
        if np.var(img_np) < 2000:
            img_np = cv2.adaptiveThreshold(
                img_np,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                25,
                7
            )
        else:
            _, img_np = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        img_processed = Image.fromarray(img_np)

        image_path = os.path.join(temp_img_dir, f"page_{i + 1}.jpg")
        img_processed.save(image_path, "JPEG", quality=95)
        image_paths.append(image_path)

    return image_paths

def clean_latex_like_text(text):
    # Remove inline $...$ math-like wrappers
    text = re.sub(r"\$(.*?)\$", r"\1", text)
    # Replace LaTeX \times with ×
    text = text.replace("\\times", "×")
    return text

def mistral_ocr_image(image_path):
    """
    Runs OCR on a single page image using mistral-ocr-latest.
    We wrap the image as a single-page PDF and send it as data:application/pdf;base64,...
    """
    try:
        img = Image.open(image_path).convert("RGB")

        buffer = BytesIO()
        img.save(buffer, format="PDF")
        pdf_bytes = buffer.getvalue()
        buffer.close()

        base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
        document_url = f"data:application/pdf;base64,{base64_pdf}"

        response = mistral_client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": document_url
            },
            include_image_base64=False
        )

        # Join all page markdown results (usually 1 page here)
        full_text = "\n\n".join(page.markdown for page in response.pages)
        return full_text

    except Exception as e:
        print(f"❌ Mistral OCR failed: {e}")
        return ""

def extract_texts_from_images(image_paths):
    """
    For each page image:
      - resize/compress,
      - OCR with mistral-ocr-latest,
      - light cleanup
    Returns list[str] (one string per page).
    """
    extracted_texts = []
    for image in image_paths:
        resize_and_compress_image(image)
        text = mistral_ocr_image(image)
        text = clean_latex_like_text(text)
        extracted_texts.append(text.strip())
        #print(extracted_texts)
    return extracted_texts

def load_prompt(medical_note):
    """Load the long prompt text and fill schema + note."""
    
    prompt_path = os.path.join(
        current_app.root_path,   # points to /app
        "services",
        "medical_prompt.txt"     # your actual file
    )

    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt file missing at: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = Template(f.read())

    return prompt_template.substitute(schema=schema, medical_note=medical_note)


#############################################
# NEW: token counting helper for Cohere LLM
#############################################
def count_cohere_tokens(text: str) -> int:
    """
    Ask Cohere tokenizer how many tokens this text would use.
    If tokenization fails, return -1 so you can still log.
    """
    try:
        tok = co.tokenize(
            model="command-a-03-2025",
            text=text
        )
        # Cohere's Python SDK returns an object with `tokens`.
        # Each item in `tokens` is a token unit.
        return len(tok.tokens)
    except Exception as e:
        print(f"Tokenize error: {e}")
        return -1


def post_process_with_cohere(medical_note: str) -> dict:
    """
    Send the combined OCR text + extraction instructions to command-a-03-2025.
    Return:
    {
        "model": "command-a-03-2025",
        "input_tokens": <int>,
        "output_tokens": <int>,
        "structured_output": <parsed JSON or {"error": ...}>
    }
    """
    #print(medical_note)
    prompt = load_prompt(medical_note)
    #print(prompt)
    #print(prompt)

    # --- Count input tokens before sending to the model ---
    #input_token_count = count_cohere_tokens(prompt)

    try:
        response = co.chat(
            model="command-a-03-2025", #"command-r-plus-08-2024", "command-a-03-2025"
            message=prompt,
            temperature=0.0,
            max_tokens=4000
        )
        raw_output_text = response.text.strip()

        # Count output tokens
        #output_token_count = count_cohere_tokens(raw_output_text)

        # Pull JSON object from output and wrap in [ ... ]
        match = re.search(r'\{.*\}', raw_output_text, re.DOTALL)
        if match:
            parsed_json = json.loads('[' + match.group(0) + ']')
        else:
            parsed_json = {"error": "No JSON found", "raw": raw_output_text}
        #print (parsed_json)

        return {
            "model": "command-a-03-2025",
            "structured_output": parsed_json
        }

    except Exception as e:
        print(f"Cohere error: {e}")
        return {
            "model": "command-a-03-2025",
            "output_tokens": -1,
            "structured_output": {"error": str(e)}
        }


def save_uploaded_file(uploaded_file):
    temp_path = os.path.join(TEMP_DIR, uploaded_file.filename)
    uploaded_file.save(temp_path)
    return temp_path

def upload_json_data_to_s3(json_data, filename_without_ext="extracted_text"):
    # Convert JSON dictionary to pretty JSON string
    json_str = json.dumps(json_data, indent=4, ensure_ascii=False)

    # Convert JSON string to a BytesIO file-like object
    json_bytes = BytesIO(json_str.encode("utf-8"))

    # Add file extension
    filename = f"{filename_without_ext}.json"

    # Call the REAL S3 uploader
    file_url = upload_file_to_s3(
        file_obj=json_bytes,
        filename=filename
    )

    return file_url

def save_json(text_data, filename_without_ext="extracted_text"):
    filename = f"{filename_without_ext}.json"
    full_path = os.path.join(OUTPUT_DIR, filename)
    with open(full_path, "w", encoding="utf-8") as json_file:
        json.dump(text_data, json_file, indent=4, ensure_ascii=False)
    return filename

def save_to_excel(data: dict, excel_file: str = 'output.xlsx'):
    """
    Store a summary row in Excel so you can audit usage/extraction history.
    Expects `data` to already be a dict (not a list).
    """
    df = pd.DataFrame([data])

    if os.path.exists(excel_file):
        try:
            existing_df = pd.read_excel(excel_file, engine='openpyxl')
            combined_df = pd.concat([existing_df, df], ignore_index=True)
        except Exception as e:
            print(f"Failed to read existing Excel file. Creating new one. Reason: {e}")
            combined_df = df
    else:
        combined_df = df

    combined_df.to_excel(excel_file, index=False, engine='openpyxl')


# ---------------- SNOMED CONFIG ----------------
SNOMED_ENDPOINT = "https://lsruv353zj.execute-api.eu-west-2.amazonaws.com/dev/fetch-snomed-code"

def fetch_snomed_code(text, size=5):
    """
    Fetch SNOMED code from OpenSearch endpoint.
    Returns dict with 'code' and 'term', or empty dict if not found.
    """
    try:
        if not text or not text.strip():
            return {"code": "", "term": ""}
        
        # Send exact text without normalization
        payload = {
            "term": text.strip(),
            "size": size  # Get multiple results to check for exact match
        }
        
        response = requests.post(SNOMED_ENDPOINT, json=payload)
        response.raise_for_status()
        data = response.json()
        results = data.get("body", [])
        
        if not results:
            return {"code": "", "term": ""}
        
        # Try exact match first (case-insensitive)
        search_text_lower = text.strip().lower()
        for result in results:
            result_term = result.get("term", "")
            if result_term.lower() == search_text_lower:
                return {
                    "code": result.get("ConceptID", ""),
                    "term": result_term
                }
        
        # Fallback: return first result
        first_result = results[0]
        return {
            "code": first_result.get("ConceptID", ""),
            "term": first_result.get("term", "")
        }
    
    except Exception as e:
        print(f"❌ SNOMED fetch error for '{text}': {e}")
        return {"code": "", "term": ""}


def fetch_snomed_code_for_med(med_name, dosage, size=5):
    """
    Fetch SNOMED code for medication, trying with dosage first.
    Returns dict with 'code' and 'term'.
    """
    try:
        if not med_name or not med_name.strip():
            return {"code": "", "term": ""}
        
        # First try: medication name + dosage
        if dosage and dosage.strip():
            med_with_dosage = f"{med_name.strip()} {dosage.strip()}"
            payload = {
                "term": med_with_dosage,
                "size": size
            }
            
            response = requests.post(SNOMED_ENDPOINT, json=payload)
            response.raise_for_status()
            data = response.json()
            results = data.get("body", [])
            
            if results:  # If we got results with dosage
                search_text_lower = med_with_dosage.lower()
                
                # Check for exact match
                for result in results:
                    result_term = result.get("term", "")
                    if result_term.lower() == search_text_lower:
                        return {
                            "code": result.get("ConceptID", ""),
                            "term": result_term
                        }
                
                # No exact match but we have results with dosage
                # Return FIRST result from dosage search
                first_result = results[0]
                return {
                    "code": first_result.get("ConceptID", ""),
                    "term": first_result.get("term", "")
                }
        
        # Only search without dosage if:
        # 1. No dosage was provided, OR
        # 2. Search with dosage returned NO results
        payload = {
            "term": med_name.strip(),
            "size": size
        }
        
        response = requests.post(SNOMED_ENDPOINT, json=payload)
        response.raise_for_status()
        data = response.json()
        results = data.get("body", [])
        
        if not results:
            return {"code": "", "term": ""}
        
        # Check for exact match
        search_text_lower = med_name.strip().lower()
        for result in results:
            result_term = result.get("term", "")
            if result_term.lower() == search_text_lower:
                return {
                    "code": result.get("ConceptID", ""),
                    "term": result_term
                }
        
        # Return first result
        first_result = results[0]
        return {
            "code": first_result.get("ConceptID", ""),
            "term": first_result.get("term", "")
        }
    
    except Exception as e:
        print(f"❌ SNOMED fetch error for medication '{med_name}': {e}")
        return {"code": "", "term": ""}


def snomed_mapping(cohere_result):
    """
    Add SNOMED codes and terms to the cohere result structure.
    """
    service = cohere_result.get("structured_output", [])[0]
    overview = service.get("clinical_info", {})
    print("overview", overview)
    
    # Problems
    problems = overview.get("problems", [])
    print("problems", problems)
    for problem in problems:
        snomed_data = fetch_snomed_code(problem.get("problem_name"))
        problem["snomed_code"] = snomed_data["code"]
        problem["snomed_term"] = snomed_data["term"]
    
    # Treatment
    treatment = overview.get("treatment", [])
    for treat in treatment:
        snomed_data = fetch_snomed_code(treat.get("treatment_name"))
        treat["snomed_code"] = snomed_data["code"]
        treat["snomed_term"] = snomed_data["term"]
    
    # Medication Plan
    medication_plan = overview.get("Medication_Plan", {})
    
    # Start medication
    start_medication = medication_plan.get("start_medication", [])
    for start in start_medication:
        snomed_data = fetch_snomed_code_for_med(
            start.get("medication_name"),
            start.get("dosage", "")
        )
        start["snomed_code"] = snomed_data["code"]
        start["snomed_term"] = snomed_data["term"]
    
    # Change medication
    change_medication = medication_plan.get("change_medication", [])
    for change in change_medication:
        snomed_data = fetch_snomed_code_for_med(
            change.get("medication_name"),
            change.get("dosage", "")
        )
        change["snomed_code"] = snomed_data["code"]
        change["snomed_term"] = snomed_data["term"]
    
    # Continue medication
    continue_medication = medication_plan.get("continue_medication", [])
    for continue_ in continue_medication:
        snomed_data = fetch_snomed_code_for_med(
            continue_.get("medication_name"),
            continue_.get("dosage", "")
        )
        continue_["snomed_code"] = snomed_data["code"]
        continue_["snomed_term"] = snomed_data["term"]
    
    # Investigations
    investigations = overview.get("investigations", [])
    for invest in investigations:
        snomed_data = fetch_snomed_code(invest.get("investigation_name"))
        invest["snomed_code"] = snomed_data["code"]
        invest["snomed_term"] = snomed_data["term"]
    
    # Diagnosis
    diagnosis = overview.get("diagnosis", [])
    for diag in diagnosis:
        snomed_data = fetch_snomed_code(diag.get("diagnosis_name"))
        diag["snomed_code"] = snomed_data["code"]
        diag["snomed_term"] = snomed_data["term"]
    
    print("result", cohere_result)
    return cohere_result

 
    
    
def extract_document_type(cohere_result: dict) -> str:
    """
    Extract document type from Cohere result
    """
    # Example – adjust based on your real Cohere response
    return (
        cohere_result.get("document_type")
        or cohere_result.get("doc_type")
        or "UNKNOWN"
    )


def storing_document_info(cohere_result,doc):
    try:
        service = cohere_result.get("structured_output", [])[0]
        document_type=service.get("document_type")
        overview = service.get("Overview",{})
        patient_info=service.get("patient_info",{})
        sender_information=overview.get("sender_information",{})
        letter_issued_dates=overview.get("letter_issued_date",{})
        event_details=overview.get("event_details",{})
        hospital_details=overview.get("hospital_details",{})

        sender_name=sender_information.get("name")
        sender_department=sender_information.get("department")
        letter_issued_date=letter_issued_dates.get("date")
        event_date=event_details.get("event_date")
        hospital_name=hospital_details.get("hospital_name")
        Document.query.filter_by(doc_id=doc.doc_id).update({
            "sender_name": sender_name,
            "sender_department": sender_department,
            "event_date": event_date,
            "letter_date": letter_issued_date,
            "hospital_name": hospital_name,
        })
        db.session.commit()


        
        return True
    except Exception as e:
        print("❌ storing document info error:", e)
        return False




def storing_patient_info(cohere_result,doc):
    try:
        document_type_for_patient = cohere_result.get("structured_output", [])[0]
        if not document_type_for_patient:
            update_doc_status(doc, 7)
            return jsonify({"message": "No document type found","status":0}), 200
  
    
        doc_access=document_type_for_patient.get("document_type")

        patient_info_dict=document_type_for_patient.get("patient_info",{})
        if not patient_info_dict:
            update_doc_status(doc, 7)
        
            return jsonify({"message": "No patient info found","status":0}), 200

        nhs_number=patient_info_dict.get("nhs_number","")
        nhs_number=nhs_number.replace(" ","")
        
        if not nhs_number or nhs_number=="[redacted]":
            nhs_number=None
        full_name=patient_info_dict.get("full_name","")
       
        if not full_name or full_name=="[redacted]":
            full_name=None
        mobile_number=patient_info_dict.get("mobile_number","")
       
        if not mobile_number or mobile_number=="[redacted]":
            mobile_number=None
        patient_tbl_id=DocumentListSchema.query.filter_by(nhs_no=nhs_number).first()
      
        if patient_tbl_id:
            Document.query.filter_by(doc_id=doc.doc_id).update({
                "patient_id": patient_tbl_id.id})
            db.session.commit()


        else:   
            pf=DocumentListSchema(doc_id=doc.doc_id,patient_name=full_name,nhs_no=nhs_number,phone_no=mobile_number)
            db.session.add(pf)
            db.session.commit()
            Document.query.filter_by(doc_id=doc.doc_id).update({
                "patient_id": pf.id})
            db.session.commit()
        return True
    except Exception as e:
        print("❌ storing patient info error:", e)
        return False


def assign_parent_doc_id(new_doc):
    """
    new_doc is ALREADY persisted in DB.
    This function finds duplicates and updates parent_doc_id.
    """

    # 1. Fetch NHS number of new document
    new_patient = (
        db.session.query(DocumentListSchema)
        .filter(DocumentListSchema.id == new_doc.patient_id)
        .first()
    )

    if not new_patient:
        return

    new_nhs_no = new_patient.nhs_no

    # 2. Define 1-year window
    start_date = new_doc.created_at - timedelta(days=365)
   
    end_date = new_doc.created_at
   

    # 3. Find metadata-matched documents within 1 year (excluding itself)
    matched_docs = (
        db.session.query(Document)
        .filter(
            Document.sender_name == new_doc.sender_name,
            Document.hospital_name == new_doc.hospital_name,
            Document.letter_date == new_doc.letter_date,
            Document.event_date == new_doc.event_date,
            Document.doc_type_code == new_doc.doc_type_code,
            Document.doc_id != new_doc.doc_id,  
            Document.delete_status == 0,             # exclude self
            Document.created_at.between(start_date, end_date)  # ⭐ 1-year filter
        )
        .all()
    )

    if not matched_docs:
        return

    # 4. Compare NHS number
    for existing_doc in matched_docs:
        if not existing_doc.patient_id:
            continue

        existing_patient = (
            db.session.query(DocumentListSchema)
            .filter(DocumentListSchema.id == existing_doc.patient_id)
            .first()
        )

        if not existing_patient:
            continue

        if existing_patient.nhs_no == new_nhs_no:
            # 5. Assign ROOT parent (star pattern)
            new_doc.parent_doc_id = (
                existing_doc.parent_doc_id or existing_doc.doc_id
            )

            db.session.commit()
            return


