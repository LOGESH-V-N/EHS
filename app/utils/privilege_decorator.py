from functools import wraps
from flask import request, jsonify,g
from jwt import ExpiredSignatureError, InvalidTokenError
import jwt

JWT_SECRET = "MY_JWT_SECRET_KEY_123"  # JWT secret
JWT_ALGO = "HS256"

def decode_jwt():
    token = request.headers.get("Authorization")
    if not token:
        return None, {
            "status": 0,
            "message": "Authorization token missing"
        }

    try:
        _, jwt_token = token.split(" ")  # Bearer <jwt>

        decoded = jwt.decode(
            jwt_token,
            JWT_SECRET,
            algorithms=[JWT_ALGO]
        )
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

            # 🔐 Always set g.user_id once JWT is valid
            g.user_id = user_id

            # ADMIN → full access
            if resource_access == 1:
                return f(*args, **kwargs)

            # USER
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


'''def require_privilege(privilege=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            decoded, error = decode_jwt()
            if error:
                return jsonify(error), 401

            rules = decoded.get("rules", {})
            print(decoded)
            resource_access = rules.get("resource_access")
            privileges = rules.get("privileges", [])

            # Normalize privileges for comparison
            normalized_privileges = [p.upper().replace(" ", "_") for p in privileges]
            normalized_required = privilege.strip().upper().replace(" ", "_") if privilege else None

            # Role type 1 → full access
            if resource_access == 1:
                return f(*args, **kwargs)

            # Role type 2 → must have privilege
            if resource_access == 2:
                if normalized_required and normalized_required not in normalized_privileges:
                    return jsonify({
                        "status": 0,
                        "message": f"You do not have privilege: {privilege}"
                    }), 403
                return f(*args, **kwargs)

            return jsonify({"status": 0, "message": "Invalid role_type"}), 403

        return wrapper
    return decorator
'''
