import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
    MEDIA_FOLDER   = os.path.join(BASE_DIR, "media")
    UPLOAD_FOLDER  = os.path.join(BASE_DIR, "media", "uploads")
    OUTPUT_FOLDER  = os.path.join(BASE_DIR, "media", "outputs")
    DATABASE       = os.path.join(BASE_DIR, "db.sqlite3")
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024   # 200 MB — supports many files
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
