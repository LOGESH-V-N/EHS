from app.extensions import db
from datetime import datetime

class Document(db.Model):
    __tablename__ = "ehs_document"

    doc_id = db.Column(db.Integer, primary_key=True)
    doc_type_code = db.Column(db.String(40))
    doc_filename = db.Column(db.String(300))
    doc_file_path = db.Column(db.String(300))
    extract_file_url = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    doc_status = db.Column(db.Integer, default=1)
    delete_status = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime)
    assign_to = db.Column(db.Integer)
    assigned_date = db.Column(db.DateTime)
    error_message = db.Column(db.String(300))

def get_pending_documents():
    return Document.query.filter_by(doc_status=1, delete_status=0).all()
