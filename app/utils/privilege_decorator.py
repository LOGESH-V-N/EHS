from functools import wraps
import datetime
import jwt
from flask import request, jsonify, g, current_app
from jwt import ExpiredSignatureError, InvalidTokenError

from app.extensions import db
from app.models.user import User

JWT_SECRET = "MY_JWT_SECRET_KEY_123"
JWT_ALGO = "HS256"


def _utcnow():
    return datetime.datetime.utcnow()


def decode_jwt():
    token = request.headers.get("Authorization")
    if not token:
        return None, {
            "status": 0,
            "message": "Authorization token missing"
        }

    try:
        _, jwt_token = token.split(" ")
        decoded = jwt.decode(
            jwt_token,
            JWT_SECRET,
            algorithms=[JWT_ALGO]
        )

        user = User.query.filter_by(uid=decoded.get("uid")).first()
        if not user:
            return None, {
                "status": 0,
                "message": "User not found"
            }

        if user.status == 1:
            return None, {
                "status": 0,
                "message": "Account is locked/inactive. Please contact admin."
            }

        timeout_minutes = current_app.config.get("SESSION_IDLE_TIMEOUT_MINUTES", 30)
        now = _utcnow()
        if user.last_login_at and now - user.last_login_at > datetime.timedelta(minutes=timeout_minutes):
            return None, {
                "status": 0,
                "message": "Session timed out due to inactivity. Please login again."
            }

        user.last_login_at = now
        db.session.commit()
        return decoded, None

    except ExpiredSignatureError:
        return None, {
            "status": 0,
            "message": "Token expired. Please login again."
        }

    except InvalidTokenError:
        return None, {
            "status": 0,
            "message": "Invalid token"
        }

    except Exception as e:
        return None, {
            "status": 0,
            "message": f"JWT decode failed: {str(e)}"
        }


def require_privilege(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            decoded, error = decode_jwt()

            if error:
                return jsonify(error), 401

            user_id = decoded.get("uid")
            rules = decoded.get("rules", {})
            resource_access = rules.get("resource_access")
            g.user_id = user_id

            if resource_access == 1:
                return f(*args, **kwargs)

            if resource_access == 2:
                if role == "ADMIN":
                    return jsonify({
                        "status": 0,
                        "message": "Admin access required"
                    }), 403

                return f(*args, **kwargs)

            return jsonify({
                "status": 0,
                "message": "Invalid role"
            }), 403

        return wrapper
    return decorator
