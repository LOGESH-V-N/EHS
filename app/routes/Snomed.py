import requests
from flask import Blueprint, request, jsonify
from app.services.s3_utils import SNOMED_ENDPOINT, normalize_text


snomed_bp = Blueprint("snomed_bp", __name__)

AWS_URL = "https://v5d4pymvi9.execute-api.eu-west-2.amazonaws.com/fetch_term/snomed"

@snomed_bp.route("/get-snomed-details", methods=["POST"])
def get_snomed_details():
    try:
        payload = request.get_json()

        if not payload or "conceptid" not in payload:
            return jsonify({
                "status": 0,
                "message": "conceptid is required"
            }), 200

        concept_id = payload["conceptid"]

        # Call AWS GET API
        aws_response = requests.get(AWS_URL, params={"concept_id": concept_id})

        if aws_response.status_code != 200:
            return jsonify({
                "status": 0,
                "message": "invalid conceptid"
            }), 200

        # AWS returns a LIST → extract first item
        aws_data = aws_response.json()

        if isinstance(aws_data, list) and len(aws_data) > 0:
            aws_data = aws_data   # take first element

        return jsonify({
            "status": 1,
            "message": "Fetched SNOMED details",
            "data": aws_data  # contains ConceptID + term
        }), 200

    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 500


@snomed_bp.route("/search-med", methods=["POST"])
def search_medication():
    try:
        data= request.get_json()
        text =  data.get("search_text")

        if not text:
            return jsonify({
                "status": 0,
                "message": "search_text is required"
            }), 200

        search_text = normalize_text(text)
        print(search_text)

        # Call AWS GET API
        aws_response = requests.post(SNOMED_ENDPOINT, json={"search_text": search_text})
        aws_response.raise_for_status()
        data = aws_response.json()
        results = data.get("body", [])

        if aws_response.status_code != 200:
            return jsonify({
                "status": 0,
                "message": "invalid search_text"
            }), 200

        # AWS returns a LIST → extract first item
        return jsonify({
            "status": 1,
            "message": "Fetched SNOMED details",
            "data": results  # contains ConceptID + term
        }), 200

    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200