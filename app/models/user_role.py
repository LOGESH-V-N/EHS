from app.extensions import db

class UserRole(db.Model):
    __tablename__ = 'tbl_user_roles'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    role_id = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime,
                           server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
