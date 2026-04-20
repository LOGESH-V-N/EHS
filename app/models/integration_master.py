from app.extensions import db
from datetime import datetime


class IntegrationMaster(db.Model):
    __tablename__ = "integration_master"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=True)
    delete_status = db.Column(db.Integer, nullable=True)
    code=db.Column(db.String(255), nullable=True)
