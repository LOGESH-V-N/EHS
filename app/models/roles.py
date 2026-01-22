from app.extensions import db
from datetime import datetime
from app.utils.date_formatter import format_datetime

 
class RoleMaster(db.Model):
    __tablename__ = "role_masters"
 
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50))
    resource_access = db.Column(db.Integer, default=1)  # 1 = All, 2 = Custom
    description = db.Column(db.String(255))
    status = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_name = db.Column(db.String(100))
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    updated_by_name = db.Column(db.String(100))
   
    def to_dict(self):
        resource_access_label = (
            "All" if self.resource_access == 1
            else "Custom" if self.resource_access == 2
            else "Unknown"
        )
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "resource_access": self.resource_access,
            "resource_access_label": resource_access_label,
            "status": self.status,
            "created_at": format_datetime(self.created_at),
            "updated_at": format_datetime(self.updated_at),
            "created_by_name": self.created_by_name,
            "updated_by_name": self.updated_by_name
        }
 