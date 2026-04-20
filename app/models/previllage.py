from app.extensions import db
from datetime import datetime

class ModuleMaster(db.Model):
    __tablename__ = "module_master"

    module_id = db.Column(db.Integer, primary_key=True)
    module_name = db.Column(db.String(200), nullable=False)
    module_code = db.Column(db.String(200), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("module_master.module_id"), nullable=True)
    status = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Self-referencing relationship
    children = db.relationship(
        "ModuleMaster",
        backref=db.backref("parent", remote_side=[module_id]),
        lazy="joined"
    )

    def to_dict(self):
        """Convert to hierarchical dict (used for API response)."""
        return {
            "id": self.module_id,
            "name": self.module_name,
            "children": [child.to_dict() for child in self.children]
        }
