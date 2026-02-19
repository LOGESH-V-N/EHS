from app.extensions import db
from datetime import datetime

class EmailIngestionState(db.Model):
    __tablename__ = "tbl_email_ingestion_state"

    id = db.Column(db.Integer, primary_key=True)
    last_fetched_at = db.Column(db.DateTime, nullable=True)
    total_documents = db.Column(db.Integer)
    config_email_id = db.Column(db.Integer)
