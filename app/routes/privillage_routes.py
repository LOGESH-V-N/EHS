from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.previllage import ModuleMaster
from app.extensions import db


previlage_bp=Blueprint("previlage_bp", __name__)

def build_module_tree(modules):
    module_map = {}
 
    for m in modules:
        module_map[m.module_id] = {
            "id": m.module_id,
            "name": m.module_name,
            "children": []
        }
 
    root_nodes = []
 
    for m in modules:
        if m.parent_id is None:
            root_nodes.append(module_map[m.module_id])
        else:
            parent = module_map.get(m.parent_id)
            if parent:
                parent["children"].append(module_map[m.module_id])
 
    return root_nodes
 
def remove_empty_children(node):
    if "children" in node:
        # Recursively clean children first
        node["children"] = [remove_empty_children(child) for child in node["children"]]
 
        # If children becomes empty → delete ONLY for leaves
        if len(node["children"]) == 0:
            del node["children"]
    return node
 
 
 
@previlage_bp.route("/all", methods=["POST"])
def get_modules():
    modules = ModuleMaster.query.order_by(ModuleMaster.parent_id, ModuleMaster.module_id).all()
    tree = build_module_tree(modules)
 
    # Remove empty children from last-level nodes
    cleaned_tree = [remove_empty_children(node) for node in tree]
    print(cleaned_tree)
 
    return jsonify(cleaned_tree)
 

@previlage_bp.route("/add", methods=["POST"])
#@jwt_required()
def add_module():
    data = request.get_json()

    module_name = data.get("module_name")
    module_code = data.get("module_code")
    parent_id = data.get("parent_id")
    status = data.get("status", 1)

    if not module_name or not module_code:
        return jsonify({"status": 0, "message": "Module name and code are required"}), 400

    # Check duplicate module_code
    existing = ModuleMaster.query.filter_by(module_code=module_code).first()
    if existing:
        return jsonify({"status": 0, "message": "Module code already exists"}), 400

    new_module = ModuleMaster(
        module_name=module_name,
        module_code=module_code,
        parent_id=parent_id,
        status=status
    )

    db.session.add(new_module)
    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "Module added successfully",
        "module_id": new_module.module_id
    })


@previlage_bp.route("/update", methods=["POST"])
#@jwt_required()
def update_module():
    data = request.get_json()
    module_id=data.get("module_id")

    module = ModuleMaster.query.get(module_id)
    if not module:
        return jsonify({"status": 0, "message": "Module not found"}), 404

    module.module_name = data.get("module_name", module.module_name)
    module.module_code = data.get("module_code", module.module_code)
    module.parent_id = data.get("parent_id", module.parent_id)
    module.status = data.get("status", module.status)

    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "Module updated successfully"
    })

@previlage_bp.route("/delete", methods=["POST"])
#@jwt_required()
def delete_module():
    data = request.get_json()
    module_id=data.get("module_id")
    module = ModuleMaster.query.get(module_id)

    if not module:
        return jsonify({"status": 0, "message": "Module not found"}), 404

    # Optional: prevent deleting parent with children
    if module.children:
        return jsonify({"status": 0, "message": "Cannot delete module with child nodes"}), 400

    db.session.delete(module)
    db.session.commit()

    return jsonify({
        "status": 1,
        "message": "Module deleted successfully"
    })
