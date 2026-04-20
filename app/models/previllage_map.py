from app.extensions import db

class RolePrivilegeMap(db.Model):
    __tablename__ = "role_privilege_map"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role_id = db.Column(db.Integer, db.ForeignKey("role_masters.id"), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey("module_master.module_id"), nullable=False)
