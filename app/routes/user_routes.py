from flask import Blueprint, request, jsonify
from app.models.user import User
from app.models.user_role import UserRole
from app.models.roles import RoleMaster
from app.schemas.user_schema import user_schema, users_schema
from app.extensions import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import text
from datetime import datetime
from app.utils.privilege_decorator import require_privilege
from app.utils.date_formatter import format_datetime




user_bp = Blueprint("user_bp", __name__)

@user_bp.route("/list", methods=["POST"])
# @require_privilege("VIEW_USERS")
def list_users():
    data = request.get_json() or {}

    # Basic pagination & sorting
    page = data.get("page", 1)
    page_size = data.get("pageSize", 15)
    search_term = data.get("searchTerm", "")
    sort_column = data.get("sortColumn", "uid")
    sort_direction = data.get("sortDirection", "asc")

    # Optional filter data (role filter)
    filter_data = data.get("filterData") or {}
    role_filter = filter_data.get("role")  # e.g. "2" or "" or None

    # Base query: active & not deleted
    query = User.query.filter_by(delete_status=0)

    # ---------- Search filter (runs always if search_term given) ----------
    if search_term:
        like_term = f"%{search_term}%"
        query = query.filter(
            db.or_(
                User.name.ilike(like_term),
                User.username.ilike(like_term),
                User.email_id.ilike(like_term),
            )
        )

    # ---------- Role filter (ONLY if role_filter is provided and valid) ----------
    # If frontend does NOT send filterData or role is "", this block is skipped.
    if role_filter not in (None, "", "0"):
        try:
            role_id = int(role_filter)
        except (TypeError, ValueError):
            role_id = None

        if role_id:
            query = (
                query.join(UserRole, User.uid == UserRole.user_id)
                     .filter(UserRole.role_id == role_id)
                     .distinct()
            )

    # ---------- Sorting ----------
    if sort_column and hasattr(User, sort_column):
        column = getattr(User, sort_column)
        if sort_direction == "desc":
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())
    else:
        # default order (if no sortColumn)
        query = query.order_by(User.uid.desc())

    # ---------- Pagination ----------
    total_count = query.count()
    users = query.paginate(page=page, per_page=page_size, error_out=False).items

    # ---------- Preload roles & created_by names for users on this page ----------
    user_ids = [u.uid for u in users]
    roles_by_user = {}
    creators_by_id = {}

    if user_ids:
        # roles
        role_rows = (
            db.session.query(UserRole.user_id, RoleMaster.name)
            .join(RoleMaster, RoleMaster.id == UserRole.role_id)
            .filter(UserRole.user_id.in_(user_ids))
            .all()
        )
        for user_id, role_name in role_rows:
            roles_by_user.setdefault(user_id, []).append(role_name)

        # created_by names
        creator_ids = [u.created_by for u in users if u.created_by]
        if creator_ids:
            creator_rows = (
                db.session.query(User.uid, User.name)
                .filter(User.uid.in_(creator_ids))
                .all()
            )
            for uid, name in creator_rows:
                creators_by_id[uid] = name

    # ---------- Build response user list ----------
    serialized_users = []
    for u in users:
        user_dict = user_schema.dump(u)

        # Add role names
        role_names = roles_by_user.get(u.uid, [])
        user_dict["role"] = ", ".join(role_names) if role_names else None

        # Add created_by user name
        user_dict["created_by_name"] = creators_by_id.get(u.created_by)
        user_dict["created_at"]= format_datetime(u.created_at)
        user_dict["updated_at"]= format_datetime(u.updated_at)

        serialized_users.append(user_dict)

    return jsonify({
        "status": "1",
        "message": "Users fetched successfully",
        "total": total_count,
        "data": serialized_users
    })

@user_bp.route("/create", methods=["POST"])
# @require_privilege("CREATE_USER")
def add_user():
    data = request.get_json() or {}

    # ---------- Read fields from frontend payload ----------
    first_name  = (data.get("first_name") or "").strip()
    middle_name = (data.get("middle_name") or "").strip()
    last_name   = (data.get("last_name") or "").strip()
    email_id    = (data.get("email") or "").strip()
    phone_no    = (data.get("phone") or "").strip()      # NOTE: 'phone' -> phone_no
    role_ids    = data.get("role_id") or []              # list of role ids
    password    = (data.get("password") or "")
    confirm_password = (data.get("confirm_password") or "")

    # Optional fields (frontend may not send these)
    address          = data.get("address")
    user_profile_img = data.get("user_profile_img")
    # if username is not sent, fall back to email
    username         = (data.get("username") or email_id).strip()

    # ---------- Basic validation ----------
    if not first_name or not email_id or not password:
        return jsonify({
            "status": 0,
            "message": "first_name, email and password are required"
        }), 200

    if password != confirm_password:
        return jsonify({"status": 0, "message": "Passwords do not match"}), 200

    # Check if username exists (only if we actually have one)
    if username:
        existing_username = User.query.filter_by(username=username).first()
        if existing_username:
            return jsonify({"status": 0, "message": "Username already exists"}), 200

    # Check if email exists
    existing_email = User.query.filter_by(email_id=email_id).first()
    if existing_email:
        return jsonify({"status": 0, "message": "Email already exists"}), 200

    # ---------- Build full display name ----------
    name_parts = [first_name]
    if middle_name:
        name_parts.append(middle_name)
    if last_name:
        name_parts.append(last_name)
    full_name = " ".join(name_parts)

    # ---------- Create User ----------
    user = User(
        name=full_name,
        first_name=first_name,
        middle_name=middle_name or None,
        last_name=last_name or None,
        username=username or None,
        email_id=email_id,
        phone_no=phone_no,
        address=address,
        user_profile_img=user_profile_img,
        created_by=1,   # later you can take this from JWT/current user
        updated_by=1
    )
    user.set_password(password)

    db.session.add(user)
    db.session.flush()   # so user.uid is available BEFORE commit

    # ---------- Insert roles into tbl_user_roles ----------
    for role_id in role_ids:
        db.session.execute(
            text("""
                INSERT INTO tbl_user_roles (user_id, role_id)
                VALUES (:user_id, :role_id)
            """),
            {"user_id": user.uid, "role_id": role_id}
        )

    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "User has been created successfully"    
    }), 200

# get a single user details

@user_bp.route("/view", methods=["POST"])
#@require_privilege("GET_USER")
def get_user():
    data = request.get_json()
    user_id = data.get("id")

    user = User.query.filter_by(uid=user_id, delete_status=0).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    # Fetch user-role mappings
    role_links = UserRole.query.filter_by(user_id=user.uid).all()
    role_ids = [rl.role_id for rl in role_links]  # uses tbl_user_roles.role_id

    # Fetch role names from RoleMaster
    roles = RoleMaster.query.filter(RoleMaster.id.in_(role_ids)).all()
    role_names = ", ".join([r.name for r in roles]) if roles else ""

    # Created by name
    created_by_name = ""
    if user.created_by:
        cb = User.query.filter_by(uid=user.created_by).first()
        if cb:
            created_by_name = cb.name

    # Updated by name
    updated_by_name = ""
    if user.updated_by:
        ub = User.query.filter_by(uid=user.updated_by).first()
        if ub:
            updated_by_name = ub.name

    result = {
        "id": user.uid,
        "name": user.name,
        "first_name": user.first_name,  # As you requested
        "middle_name": user.middle_name,
        "last_name": user.last_name,
        "username": user.username,
        "email": user.email_id,
        "phone": user.phone_no,
        "role_id": role_ids,          # List of IDs
        "role_name": role_names,      # Comma-separated names
        "created_at": format_datetime(user.created_at) or "",
        "created_by_name": created_by_name,
        "updated_at": format_datetime(user.updated_at) or "",
        "updated_by_name": updated_by_name,
        "status": user.status,
        "status_label": "Active" if user.status == 0 else "Inactive"
    }

    return jsonify({"data": result})

# update user
@user_bp.route('/update', methods=['POST'])
def update_user():
    data = request.get_json() or {}

    uid = data.get("uid")
    if not uid:
        return jsonify({"status": 0, "message": "User ID is required"}), 200

    # Fetch user
    user = User.query.filter_by(uid=uid, delete_status=0).first()
    if not user:
        return jsonify({"status": 0, "message": "User not found"}), 200

    # ------------------------------
    # Read fields (USE SAME KEYS AS FRONTEND)
    # ------------------------------
    first_name  = (data.get("first_name") or "").strip()
    middle_name = (data.get("middle_name") or "").strip()
    last_name   = (data.get("last_name") or "").strip()
    username    = (data.get("username") or "").strip()
    email_id    = (data.get("email") or "").strip()
    phone_no    = (data.get("phone") or "").strip()
    address     = data.get("address")
    role_ids    = data.get("role_id") or []

    # ------------------------------
    # Validation
    # ------------------------------
    if not first_name or not email_id :
        return jsonify({"status": 0, "message": "first_name, email are required"}), 200

    # Duplicate email check
    email_exists = User.query.filter(
        User.email_id == email_id,
        User.uid != uid
    ).first()
    if email_exists:
        return jsonify({"status": 0, "message": "Email already exists"}), 200


    # ------------------------------
    # Rebuild full name
    # ------------------------------
    name_parts = []
    if first_name:
        name_parts.append(first_name)
    if middle_name:
        name_parts.append(middle_name)
    if last_name:
        name_parts.append(last_name)
    full_name = " ".join(name_parts)
        
    # ------------------------------
    # Update user fields
    # ------------------------------
    user.name = full_name
    user.first_name = first_name
    user.middle_name = middle_name or None
    user.last_name = last_name or None
    user.username = username
    user.email_id = email_id
    user.phone_no = phone_no
    user.address = address
    user.updated_at = datetime.now()
    user.updated_by = 1   # later: current user from JWT

    # ------------------------------
    # Update roles (tbl_user_roles)
    # ------------------------------
    UserRole.query.filter_by(user_id=uid).delete()

    for rid in role_ids:
        db.session.add(UserRole(user_id=uid, role_id=rid))

    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "User has been updated successfully"
    })



@user_bp.route("/<int:id>", methods=["DELETE"])
#@require_privilege("DELETE_USER")
def delete_user(id):

    user = User.query.get(id)
    if not user:
        response = {
            "status": 0,
            "message": "User not found"
        }
        return jsonify(response), 200
    db.session.delete(user)
    db.session.commit()
   
    response = {
        "status": 1,
        "message": "User deleted successfully"
    }
    return jsonify(response)



@user_bp.route("/status", methods=["POST"])
#@require_privilege("CHANGE_STATUS_USER")
def update_user_status():
    """current_user = get_jwt_identity()

    if not current_user:
        return jsonify({
            "status": 0,
            "message": "Invalid or missing token."
        }), 400"""

    data = request.get_json() or {}

    user_id = data.get("id")
    new_status = data.get("status")

    # Basic validation
    if user_id is None or new_status is None:
        return jsonify({
            "status": 0,
            "message": "Both 'id' and 'status' are required."
        }), 200

    # Ensure status is either 0 or 1
    try:
        new_status = int(new_status)
    except (TypeError, ValueError):
        return jsonify({
            "status": 0,
            "message": "Status must be 0 (activate) or 1 (deactivate)."
        }), 200

    if new_status not in (0, 1):
        return jsonify({
            "status": 0,
            "message": "Status must be 0 (activate) or 1 (deactivate)."
        }), 200

    user = User.query.get(user_id)
    if not user:
        return jsonify({
            "status": 0,
            "message": "User not found."
        }), 200

    # Update status (0 = active, 1 = inactive)
    user.status = new_status
    db.session.commit()

    # Message based on new status
    if new_status == 0:
        msg = "User has been activated successfully"
    else:
        msg = "User has been deactivated successfully"

    return jsonify({
        "status": 1,
        "message": msg
    }), 200

