from app.models.user import User
from app.models.user_role import UserRole
from app.models.roles import RoleMaster
from flask import Blueprint, request, jsonify
from datetime import datetime
from app.extensions import db
from app.utils.privilege_decorator import require_privilege


profile_bp = Blueprint("profile_bp", __name__)

@profile_bp.route("/view", methods=["POST"])
@require_privilege("USER")
def view_profile():
    try:
        user_id = request.json.get("user_id")
        user = User.query.filter_by(uid=user_id).first()
        user_roles = UserRole.query.filter_by(user_id=user_id).first()

        # Extract role IDs
        role_ids = user_roles.role_id

        # Fetch role names
        roles = RoleMaster.query.filter_by(id=role_ids).first()
        role_names = roles.name
        if not user:
            return jsonify({"status": 0, "message": "User not found"}), 200
        return jsonify({"status": 1, "message": "User found", "data":{
            "user_id": user.uid,
            "first_name": user.first_name,
            "middle_name": user.middle_name,
            "last_name": user.last_name,
            "phone_no": user.phone_no,
            "email_id": user.email_id,
            "status": user.status,
            "role_id": role_ids,
            "role_name": role_names,
            "created_by": user.created_by,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }}), 200
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200

@profile_bp.route("/update", methods=["POST"])
@require_privilege("USER")
def update_profile():
    try:
        user_id = request.json.get("user_id")
        user = User.query.filter_by(uid=user_id).first()
        if not user:
            return jsonify({"status": 0, "message": "User not found"}), 200
        user.first_name = request.json.get("first_name")
        user.middle_name = request.json.get("middle_name")
        user.last_name = request.json.get("last_name")
        user.phone_no = request.json.get("phone_no")
        user.email_id = request.json.get("email_id")
        user.updated_by = request.json.get("updated_by")
        user.updated_at = datetime.now()
        db.session.commit()
        return jsonify({"status": 1, "message": "User updated successfully"}), 200
    except Exception as e:
        return jsonify({"status": 0, "message": str(e)}), 200