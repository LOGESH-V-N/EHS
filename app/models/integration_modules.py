from app.extensions import db
from datetime import datetime

class IntegrationModules(db.Model):
    __tablename__ = "integration_modules"

    m_id = db.Column(db.Integer, primary_key=True)
    im_id = db.Column(db.Integer, nullable=True)
    module_name = db.Column(db.String(255), nullable=True)
    display_name = db.Column(db.String(255), nullable=True)
    delete_status = db.Column(db.Integer, nullable=True)