from flask import Blueprint, request, jsonify
from app.models.roles import RoleMaster
from app.extensions import db
from app.models.previllage import ModuleMaster
from app.models.previllage_map import RolePrivilegeMap
from werkzeug.exceptions import NotFound
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import asc, desc
from app.utils.privilege_decorator import require_privilege


role_bp= Blueprint("role_bp", __name__)


@role_bp.route("/list", methods=["POST"])
#@require_privilege("VIEW_ROLE")
def list_roles():
    data = request.get_json()

    page = data.get("page", 1)
    page_size = data.get("pageSize", 15)
    search_term = data.get("searchTerm", "")
    sort_column = data.get("sortColumn", "")
    sort_direction = data.get("sortDirection", "")

    # 1️⃣ Base Query
    query = RoleMaster.query

    # 2️⃣ Search Filter → apply on name, code, description
    if search_term:
        search = f"%{search_term}%"
        query = query.filter(
            (RoleMaster.name.ilike(search)) |
            (RoleMaster.code.ilike(search)) |
            (RoleMaster.description.ilike(search))
        )

    # 3️⃣ Sorting
    if sort_column:
        sort_attr = getattr(RoleMaster, sort_column, None)
        if sort_attr:
            if sort_direction.lower() == "desc":
                query = query.order_by(desc(sort_attr))
            else:
                query = query.order_by(asc(sort_attr))
    else:
        # Default sort → latest first
        query = query.order_by(desc(RoleMaster.created_at))

    # 4️⃣ Total before pagination
    total = query.count()

    # 5️⃣ Pagination
    records = query.offset((page - 1) * page_size).limit(page_size).all()

    # 6️⃣ Format Response
    data_list = [record.to_dict() for record in records]

    return jsonify({
        "data": data_list,
        "total": total
    })
@role_bp.route("/create", methods=["POST"])
#@require_privilege("CREATE_ROLE")
def create_role():
    data = request.get_json()

    name = data.get("name")
    role_type = int(data.get("role_type_id"))   # ✅ FIXED
    module_ids = data.get("privilege_id", [])
    print("module",module_ids)

    if not name or not role_type:
        return jsonify({"status": 0, "message": "Missing required fields"}), 400

    new_role = RoleMaster(
        name=name,
        resource_access=role_type,
        status=0,
        created_by_name="Admin"
    )
    db.session.add(new_role)
    db.session.commit()
    print(new_role)

    # ✅ Load all modules if role_type = 1
    if role_type == 1:
        all_modules = ModuleMaster.query.with_entities(ModuleMaster.module_id).all()
        module_ids = [m[0] for m in all_modules]

    # ✅ Insert module mappings safely
    for mid in module_ids:
        mapping = RolePrivilegeMap(role_id=new_role.id, module_id=mid)
        db.session.add(mapping)

    db.session.commit()

    return jsonify({"status": 1, "message": "User Role has been created successfully"})


@role_bp.route("/update", methods=["POST"])
#@require_privilege("UPDATE_ROLE")
def update_role():
    data = request.get_json()

    role_id = data.get("id")
    name = data.get("name")
    role_type = data.get("role_type_id")
    module_ids = data.get("privilege_id", [])
    


    if not role_id or not name or not role_type:
        return jsonify({"status": 0, "message": "Missing required fields"}), 400

    # Fetch existing role
    role = RoleMaster.query.filter_by(id=role_id).first()
    if not role:
        return jsonify({"status": 0, "message": "Role not found"}), 404

    # Update basic fields
    role.name = name
    role.resource_access = role_type
    role.updated_by_name = "Admin"

    # If role_type = 1 (All) → assign ALL modules
    if role_type == 1:
        all_modules = ModuleMaster.query.with_entities(ModuleMaster.module_id).all()
        module_ids = [m[0] for m in all_modules]

    # STEP 1: Remove old mappings
    RolePrivilegeMap.query.filter_by(role_id=role.id).delete()

    # STEP 2: Insert updated mappings
    for mid in module_ids:
        
        mapping = RolePrivilegeMap(role_id=role.id, module_id=mid)
        db.session.add(mapping)

    db.session.commit()

    return jsonify({"status": 1, "message": "User Role has been updated successfully"})

@role_bp.route("/details", methods=["POST"])
#@require_privilege("ROLE_DETAILS")
def get_role_details():
    data = request.get_json()
    role_id = data.get("id")

    if not role_id:
        return jsonify({"status": 0, "message": "Role ID is required"}), 400

    # Fetch role
    role = RoleMaster.query.filter_by(id=role_id).first()
    if not role:
        return jsonify({"status": 0, "message": "Role not found"}), 404

    # Fetch privilege IDs for this role
    privs = (
        RolePrivilegeMap.query.with_entities(RolePrivilegeMap.module_id)
        .filter_by(role_id=role_id)
        .all()
    )
    
    module_ids = [p[0] for p in privs]

    # Prepare response in required format
    response_data = {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "resource_access": role.resource_access,
        "description": role.description,
        "status": role.status,
        "created_by": role.created_by_name,
        "created_at": int(role.created_at.timestamp()) if role.created_at else None,
        "updated_by": role.updated_by_name,
        "updated_at": int(role.updated_at.timestamp()) if role.updated_at else None
    }

    return jsonify({
        "data": response_data,
        "privilege_id": module_ids
    })


@role_bp.route("/status", methods=["POST"])
#@require_privilege("ROLE_STATUS")
def update_role_status():
    data = request.get_json()

    role_id = data.get("id")
    status = data.get("status")   # 0 = Active, 1 = Inactive

    if role_id is None or status is None:
        return jsonify({"status": 0, "message": "Role ID and status are required"}), 400

    role = RoleMaster.query.filter_by(id=role_id).first()

    if not role:
        return jsonify({"status": 0, "message": "Role not found"}), 404

    # Update Status
    role.status = status
    db.session.commit()

    # Response message
    if status == 0:
        msg = "Role has been activated successfully"
    else:
        msg = "Role has been deactivated successfully"

    return jsonify({"status": 1, "message": msg})

@role_bp.route("/types", methods=["POST"])
#@require_privilege("ROLE_TYPE")
def get_role_types():
    data = request.get_json()
    status = data.get("status")   # Not really needed but included as per request

    # Static role types
    role_types = [
        {"id": 1, "name": "All"},
        {"id": 2, "name": "Custom"}
    ]

    return jsonify({"data": role_types})


@role_bp.route("/get", methods=["POST"])
#@require_privilege("ROLE_ACTIVE_INACTIVE")
def get_roles():
    data = request.get_json()
    status = data.get("status")   # 0 = Active, 1 = Inactive

    if status is None:
        return jsonify({"status": 0, "message": "Status is required"}), 400

    roles = (
        RoleMaster.query
        .with_entities(RoleMaster.id, RoleMaster.name)
        .filter_by(status=status)
        .order_by(RoleMaster.name.asc())
        .all()
    )

    result = [{"id": r.id, "name": r.name} for r in roles]

    return jsonify({"data": result})

@role_bp.route("/view", methods=["POST"])
#@require_privilege("ROLE_DELETE")
def get_single_role():
    data = request.get_json()
    role_id = data.get("id")
 
    if not role_id:
        return jsonify({"status": 0, "message": "Role ID is required"}), 400
 
    role = RoleMaster.query.filter_by(id=role_id).first()
    if not role:
        return jsonify({"status": 0, "message": "Role not found"}), 404
 
    privs = (
        RolePrivilegeMap.query.with_entities(RolePrivilegeMap.module_id)
        .filter_by(role_id=role_id)
        .all()
    )
    module_ids = [p[0] for p in privs]
    # Fetch all descendant modules for the selected privilege IDs
 
    names=ModuleMaster.query.filter(ModuleMaster.module_id.in_(module_ids)).all()
    module_names=[n.module_name for n in names]
   
 
    '''all_related_module_ids = set(module_ids)
   
    # Recursively find all child modules
    while True:
        new_children = (
            ModuleMaster.query.with_entities(ModuleMaster.module_id)
            .filter(ModuleMaster.parent_id.in_(all_related_module_ids))
            .filter(ModuleMaster.module_id.notin_(all_related_module_ids))
            .all()
        )
        if not new_children:
            break
       
        new_child_ids = {m[0] for m in new_children}
        all_related_module_ids.update(new_child_ids)
 
    # Convert set back to list for further operations
    module_ids = list(all_related_module_ids)
 
 
    modules = (
        ModuleMaster.query.with_entities(ModuleMaster.module_id, ModuleMaster.module_name)
        .filter(ModuleMaster.module_id.in_(module_ids))
        .all()
    )
    module_names = [{"id": m.module_id, "name": m.module_name} for m in modules]
'''
    response_data = {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "resource_access": role.resource_access,
        "resource_access_label": "All" if role.resource_access == 1 else "Custom",
        "description": role.description,
        "status": role.status,
        "created_by": role.created_by_name,
        "created_at": int(role.created_at.timestamp()) if role.created_at else None,
        "updated_by": role.updated_by_name,
        "updated_at": int(role.updated_at.timestamp()) if role.updated_at else None
    }
 
    return jsonify({
        "data": response_data,  
        "privilege_id": module_ids,
        "privilege_label": module_names
    })
 
