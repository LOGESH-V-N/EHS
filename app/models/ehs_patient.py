from app.extensions import db
from datetime import datetime
 
class DocumentListSchema(db.Model):
    __tablename__ = "ehs_patient"
 
    id = db.Column(db.Integer, primary_key=True)
    doc_id = db.Column(db.Integer, nullable=False)
    patient_name = db.Column(db.String(255))
    nhs_no = db.Column(db.String(50), index=True)
    phone_no = db.Column(db.String(50))