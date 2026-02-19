from flask import Blueprint, request, jsonify, current_app
from app.models.user import User
from app.extensions import db
from app.utils.email import send_email
from datetime import timedelta
import random
import datetime
from app.models.roles import RoleMaster
from app.models.previllage import ModuleMaster
from app.models.previllage_map import RolePrivilegeMap
from app.models.user_role import UserRole
import jwt


auth_bp = Blueprint("auth_bp", __name__)

JWT_SECRET = "MY_JWT_SECRET_KEY_123"
JWT_ALGO = "HS256"


def _utcnow():
    return datetime.datetime.utcnow()


def _is_locked(user):
    return user.status == 1


def _build_jwt_payload(user, resource_access, privileges):
    issued_at = _utcnow()
    session_timeout_minutes = current_app.config["SESSION_IDLE_TIMEOUT_MINUTES"]

    payload = {
        "uid": user.uid,
        "email": user.email_id,
        "display_name": user.name,
        "user_type": resource_access,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=session_timeout_minutes),
        "rules": {
            "resource_access": resource_access,
            "privileges": privileges,
        },
    }
    return payload


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    email = (data.get("email") or "").strip()
    password = data.get("password")

    if not email or not password:
        return jsonify({"status": 0, "message": "Email and password required"}), 200

    user = User.query.filter_by(email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "Invalid email or password"}), 200

    if _is_locked(user):
        return jsonify({
            "status": 0,
            "message": "Account is locked/inactive. Please contact admin to activate your account.",
        }), 200

    max_login_attempts = current_app.config["LOGIN_MAX_FAILED_ATTEMPTS"]
    if not user.check_password(password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= max_login_attempts:
            user.status = 1
            db.session.commit()
            return jsonify({
                "status": 0,
                "message": "Account locked due to multiple failed login attempts. Please contact admin.",
            }), 200

        db.session.commit()
        remaining_attempts = max_login_attempts - user.failed_login_attempts
        return jsonify({
            "status": 0,
            "message": f"Invalid email or password. {remaining_attempts} attempt(s) remaining before lockout.",
        }), 200

    user.failed_login_attempts = 0
    user.last_login_at = _utcnow()

    user_roles = UserRole.query.filter_by(user_id=user.uid).first()
    if not user_roles:
        db.session.commit()
        return jsonify({"status": 0, "message": "No roles assigned to user"}), 200

    roles = RoleMaster.query.filter_by(id=user_roles.role_id).first()
    if not roles:
        db.session.commit()
        return jsonify({"status": 0, "message": "Roles not found"}), 200

    privileges = set()
    if roles.resource_access == 1:
        resource_access = 1
    else:
        resource_access = 2
        role_privs = RolePrivilegeMap.query.filter_by(role_id=roles.id).all()
        module_ids = [rp.module_id for rp in role_privs]
        if module_ids:
            modules = ModuleMaster.query.filter(ModuleMaster.module_id.in_(module_ids)).all()
            for module in modules:
                privileges.add(module.module_code)

    privileges = list(privileges)
    payload = _build_jwt_payload(user, resource_access, privileges)
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "Login successful",
        "resource_access": resource_access,
        "user_type": resource_access,
        "token": token,
        "rules": payload["rules"],
    }), 200


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()

    if not email:
        return jsonify({"status": 0, "message": "Email is required"}), 200

    user = User.query.filter_by(email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "Email not found"}), 200

    if _is_locked(user):
        return jsonify({
            "status": 0,
            "message": "Account is locked/inactive. Please contact admin.",
        }), 200

    otp = random.randint(100000, 999999)
    user.otp = otp
    user.otp_expiry = _utcnow() + timedelta(minutes=10)
    user.otp_verified = 0
    user.otp_failed_attempts = 0
    user.otp_resend_locked_until = _utcnow() + timedelta(
        seconds=current_app.config["OTP_RESEND_COOLDOWN_SECONDS"]
    )
    db.session.commit()

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
    data = request.get_json() or {}

    email = (data.get("email") or "").strip()
    user_id = data.get("user_id")

    if not email or not user_id:
        return jsonify({"status": 0, "message": "Email and user_id are required"}), 200

    otp_digits = [data.get(f"otp{i}") for i in range(1, 7)]
    if None in otp_digits or any(not str(d).isdigit() for d in otp_digits):
        return jsonify({"status": 0, "message": "Invalid OTP format"}), 200

    input_otp = int("".join(str(d) for d in otp_digits))

    user = User.query.filter_by(uid=user_id, email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    if not user.otp_expiry or _utcnow() > user.otp_expiry:
        return jsonify({"status": 0, "message": "OTP expired"}), 200

    max_otp_attempts = current_app.config["OTP_MAX_FAILED_ATTEMPTS"]
    if user.otp != input_otp:
        user.otp_failed_attempts = (user.otp_failed_attempts or 0) + 1
        if user.otp_failed_attempts >= max_otp_attempts:
            user.status = 1
            db.session.commit()
            return jsonify({
                "status": 0,
                "message": "Account locked due to multiple invalid OTP attempts. Please contact admin.",
            }), 200

        db.session.commit()
        remaining_attempts = max_otp_attempts - user.otp_failed_attempts
        return jsonify({
            "status": 0,
            "message": f"Invalid OTP. {remaining_attempts} attempt(s) remaining.",
        }), 200

    user.otp_verified = 1
    user.otp_failed_attempts = 0
    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "OTP was verified"
    }), 200


@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    user_id = data.get("user_id")

    if not email or not user_id:
        return jsonify({"status": 0, "message": "Email and user_id are required"}), 200

    user = User.query.filter_by(uid=user_id, email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    if _is_locked(user):
        return jsonify({
            "status": 0,
            "message": "Account is locked/inactive. Please contact admin.",
        }), 200

    now = _utcnow()
    if user.otp_resend_locked_until and now < user.otp_resend_locked_until:
        retry_after = int((user.otp_resend_locked_until - now).total_seconds())
        return jsonify({
            "status": 0,
            "message": f"Please wait {retry_after} seconds before requesting a new OTP.",
        }), 200

    otp = random.randint(100000, 999999)
    user.otp = otp
    user.otp_expiry = now + timedelta(minutes=10)
    user.otp_verified = 0
    user.otp_failed_attempts = 0
    user.otp_resend_locked_until = now + timedelta(
        seconds=current_app.config["OTP_RESEND_COOLDOWN_SECONDS"]
    )
    db.session.commit()

    email_sent = send_email(email, otp)
    if not email_sent:
        return jsonify({"status": 0, "message": "Failed to send OTP"}), 200

    return jsonify({
        "status": 1,
        "message": "OTP resent successfully"
    }), 200


@auth_bp.route('/set-new-password', methods=['POST'])
def set_new_password():
    data = request.get_json() or {}

    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")
    email = (data.get("email") or "").strip()
    user_id = data.get("user_id")

    if not new_password or not confirm_password or not email or not user_id:
        return jsonify({"status": 0, "message": "All fields are required"}), 200

    if new_password != confirm_password:
        return jsonify({"status": 0, "message": "Passwords do not match"}), 200

    user = User.query.filter_by(uid=user_id, email_id=email).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    if user.otp_verified != 1:
        return jsonify({"status": 0, "message": "OTP not verified"}), 200

    user.set_password(new_password)
    user.otp = None
    user.otp_expiry = None
    user.otp_verified = 0
    user.otp_failed_attempts = 0
    user.otp_resend_locked_until = None

    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "Password has been changed successfully."
    }), 200


@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    if not user_id or not old_password or not new_password or not confirm_password:
        return jsonify({"status": 0, "message": "All fields are required"}), 200

    user = User.query.filter_by(uid=user_id).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    if not user.check_password(old_password):
        return jsonify({"status": 0, "message": "Old password is incorrect. Please enter the correct password."}), 200

    if new_password != confirm_password:
        return jsonify({"status": 0, "message": "Passwords do not match"}), 200

    if old_password == new_password:
        return jsonify({"status": 0, "message": "New password must be different from old password"}), 200

    user.set_password(new_password)
    db.session.commit()
    return jsonify({"status": 1, "message": "Password has been changed successfully."}), 200
