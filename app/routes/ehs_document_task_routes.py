from flask import Blueprint, request, jsonify
from app.models.ehs_doc_priority import Ehs_Doc_Priority
from app.models.ehs_doc_task import EhsDocumentTask
from app.models.user import User
from app import db


doc_task_bp = Blueprint("doc_task_bp", __name__)

@doc_task_bp.route("/priority", methods=["POST"])
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
def task_list_api():
    try:
        data=request.get_json()
        doc_id=data.get("doc_id")
        task = EhsDocumentTask.query.filter_by(doc_id=doc_id).all()
        task_list = []
        for t in task:
            task = {
                "id": t.id,
                "doc_id": t.doc_id,
                "task_name": t.task_name,
                "sub_title": t.sub_title,
                "assign_to": t.assign_to,
                "assign_to_label": User.query.filter_by(uid=t.assign_to).first().name,
                "note": t.note,
                "due_date": t.due_date.strftime("%Y-%m-%d") if t.due_date else None,
                "priority_id": t.priority_id,
                "priority_label": Ehs_Doc_Priority.query.filter_by(id=t.priority_id).first().name,
                "created_by": t.created_by,
                "created_by_name": User.query.filter_by(uid=t.created_by).first().name,
                "updated_by": t.updated_by,
                "updated_by_name":User.query.filter_by(uid=t.updated_by).first().name,
                "created_at": t.created_at.strftime("%Y-%B-%d %H:%M:%S"),
                "updated_at": t.updated_at.strftime("%Y-%B-%d %H:%M:%S")
            }
            task_list.append(task)
        return jsonify({"status": 1, "data": task_list}), 200
    except Exception as e:
        return jsonify({"status": 0, "error": str(e)}), 200

@doc_task_bp.route("/create", methods=["POST"])
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
        created_by=data.get("created_by")
        updated_by=data.get("updated_by")
        task = EhsDocumentTask(doc_id=doc_id, task_name=task_name, sub_title=sub_title, assign_to=assign_to, note=note, due_date=due_date, priority_id=priority_id, created_by=created_by, updated_by=updated_by)
        db.session.add(task)
        db.session.commit()
        return jsonify({"status": 1, "message": "Task added successfully"}), 200
    except Exception as e:
        return jsonify({"status": 0, "error": str(e)}), 200

@doc_task_bp.route("/update", methods=["POST"])
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
        updated_by=data.get("updated_by")
        task = EhsDocumentTask.query.filter_by(id=id,doc_id=doc_id).first()
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
