from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = 'user_master'
    uid = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    middle_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(120))
    email_id = db.Column(db.String(120), unique=True)
    address = db.Column(db.String(255))
    phone_no = db.Column(db.String(10))
    user_role = db.Column(db.Integer)
    delete_status = db.Column(db.Integer, default=0)
    status = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_by = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=datetime.now)
    user_profile_img = db.Column(db.String(255))
    otp = db.Column(db.Integer)
    otp_expiry = db.Column(db.DateTime)
    otp_verified = db.Column(db.Integer, default=0)


    def set_password(self, password):
        self.password = generate_password_hash(password)
   
    def check_password(self, password):
        return check_password_hash(self.password, password)