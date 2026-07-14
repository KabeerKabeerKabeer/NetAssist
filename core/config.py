import os
from dotenv import load_dotenv

# Ensure environment variables are loaded from the root .env file
load_dotenv(override=True)

class AppSettings:
    def __init__(self):
        # 1. API Credentials
        self.geminiApiKey = os.getenv("GEMINI_API_KEY")
        if not self.geminiApiKey:
            raise ValueError("CRITICAL: GEMINI_API_KEY environment variable is missing.")

        # 2. Local File System Paths
        self.dbPath = os.getenv("DATABASE_PATH", "data/companyData.db")
        self.chromaStoragePath = os.getenv("CHROMA_STORAGE_PATH", "data/chromaStorage")
        self.employeeJsonPath = os.getenv("EMPLOYEE_JSON_PATH", "data/employeeProfiles.json")

        # 3. Scraper & Background Task Settings
        self.scraperBaseUrl = os.getenv("SCRAPER_BASE_URL", "https://netsoltech.com/")
        self.scraperMaxPages = int(os.getenv("SCRAPER_MAX_PAGES", 40))
        self.syncIntervalHours = int(os.getenv("SYNC_INTERVAL_HOURS", 12))

        # 4. Vector Database Configurations
        self.chromaCollectionName = os.getenv("CHROMA_COLLECTION_NAME", "netsolWebsite")

# Instantiate a single global configuration instance to share across modules
settings = AppSettings()