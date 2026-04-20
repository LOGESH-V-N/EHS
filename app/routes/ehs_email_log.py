from flask import Blueprint, request, jsonify
from app.models.ehs_sync_log import EhsSyncLog
from app.extensions import db
from datetime import datetime
from app.utils.privilege_decorator import require_privilege


email_log_bp= Blueprint("email_log_bp", __name__)


@email_log_bp.route("/email_get_log", methods=["GET"])
@require_privilege("USER")
def email_log():
    try:
        # Get latest record based on sync_time
        latest_log = (
            db.session.query(EhsSyncLog)
            .order_by(EhsSyncLog.id.desc())
            .first()
        )

        if not latest_log:
            return jsonify({
                "status": 1,
                "message": "No sync records found",
                "sync_time": None
            }), 200

        return jsonify({
            "status": 1,
            "sync_time": latest_log.sync_time
        }), 200

    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 500
    

@email_log_bp.route("/email_insert_log", methods=["POST"])
@require_privilege("USER")
def insert_email_log():
    try:
        data = request.get_json()

        sync_time_str = data.get("sync_time")

        if not sync_time_str:
            return jsonify({
                "status": 0,
                "message": "sync_time is required"
            }), 400

        # Expected format: YYYY-MM-DD HH:MM:SS
       

        new_log = EhsSyncLog(
            sync_time=sync_time_str
        )

        db.session.add(new_log)
        db.session.commit()

        return jsonify({
            "status": 1,
            "message": "Sync log inserted successfully",
            "id": new_log.id
        }), 201

    except ValueError:
        return jsonify({
            "status": 0,
            "message": "Invalid datetime format. Use YYYY-MM-DD HH:MM:SS"
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 500