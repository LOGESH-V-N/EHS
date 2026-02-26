from app.extensions import db
from datetime import datetime

class DocTypeMaster(db.Model):
    __tablename__ = "doc_type_master"

    doc_type_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_type_name = db.Column(db.String(255), unique=True, nullable=False)
    doc_type_code = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    del_status = db.Column(db.Integer, default=0)
