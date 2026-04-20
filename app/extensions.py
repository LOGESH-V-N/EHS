from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask import jsonify

db = SQLAlchemy()
ma = Marshmallow()
cors = CORS()
jwt = JWTManager()


def init_jwt(app):
    jwt.init_app(app)
@jwt.expired_token_loader

def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        "status":"error",
        "data":{},
        "message": "Token has expired"
    }), 400
    
