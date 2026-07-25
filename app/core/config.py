import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")

    DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "storage/uploads")
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "change-me")
    ENABLE_LLM_CATEGORIZATION = os.getenv("ENABLE_LLM_CATEGORIZATION", "true").lower() == "true"

settings = Settings()