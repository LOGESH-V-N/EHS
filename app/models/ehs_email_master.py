from app.extensions import db
from datetime import datetime

class EhsEmailMaster(db.Model):
    __tablename__ = "ehs_app_config"

    id = db.Column(db.Integer, primary_key=True)
    sync_email = db.Column(db.String(255), nullable=False)
    sync_password = db.Column(db.String(255), nullable=False)
    sync_server = db.Column(db.String(255), nullable=False)
    status_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)




