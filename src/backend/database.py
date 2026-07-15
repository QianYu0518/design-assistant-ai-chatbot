import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import certifi
from dotenv import load_dotenv

load_dotenv()

class AuditDatabase:
    def __init__(self):
        self.uri = os.getenv("MONGO_URI")

        # Use motor for ASYNC support
        self.client = AsyncIOMotorClient(self.uri, tlsCAFile=certifi.where())
        self.db = self.client["ui_audit_db"]
        self.collection = self.db["audits"]
    
    async def save_audit(self, filename, query, metrics, report):
        # Save the audit result asynchronously

        try:
            document = {
                "timestamp": datetime.now(timezone.utc),
                "filename": filename or "no_file",
                "user_query": query,
                "metrics": metrics,
                "gemini_report": report
            }
            await self.collection.insert_one(document)
            return True
        
        except Exception as e:
            print(f"Database Error: {e}")
            return False

# Initialize instance
db_helper = AuditDatabase()
