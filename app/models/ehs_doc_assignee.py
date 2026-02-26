from datetime import datetime
from app import db
 
class EhsDocumentAssignee(db.Model):
    __tablename__ = "ehs_document_assignee"
 
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
 
    assignee_id = db.Column(db.Integer, nullable=False, index=True)
    doc_id = db.Column(db.Integer, nullable=False, index=True)
    priority_id = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
 
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )
 
    created_by = db.Column(db.Integer, nullable=True)
 
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
 
    updated_by = db.Column(db.Integer, nullable=True)
 