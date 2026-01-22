from app.extensions import db
from datetime import datetime
#from app.models.log import Log

class Log(db.Model):
    __tablename__ = "ehs_document_log"

    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_id = db.Column(db.Integer, nullable=False)
    doc_status = db.Column(db.String(100), nullable=False)
    datatime = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __init__(self, doc_id, doc_status, datatime):
        self.doc_id = doc_id
        self.doc_status = doc_status
        self.datatime = datatime



