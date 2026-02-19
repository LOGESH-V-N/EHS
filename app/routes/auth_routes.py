from flask import Blueprint, request, jsonify
from app.models.user import User
from app.extensions import db
from app.utils.email import send_email
from werkzeug.security import check_password_hash
from flask_jwt_extended import create_access_token
import json
from datetime import timedelta
from werkzeug.security import generate_password_hash
import random
import datetime
from app.models.roles import RoleMaster
from app.models.previllage import ModuleMaster
from app.models.previllage_map import RolePrivilegeMap
from app.models.user_role import UserRole
import jwt, datetime

auth_bp = Blueprint("auth_bp", __name__)

JWT_SECRET = "MY_JWT_SECRET_KEY_123"
JWT_ALGO = "HS256"


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"status": 0, "message": "Email and password required"}), 200

    # Fetch user by email
    user = User.query.filter_by(email_id=email).first()
    if not user or not user.check_password(password):
        return jsonify({"status": 0, "message": "Invalid email or password"}),  200

    # ------------------------------------------------------
    # 1️⃣ Get all roles of this user
    # ------------------------------------------------------
    user_roles = UserRole.query.filter_by(user_id=user.uid).first()
    if not user_roles:
        return jsonify({"status": 0, "message": "No roles assigned to user"}), 200

    

    # ------------------------------------------------------
    # 2️⃣ Get role details
    # ------------------------------------------------------
    roles = RoleMaster.query.filter_by(id=user_roles.role_id).first()
    if not roles:
        return jsonify({"status": 0, "message": "Roles not found"}), 200

    # ------------------------------------------------------
    # 3️⃣ Collect privileges from all roles
    # ------------------------------------------------------
    privileges = set()
  # default full access if any role is type 1

    
    if roles.resource_access == 1:
        resource_access = 1  # at least one role has full access
    else:
            # Get modules assigned to this role
        
        resource_access = 2
        role_privs = RolePrivilegeMap.query.filter_by(role_id=roles.id).all()
        module_ids = [rp.module_id for rp in role_privs]
        modules = ModuleMaster.query.filter(ModuleMaster.module_id.in_(module_ids)).all()
        for m in modules:
            privileges.add(m.module_code)

    privileges = list(privileges)  # convert set to list

    # ------------------------------------------------------
    # 4️⃣ Build JWT payload
    # ------------------------------------------------------
    payload = {
        "uid": user.uid,
        "email": user.email_id,
        "display_name": user.name,
        "user_type":resource_access,
        "rules": {
            "resource_access": resource_access,
            "privileges": privileges
        },
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

    return jsonify({
        "status": 1,
        "message": "Login successful",
        "resource_access": resource_access,
        "user_type" : resource_access,
        "token": token,
        "rules": payload["rules"]
    }), 200
# -----------------------------
# Forgot Password – Send OTP
# -----------------------------
@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"status": 0, "message": "Email is required"}), 200

    # Check if user exists
    user = User.query.filter_by(email_id=email).first()

    if not user:
        return jsonify({"status": 0, "message": "Email not found"}), 200

    # Generate 6-digit OTP
    otp = random.randint(100000, 999999)

    # Save OTP + expiry time
    user.otp = otp
    user.otp_expiry = datetime.datetime.now() + timedelta(minutes=10)   # OTP valid for 10 minutes
    user.otp_verified = 0                                      # Reset verification flag
    db.session.commit()

    # Send email
    email_sent = send_email(email, otp)
    if not email_sent:
        return jsonify({"status": 0, "message": "Failed to send OTP"}), 200

    return jsonify({
        "status": 1,
        "id": user.uid,
        "message": "OTP sent to your email address"
    }), 200

@auth_bp.route('/validate-otp', methods=['POST'])
def validate_otp():
    data = request.get_json()

    email = data.get("email")
    user_id = data.get("user_id")

    if not email or not user_id:
        return jsonify({"status": 0, "message": "Email and user_id are required"}), 200

    # Combine OTP digits
    otp_digits = [data.get(f"otp{i}") for i in range(1, 7)]
    if None in otp_digits:
        return jsonify({"status": 0, "message": "Invalid OTP format"}), 200

    input_otp = int("".join(otp_digits))

    # Fetch user
    user = User.query.filter_by(uid=user_id, email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    # Check expiry
    if not user.otp_expiry or datetime.datetime.now() > user.otp_expiry:
        return jsonify({"status": 0, "message": "OTP expired"}), 200

    # Check OTP match
    if user.otp != input_otp:
        return jsonify({"status": 0, "message": "Invalid OTP"}), 200

    # Mark OTP as verified
    user.otp_verified = 1
    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "OTP was verified"
    }), 200

@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    data = request.get_json()
    email = data.get("email")
    user_id = data.get("user_id")

    if not email or not user_id:
        return jsonify({"status": 0, "message": "Email and user_id are required"}), 200

    # Fetch user
    user = User.query.filter_by(uid=user_id, email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    # Generate new OTP
    otp = random.randint(100000, 999999)

    user.otp = otp
    user.otp_expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)
    user.otp_verified = 0
    db.session.commit()

    # Send email
    email_sent = send_email(email, otp)
    if not email_sent:
        return jsonify({"status": 0, "message": "Failed to send OTP"}), 200

    return jsonify({
        "status": 1,
        "message": "OTP resent successfully"
    }), 200


@auth_bp.route('/set-new-password', methods=['POST'])
def set_new_password():
    data = request.get_json()
 
    username = data.get("user_name")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")
    email = data.get("email")
    user_id = data.get("user_id")
 
    # Validate required fields
    if not new_password or not confirm_password or not email or not user_id:
        return jsonify({"status": 0, "message": "All fields are required"}), 200
 
    # Password match check
    if new_password != confirm_password:
        return jsonify({"status": 0, "message": "Passwords do not match"}), 200
 
    # Fetch user
    user = User.query.filter_by(uid=user_id, email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200
 
    # Check OTP verification
    if user.otp_verified != 1:
        return jsonify({"status": 0, "message": "OTP not verified"}), 200
 
    # Update password (hashed)
    user.set_password(new_password)
 
    # Reset OTP fields
    user.otp = None
    user.otp_expiry = None
    user.otp_verified = 0
 
    db.session.commit()
 
    return jsonify({
        "status": 1,
        "message": "Password has been changed successfully."
    }), 200


@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    data = request.get_json()
    user_id = data.get("user_id")
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")
 
    user = User.query.filter_by(uid=user_id).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200
    if not user.check_password(old_password):
        return jsonify({"status": 0, "message": "Old password is incorrect"}), 200
    if new_password != confirm_password:
        return jsonify({"status": 0, "message": "Passwords do not match"}), 200
    user.set_password(new_password)
    db.session.commit()
    return jsonify({"status": 1, "message": "Password has been changed successfully."}), 200
 
 