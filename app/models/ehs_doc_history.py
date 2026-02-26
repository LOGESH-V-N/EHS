from app.extensions import db
from datetime import datetime

class Ehs_Document_History(db.Model):
    __tablename__ = "ehs_document_history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_id = db.Column(db.Integer, nullable=False)
    activity_id = db.Column(db.Integer,nullable=False,comment="1 = AI Generated, 2 = Edited")
    s3_path = db.Column(db.String(500))
    time_stamp = db.Column(db.DateTime, default=datetime.utcnow)
