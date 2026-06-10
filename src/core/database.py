"""
Database Connection Module — OBD-Cortex RAG
Establishes a single, pooled MongoDB Atlas connection and exposes named
collection handles for the entire application to import.
"""

import sys
from motor.motor_asyncio import AsyncIOMotorClient
import certifi
import logging
from core.config import MONGO_URI

logger = logging.getLogger(__name__)

# ==========================================
# 1. CLIENT INITIALIZATION
# ==========================================
# MongoClient manages an internal connection pool — a set of reusable TCP
# sockets to the Atlas cluster. We configure it for a lightweight edge server.

_CLIENT_OPTIONS = {
    "tlsCAFile": certifi.where(),       # CA bundle for TLS certificate verification
    "serverSelectionTimeoutMS": 5000,   # Fail fast if cluster is unreachable (5s cap)
    "maxPoolSize": 10,                  # Right-sized for a single Droplet (default 100 is excessive)
    "minPoolSize": 1,                   # Keep one socket warm to avoid cold-start latency
    "appName": "obd-cortex-api",        # Identifies this app in Atlas performance profiler
    "retryWrites": True,                # Auto-retry writes on transient network failures
    "retryReads": True,                 # Auto-retry reads on transient network failures
}

logger.info("[*] Initializing Async MongoDB Connection...")

try:
    client = AsyncIOMotorClient(MONGO_URI, **_CLIENT_OPTIONS)
except Exception as e:
    error_msg = str(e)
    if MONGO_URI:
        error_msg = error_msg.replace(MONGO_URI, "[REDACTED_URI]")
    logger.error(f"[!] Database Connection Failed: {error_msg}")
    sys.exit(1)

# ==========================================
# 2. DATABASE & COLLECTION HANDLES
# ==========================================
# These are lightweight references — no network calls or memory allocation
# occurs until an actual read/write operation is performed on them.

db = client["rag_db"]

col_telemetry = db["vehicle_telemetry"]     # Live CAN-bus telemetry snapshots
col_devices = db["devices"]                 # Pi device registration & owner pairing

async def init_db():
    """Asynchronously initialize database indexes and verify connection."""
    try:
        await client.admin.command("ping")
        logger.info("[✓] Database Connected and Pinged Successfully.")
    except Exception as e:
        logger.error(f"[!] Database Ping Failed: {e}")
        sys.exit(1)

    # Create index on telemetry collection for faster retrieval
    try:
        await col_telemetry.create_index([("vehicle_id", 1), ("timestamp", -1)])
    except Exception as e:
        logger.warning(f"[!] Warning: Could not create index on col_telemetry: {e}")

    logger.info("[✓] Database Indexes Verified.")
