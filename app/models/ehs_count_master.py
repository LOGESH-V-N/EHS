from app.extensions import db
from datetime import datetime

class Count(db.Model):
    __tablename__ = "ehs_count_master"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    code = db.Column(db.String(255))
    description = db.Column(db.String(255))
    color_code = db.Column(db.String(50))
    status = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
