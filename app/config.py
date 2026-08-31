import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "fallback_secret_key")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")) # 8 hours
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./hrms.db")
    
    # Session cookie name
    COOKIE_NAME: str = "access_token"

settings = Settings()
