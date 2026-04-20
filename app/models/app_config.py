from app.extensions import db
from datetime import datetime

class AppConfig(db.Model):
    __tablename__ = "app_config"

    id = db.Column(db.Integer, primary_key=True)
    im_id = db.Column(db.Integer, nullable=True)
    active_status = db.Column(db.Integer, nullable=True)
    updated_date = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)