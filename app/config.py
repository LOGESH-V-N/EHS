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
    AWS_BUCKET = os.getenv("AWS_DEFAULT_BUCKET")
    
    SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_pre_ping": True,      # ✅ MOST IMPORTANT
    "pool_recycle": 280,        # recycle before MySQL timeout
    "pool_size": 10,
    "max_overflow": 20,
}
    

