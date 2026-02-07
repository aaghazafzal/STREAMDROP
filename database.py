import motor.motor_asyncio
import time
import datetime
from config import Config

class Database:
    def __init__(self):
        self._client = None
        self.db = None
        self.col = None

    async def connect(self):
        print(f"Connecting to MongoDB...")
        self._client = motor.motor_asyncio.AsyncIOMotorClient(Config.DATABASE_URL)
        self.db = self._client["UnivoraStreamDrop"]
        self.col = self.db.links
        
        # Create indexes for faster queries (Performance Optimization)
        try:
            await self.col.create_index("user_id")
            await self.col.create_index("timestamp")
            await self.col.create_index([("user_id", 1), ("timestamp", -1)])
            await self.db.users.create_index("_id")
            print("✅ Database indexes created/verified.")
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
        
        print("✅ Database connection established (MongoDB).")

    async def disconnect(self):
        if self._client:
            self._client.close()

    async def save_link(self, unique_id, message_id, backups: dict, file_name: str = "Unknown", file_size: str = "Unknown", user_id: int = 0, expiry_date: datetime.datetime = None):
        data = {
            "_id": unique_id,
            "msg_id": int(message_id),
            "backups": backups,
            "file_name": file_name,
            "file_size": file_size,
            "user_id": user_id,
            "timestamp": int(time.time()),
            "date_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "expiry_date": expiry_date # New Field
        }
        await self.col.update_one({"_id": unique_id}, {"$set": data}, upsert=True)
        # Also track user
        if user_id:
            await self.db.users.update_one({"_id": user_id}, {"$set": {"last_active": int(time.time())}}, upsert=True)
        print(f"DEBUG DB: Saved {unique_id} to MongoDB.")

    async def get_link(self, unique_id):
        link = await self.col.find_one({"_id": unique_id})
        if link:
            # Check Expiry
            expiry = link.get("expiry_date")
            if expiry and expiry < datetime.datetime.now():
                # Link Expired
                # Optional: Delete it? No, keep for now, just deny access. Or delete to save space?
                # User said "link 24hr ke baad expire ho jayega". Usually implies it stops working.
                # Let's return None to simulate 404.
                return None, None
            return link["msg_id"], link.get("backups", {})
        return None, None

    # --- SUBSCRIPTION METHODS ---

    async def get_user_data(self, user_id):
        user = await self.db.users.find_one({"_id": user_id})
        if not user:
            # Create default free user
            user = {
                "_id": user_id,
                "plan": "free",
                "plan_expiry": None,
                "daily_count": 0,
                "last_usage_date": datetime.date.today().isoformat()
            }
            await self.db.users.insert_one(user)
        return user

    async def update_user_usage(self, user_id, daily_count: int = None, date_str: str = None):
        update_data = {}
        if daily_count is not None:
            update_data["daily_count"] = daily_count
        if date_str is not None:
            update_data["last_usage_date"] = date_str
            
        if update_data:
            await self.db.users.update_one({"_id": user_id}, {"$set": update_data})

    async def set_user_plan(self, user_id, plan_name, expiry_date: datetime.datetime):
        await self.db.users.update_one(
            {"_id": user_id}, 
            {"$set": {"plan": plan_name, "plan_expiry": expiry_date}},
            upsert=True
        )

    async def get_user_links(self, user_id, limit=20):
        # Deprecated: use get_active_links for user facing apps
        cursor = self.col.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_user_active_links(self, user_id, limit=5):
        # Filter: Expiry is None OR Expiry > Now
        now = datetime.datetime.now()
        query = {
            "user_id": user_id,
            "$or": [
                {"expiry_date": None},
                {"expiry_date": {"$gt": now}}
            ]
        }
        cursor = self.col.find(query).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_all_user_active_links(self, user_id):
        # For Dashboard (ALL links)
        now = datetime.datetime.now()
        query = {
            "user_id": user_id,
            "$or": [
                {"expiry_date": None},
                {"expiry_date": {"$gt": now}}
            ]
        }
        cursor = self.col.find(query).sort("timestamp", -1)
        return await cursor.to_list(length=None)

    async def get_all_links(self):
        cursor = self.col.find().sort("timestamp", -1)
        return await cursor.to_list(length=100) # Cap at 100 for safety
        
    async def delete_link(self, unique_id):
        await self.col.delete_one({"_id": unique_id})
        
    async def count_links(self):
        return await self.col.count_documents({})

    async def get_user_total_links(self, user_id):
        return await self.col.count_documents({"user_id": user_id})
        
    async def total_users(self):
        return await self.db.users.count_documents({})

    async def get_all_users(self):
        cursor = self.db.users.find({}, {"_id": 1})
        return await cursor.to_list(length=None)

    async def ban_user(self, user_id, reason="Admin Ban"):
        await self.db.banned.update_one({"_id": user_id}, {"$set": {"reason": reason}}, upsert=True)

    async def unban_user(self, user_id):
        await self.db.banned.delete_one({"_id": user_id})

    async def is_banned(self, user_id):
        return await self.db.banned.find_one({"_id": user_id}) is not None

db = Database()
