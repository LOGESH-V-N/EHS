from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.integration_master import IntegrationMaster
from app.models.integration_modules import IntegrationModules
from app.models.app_config import AppConfig
from app.models.app_modules import AppModules
from datetime import datetime
integration_bp = Blueprint('integration_bp', __name__)

@integration_bp.route("/integration", methods=["POST"])
def get_app_configurations():

    integrations = IntegrationMaster.query.filter_by(delete_status=0).all()
    result = []

    for integration in integrations:

        # check integration config
        config = AppConfig.query.filter_by(im_id=integration.id).first()

        if not config:
            config = AppConfig(
                im_id=integration.id,
                active_status=0,
                updated_date=datetime.utcnow()
            )
            db.session.add(config)
            db.session.commit()

        modules = IntegrationModules.query.filter_by(
            im_id=integration.id,
            delete_status=0
        ).all()

        module_list = []

        for module in modules:

            app_module = AppModules.query.filter_by(m_id=module.m_id).first()

            if not app_module:
                app_module = AppModules(
                    m_id=module.m_id,
                    active_status=0,
                    updated_date=datetime.utcnow()
                )
                db.session.add(app_module)
                db.session.commit()

            module_list.append({
                "m_id": module.m_id,
                "code": module.module_name,
                "name": module.display_name,
                "active_status": app_module.active_status
            })

        result.append({
            "id": integration.id,
            "code": integration.code,
            "name": integration.name,
            "active_status": config.active_status,
            "modules": module_list
        })

    return jsonify({
        "message": "App Configuration fetched successfully",
        "status": 1,
        "data": result
    })

'''@integration_bp.route("/save-integration", methods=["POST"])
def save_integration():
    return jsonify({
        "message": "App Configuration fetched successfully",
        "status": 1
    })'''

@integration_bp.route("/save-integration", methods=["POST"])
def save_integration():

    data = request.json
    integrations = data.get("integrations", [])

    try:

        # 1️⃣ Reset all statuses
        AppConfig.query.update({"active_status": 0})
        AppModules.query.update({"active_status": 0})

        for integration in integrations:

            im_id = integration.get("id")
            integration_status = integration.get("active_status")

            config = AppConfig.query.filter_by(im_id=im_id).first()

            if config:
                config.active_status = integration_status
                config.updated_date = datetime.utcnow()

            # 2️⃣ Update modules
            modules = integration.get("modules", [])

            for module in modules:

                m_id = module.get("m_id")
                module_status = module.get("active_status", 0)

                app_module = AppModules.query.filter_by(m_id=m_id).first()

                if app_module:
                    app_module.active_status = module_status
                    app_module.updated_date = datetime.utcnow()

        db.session.commit()

        return jsonify({
            "message": "App Configuration updated successfully",
            "status": 1
        }), 200

    except Exception as e:

        db.session.rollback()

        return jsonify({
            "message": str(e),
            "status": 0
        }), 200