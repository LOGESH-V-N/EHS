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
        "med2.txt"     # your actual files
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

def normalize_text(text):
    if not text:
        return ""
    # Convert to lowercase
    text = text.lower()
    # Keep only letters and numbers (remove spaces, punctuation, etc.)
    text = re.sub(r'[^a-z0-9]', '', text)
    return text


def fetch_snomed_code(text):
    try:
        text = normalize_text(text)
        if not text:
            return ""
        response = requests.post(SNOMED_ENDPOINT, json={"search_text": text})
        response.raise_for_status()
        data = response.json()
        results = data.get("body", [])
        #print(f"concept_id:{results}")
        if not results:
            return ""
        # Try exact match first
        for result in results:
            if normalize_text(result.get("term", "")) == text:
                return result.get("ConceptID", "")
        # Fallback: first match
        
        return ""
    
    except Exception as e:
        print(f"❌ SNOMED fetch error for '{text}': {e}")
        return ""
    
def fetch_snomed_code_for_med(med_name,dosage):
    try:
        text = normalize_text(med_name)
        #print(f"scanfromnorm{text}")
        if not text:
            return ""
        response = requests.post(SNOMED_ENDPOINT, json={"search_text": text})
        response.raise_for_status()
        data = response.json()
        results = data.get("body", [])
        #print(f"concept_id:{results}")
        if not results:
            return ""
        # Try exact match first
        med_tex = f"{med_name} {dosage}"
        med_text=normalize_text(med_tex)
        #print(f"scanmedtext{med_text}")
        for result in results:
            
            if normalize_text(result.get("term", "")) == normalize_text(med_text):
                return result.get("ConceptID", "")
            # Fallback: first match
            if normalize_text(result.get("term", "")) == text:
                return result.get("ConceptID", "")
           

          
        return ""
    except Exception as e:
        print(f"❌ SNOMED fetch error for medications '{text}': {e}")
        return ""
    

# new update
def snomed_mapping(cohere_result):
    
        service = (cohere_result.get("structured_output", [])[0])

        overview=service.get("clinical_info",{})
        #print("overview",overview)
        problems=overview.get("problems",[])
        #print("problems",problems)
        for problem in problems:
            problem["snomed_code"] = fetch_snomed_code(problem.get("problem_name"))
        treatment=overview.get("treatment",[])
        for treat in treatment:
            treat["snomed_code"] = fetch_snomed_code(treat.get("treatment_name"))  
        medication_plan=overview.get("Medication_Plan",{})
        start_medication=medication_plan.get("start_medication",[])
        for start in start_medication:
            start["snomed_code"] = fetch_snomed_code(start.get("medication_name"))
        change_medication=medication_plan.get("change_medication",[])
        for change in change_medication:
            change["snomed_code"] = fetch_snomed_code(change.get("medication_name"))
        continue_medication=medication_plan.get("continue_medication",[])
        for continue_ in continue_medication:
            continue_["snomed_code"] = fetch_snomed_code(continue_.get("medication_name"))
        investigations=overview.get("investigations",[])
        for invest in investigations:
            invest["snomed_code"] = fetch_snomed_code(invest.get("investigation_name"))
        diagnosis=overview.get("diagnosis",[])
        for diag in diagnosis:
            diag["snomed_code"] = fetch_snomed_code(diag.get("diagnosis_name"))
        #print("result",cohere_result)
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


