# config.py (CLEANED AND CORRECTED VERSION)

import os
from dotenv import load_dotenv

load_dotenv(".env")

class Config:
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    OWNER_ID = int(os.environ.get("OWNER_ID", 0))
    
    STORAGE_CHANNEL = int(os.environ.get("STORAGE_CHANNEL", 0))
    
    # Yeh lines bilkul class ke neeche aligned honi chahiye
    BASE_URL = os.environ.get("BASE_URL", "").rstrip('/')
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    BLOGGER_PAGE_URL = os.environ.get("BLOGGER_PAGE_URL", "")
