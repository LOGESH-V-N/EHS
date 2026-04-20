from app.extensions import db
from datetime import datetime

class Ehs_Doc_Priority(db.Model):
    __tablename__ = "ehs_tbl_master_priority"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    code = db.Column(db.String(100))
    description = db.Column(db.String(255))  
    color_code = db.Column(db.String(100))  
    status = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime)