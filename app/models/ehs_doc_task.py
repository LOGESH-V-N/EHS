from app.extensions import db

from datetime import datetime
from app import db

class EhsDocumentTask(db.Model):
    __tablename__ = "ehs_document_task"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_id = db.Column(db.Integer, nullable=False)
    task_name = db.Column(db.String(255), nullable=False)
    sub_title = db.Column(db.String(255))
    assign_to = db.Column(db.Integer)
    note = db.Column(db.Text)
    due_date = db.Column(db.Date)
    priority_id = db.Column(db.Integer)
    created_by = db.Column(db.Integer)
    updated_by = db.Column(db.Integer)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
