from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.document import DocTypeMaster
from flask_jwt_extended import jwt_required

doc_type_bp= Blueprint("doc_type_bp", __name__)

@doc_type_bp.route("/", methods=["POST"])
#@jwt_required()
def add_doc_type():
    data = request.json
    name = data.get("doc_type_name")
    code = data.get("doc_type_code")

    if DocTypeMaster.query.filter_by(doc_type_name=name).first():
        return jsonify({"status": 0, "message": "Document type already exists"}), 400

    new_doc = DocTypeMaster(
        doc_type_name=name,
        doc_type_code=code
    )

    db.session.add(new_doc)
    db.session.commit()

    return jsonify({"status": 1, "message": "Document type added successfully"})

@doc_type_bp.route("/", methods=["GET"])
#@jwt_required()
def get_doc_types():
    docs = DocTypeMaster.query.filter_by(del_status=0).all()

    output = []
    for d in docs:
        output.append({
            "doc_type_id": d.doc_type_id,
            "doc_type_name": d.doc_type_name,
            "doc_type_code": d.doc_type_code,
            "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Active" if d.del_status == 0 else "Deleted"
        })

    return jsonify({"status": 1, "data": output})

@doc_type_bp.route("/", methods=["PUT"])
#@jwt_required()
def update_doc_type():
    data = request.json
    doc_id = data.get("doc_type_id")

    doc = DocTypeMaster.query.get(doc_id)
    if not doc:
        return jsonify({"status": 0, "message": "Document type not found"}), 404

    doc.doc_type_name = data.get("doc_type_name", doc.doc_type_name)
    doc.doc_type_code = data.get("doc_type_code", doc.doc_type_code)

    db.session.commit()

    return jsonify({"status": 1, "message": "Document type updated successfully"})

@doc_type_bp.route("/", methods=["DELETE"])
#@jwt_required()
def delete_doc_type():
    data = request.json
    doc_id = data.get("doc_type_id")

    doc = DocTypeMaster.query.get(doc_id)
    if not doc:
        return jsonify({"status": 0, "message": "Document type not found"}), 404

    doc.del_status = 1
    db.session.commit()

    return jsonify({"status": 1, "message": "Document type deleted successfully"})
