from flask import Blueprint, request, jsonify,g
from app.models.ehs_doc_priority import Ehs_Doc_Priority
from app.models.ehs_doc_task import EhsDocumentTask
from app.models.user import User
from app import db
from app.utils.privilege_decorator import require_privilege


doc_task_bp = Blueprint("doc_task_bp", __name__)


# to see the priority list for the db
@doc_task_bp.route("/priority", methods=["POST"])
@require_privilege("USER")
def priority_api():
    try:
        priority = Ehs_Doc_Priority.query.all()
        priority_list = []
        for pri in priority:
            priority = {
                "id": pri.id,
                "name": pri.name,
                "code": pri.code
            }
            priority_list.append(priority)
        return jsonify({"status": 1, "data": priority_list}), 200
    except Exception as e:
        return jsonify({"status": 0, "error": str(e)}), 200


@doc_task_bp.route("/list", methods=["POST"])
@require_privilege("USER")
def task_list_api():
    try:
        data=request.get_json()
        doc_id=data.get("doc_id")
        task = EhsDocumentTask.query.filter_by(doc_id=doc_id).all()
        task_list = []
        for t in task:
            if t.assign_to==None:
                assign_to=None
            else:
                assign_to=User.query.filter_by(uid=t.assign_to).first().name
            if t.priority_id==None:
                priority_id=None
            else:
                priority_id=Ehs_Doc_Priority.query.filter_by(id=t.priority_id).first().name
            if t.created_by==None:
                created_by=None
            else:
                created_by=User.query.filter_by(uid=t.created_by).first().name
            if t.updated_by==None:
                updated_by=None
            else:
                updated_by=User.query.filter_by(uid=t.updated_by).first().name


            task = {
                "id": t.id,
                "doc_id": t.doc_id,
                "task_name": t.task_name,
                "sub_title": t.sub_title,
                "assign_to": t.assign_to,
                "assign_to_label": User.query.filter_by(uid=t.assign_to).first().name if User.query.filter_by(uid=t.assign_to).first() else None,
                "note": t.note,
                "due_date": t.due_date.strftime("%Y-%m-%d") if t.due_date else None,
                "priority_id": t.priority_id,
                "priority_label": priority_id,
                "priority_color": Ehs_Doc_Priority.query.filter_by(id=t.priority_id).first().color_code if t.priority_id else None,
                "created_by": t.created_by,
                "created_by_name": created_by,
                "updated_by": t.updated_by,
                "updated_by_name": updated_by,
                "created_at": t.created_at.strftime("%Y-%B-%d %H:%M:%S"),
                "updated_at": t.updated_at.strftime("%Y-%B-%d %H:%M:%S")
            }
            task_list.append(task)
        return jsonify({"status": 1, "data": task_list}), 200
    except Exception as e:
        return jsonify({"status": 0, "error": str(e)}), 200

@doc_task_bp.route("/create", methods=["POST"])
@require_privilege("USER")
def task_add_api():
    try:
        data=request.get_json()
        doc_id=data.get("doc_id")
        task_name=data.get("task_name")
        sub_title=data.get("sub_title")
        assign_to=data.get("assign_to")
        note=data.get("note")
        due_date=data.get("due_date")
        priority_id=data.get("priority_id")
        created_by=g.user_id
        if assign_to=="":
            assign_to=None
        if due_date=="":
            due_date=None
        if priority_id=="":
            priority_id=None
        if sub_title=="":
            sub_title=None
        if note=="":
            note=None

        task = EhsDocumentTask(doc_id=doc_id, task_name=task_name, sub_title=sub_title, assign_to=assign_to, note=note, due_date=due_date, priority_id=priority_id, created_by=created_by)
        db.session.add(task)
        db.session.commit()
        return jsonify({"status": 1, "message": "Task added successfully"}), 200
    except Exception as e:
        return jsonify({"status": 0, "error": str(e)}), 200

@doc_task_bp.route("/update", methods=["POST"])
@require_privilege("USER")
def task_update_api():
    try:
        data=request.get_json()
        id=data.get("id")
        doc_id=data.get("doc_id")
        task_name=data.get("task_name")
        sub_title=data.get("sub_title")
        assign_to=data.get("assign_to")
        note=data.get("note")
        due_date=data.get("due_date")
        priority_id=data.get("priority_id")
        updated_by=g.user_id
        task = EhsDocumentTask.query.filter_by(id=id,doc_id=doc_id).first()
        if not task:
            return jsonify({"status": 0, "error": "Task not found"}), 200
        task.task_name = task_name
        task.sub_title = sub_title
        task.assign_to = assign_to
        task.note = note
        task.due_date = due_date
        task.priority_id = priority_id
        task.updated_by = updated_by
        db.session.commit()
        return jsonify({"status": 1, "message": "Task updated successfully"}), 200
    except Exception as e:
        return jsonify({"status": 0, "error": str(e)}), 200

@doc_task_bp.route("/delete", methods=["POST"])
@require_privilege("USER")
def task_delete_api():
    try:
        data=request.get_json()
        id=data.get("id")
        doc_id=data.get("doc_id")
        task = EhsDocumentTask.query.filter_by(id=id,doc_id=doc_id).first()
        db.session.delete(task)
        db.session.commit()
        return jsonify({"status": 1, "message": "Task deleted successfully"}), 200
    except Exception as e:
        return jsonify({"status": 0, "error": str(e)}), 200
