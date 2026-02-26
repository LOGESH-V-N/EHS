from app.extensions import db
from datetime import datetime

class EhsSyncLog(db.Model):
    __tablename__ = "ehs_sync_log"

    id = db.Column(db.Integer, primary_key=True)
    sync_time = db.Column(db.DateTime, nullable=False)
    created_datetime = db.Column(db.DateTime, default=datetime.now)