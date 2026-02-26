import jwt
from functools import wraps
from flask import Blueprint, request, jsonify
from .user_routes import user_bp
from .auth_routes import auth_bp
from .role_routes import role_bp
from .privillage_routes import previlage_bp
from .document_routes import doc_type_bp
from .process_docs import process_docs_bp
from app.routes.ehs_document_route import document_bp
from .Snomed import snomed_bp

from .json_routes import json_doc_bp

from .ehs_document_list_routes import document_list_bp
from .profile_routes import profile_bp
from .ehs_document_task_routes import doc_task_bp
from .dashboard_routes import dashboard_bp
from .duplicate_routes import duplicate_bp
from .ingestion_routes import ingestion_bp
from .ehs_document_mail_routes import mail_list_bp
from .ehs_email_log import email_log_bp

    
 

SECRET_TOKEN = "aasasjjjnndndnfsjjn"        # x-api-key secret


# ---------------------------------------------
# 1️⃣ VALIDATE x-api-key
# ---------------------------------------------
def x_api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        api_key = request.headers.get("x-api-key")

        if not api_key:
            return jsonify({"status": 0, "message": "x-api-key missing"}), 400

        try:
            keyword, token = api_key.split(" ")
        except:
            return jsonify({"status": 0, "message": "Invalid x-api-key format"}), 400

        if token != SECRET_TOKEN:
            return jsonify({"status": 0, "message": "Invalid token!"}), 400

        return f(*args, **kwargs)

    return decorated





# ---------------------------------------------
# 4️⃣ REGISTER BLUEPRINTS WITH SECURITY
# ---------------------------------------------
def register_routes(app):

    # Apply x-api-key for selected blueprints
    for bp in [user_bp]:
        @bp.before_request
        def before_request_func():
            pass

    # Register blueprints
    app.register_blueprint(user_bp, url_prefix="/users")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(role_bp, url_prefix="/roles")
    app.register_blueprint(doc_type_bp, url_prefix="/doc")
    app.register_blueprint(previlage_bp, url_prefix="/previlage")
    app.register_blueprint(document_bp, url_prefix="/doc_tab")
    app.register_blueprint(process_docs_bp, url_prefix="/extract")
    app.register_blueprint(snomed_bp, url_prefix="/snomed")
    app.register_blueprint(json_doc_bp, url_prefix="/modify")
    app.register_blueprint(duplicate_bp, url_prefix="/duplicate")
    app.register_blueprint(document_list_bp, url_prefix="/document")
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(doc_task_bp, url_prefix="/doc_task")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(ingestion_bp, url_prefix="/ingestion")
    app.register_blueprint(mail_list_bp, url_prefix="/mail")
    app.register_blueprint(email_log_bp, url_prefix="/email_log")



