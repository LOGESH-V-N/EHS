import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = "ahsjhahjajhhajhah"

    AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
    AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
    AWS_REGION = os.getenv("AWS_REGION")
    if os.getenv("DEVELOPMENT_MODE")=="True":
        AWS_BUCKET = os.getenv("AWS_DEV_BUCKET")
    else:
        AWS_BUCKET = os.getenv("AWS_PROD_BUCKET")
    AWS_BUCKET_MAIL = os.getenv("MAIL_FOLDER")
    AWS_LISTENER_FOLDER=os.getenv("FOLDER_LISTENER")
    AWS_APP_FOLDER=os.getenv("APP_FOLDER")
    AWS_JSON_FOLDER=os.getenv("JSON_FOLDER")
    
    SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_pre_ping": True,      # ✅ MOST IMPORTANT
    "pool_recycle": 280,        # recycle before MySQL timeout
    "pool_size": 10,
    "max_overflow": 20,
}
    

