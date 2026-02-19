from flask import Flask
from .extensions import db, ma, cors, jwt
from .config import Config
from .routes import register_routes

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    ma.init_app(app)
    cors.init_app(app)

    jwt.init_app(app)
    register_routes(app)

    return app
