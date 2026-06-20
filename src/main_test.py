import os
import sys
import time
import asyncio
import argparse
import datetime
import hmac
import hashlib
import json
from pathlib import Path

# Dynamically calculate the SERVICE_ROOT based on this script's location
SERVICE_ROOT = Path(__file__).resolve().parent
if SERVICE_ROOT.name == "src":
    SERVICE_ROOT = SERVICE_ROOT.parent

sys.path.insert(0, str(SERVICE_ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(SERVICE_ROOT / ".env")
except ImportError:
    pass

import core.config
from core.database import init_db, db, col_telemetry, col_devices

# Setup mock data for verification
TEST_DEVICE_ID = 999999
TEST_SECRET = "TEST_SECRET_ABC_123_XYZ"
TEST_TOKEN = "TEST_TOKEN_123"
TEST_VIN = "TEST_VIN_PERF_123"

def print_table(title, headers, rows):
    print(f"\n=== {title} ===")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
            
    header_str = " | ".join(f"{headers[i]:<{widths[i]}}" for i in range(len(headers)))
    print(header_str)
    print("-" * (sum(widths) + 3 * (len(headers) - 1)))
    
    for row in rows:
        row_str = " | ".join(f"{str(row[i]):<{widths[i]}}" for i in range(len(row)))
        print(row_str)
    print("-" * (sum(widths) + 3 * (len(headers) - 1)))

async def test_database_latency():
    print("\n[*] Running Database I/O Latency Benchmark...")
    try:
        await init_db()
    except Exception as e:
        print(f"    [-] Database connection failed: {e}")
        return

    # Warm up connection
    await db.client.admin.command("ping")

    # Generate synthetic telemetry document
    test_doc = {
        "vehicle_id": TEST_VIN,
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "mil_active": False,
        "dtc_count": 0,
        "confirmed_dtcs": [],
        "pending_dtcs": [],
        "system_status": "healthy",
        "scan_summary": "Database Performance Test Document"
    }

    # 1. Single Write Latency
    print("[*] Benchmarking single document inserts (10 iterations)...")
    write_latencies = []
    inserted_ids = []
    for _ in range(10):
        start = time.time()
        result = await col_telemetry.insert_one(test_doc.copy())
        latency = (time.time() - start) * 1000
        write_latencies.append(latency)
        inserted_ids.append(result.inserted_id)

    # 2. Batch Write Latency
    print("[*] Benchmarking batch document inserts (5 batches of 20 documents)...")
    batch_latencies = []
    for _ in range(5):
        batch = [test_doc.copy() for _ in range(20)]
        start = time.time()
        result = await col_telemetry.insert_many(batch)
        latency = (time.time() - start) * 1000
        batch_latencies.append(latency)
        inserted_ids.extend(result.inserted_ids)

    # 3. Read Latency (Querying our inserts)
    print("[*] Benchmarking query read latency (10 iterations)...")
    read_latencies = []
    for _ in range(10):
        start = time.time()
        results = await col_telemetry.find({"vehicle_id": TEST_VIN}).to_list(length=100)
        latency = (time.time() - start) * 1000
        read_latencies.append(latency)

    # 4. Clean up insertions
    print("[*] Cleaning up database test records...")
    start_delete = time.time()
    await col_telemetry.delete_many({"vehicle_id": TEST_VIN})
    delete_latency = (time.time() - start_delete) * 1000

    # Display results
    headers = ["Operation", "Min (ms)", "Max (ms)", "Average (ms)", "Throughput"]
    
    avg_write = sum(write_latencies) / len(write_latencies)
    tput_write = 1000 / avg_write
    
    avg_batch = sum(batch_latencies) / len(batch_latencies)
    tput_batch = 100 / (avg_batch * 5 / 1000) # total docs / total time

    avg_read = sum(read_latencies) / len(read_latencies)
    tput_read = 1000 / avg_read

    rows = [
        ["Single Write (1 doc)", f"{min(write_latencies):.2f}", f"{max(write_latencies):.2f}", f"{avg_write:.2f}", f"{tput_write:.2f} docs/sec"],
        ["Batch Write (20 docs)", f"{min(batch_latencies):.2f}", f"{max(batch_latencies):.2f}", f"{avg_batch:.2f}", f"{tput_batch:.2f} docs/sec"],
        ["Query (find)", f"{min(read_latencies):.2f}", f"{max(read_latencies):.2f}", f"{avg_read:.2f}", f"{tput_read:.2f} queries/sec"],
        ["Cleanup (delete_many)", "-", "-", f"{delete_latency:.2f}", "-"]
    ]
    print_table("Database Operation Latencies", headers, rows)

def test_hmac_performance():
    print("\n[*] Running HMAC Signature Validation Benchmark...")
    
    payload = {
        "vehicle_id": TEST_VIN,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active": False,
        "dtc_count": 0,
        "confirmed_dtcs": [],
        "pending_dtcs": [],
        "system_status": "healthy"
    }
    body_bytes = json.dumps(payload).encode('utf-8')
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    signed_data = timestamp.encode('utf-8') + body_bytes

    print("[*] Benchmarking HMAC validation rate (10,000 iterations)...")
    
    start_time = time.time()
    iterations = 10000
    for _ in range(iterations):
        # 1. Sign (Sender side)
        sig = hmac.new(TEST_SECRET.encode('utf-8'), signed_data, hashlib.sha256).hexdigest()
        
        # 2. Verify (Receiver side)
        expected_sig = hmac.new(TEST_SECRET.encode('utf-8'), signed_data, hashlib.sha256).hexdigest()
        hmac.compare_digest(sig, expected_sig)
        
    duration = time.time() - start_time
    avg_latency_us = (duration / iterations) * 1000000
    ops_per_sec = iterations / duration

    headers = ["Metric", "Value"]
    rows = [
        ["Total Validations", f"{iterations}"],
        ["Total Duration (s)", f"{duration:.4f}"],
        ["Avg Validation Latency (us)", f"{avg_latency_us:.2f}"],
        ["Verification Rate (signatures/sec)", f"{ops_per_sec:.2f}"]
    ]
    print_table("HMAC Authentication Performance", headers, rows)

async def test_api_endpoints():
    print("\n[*] Running API Endpoints Performance Test...")
    try:
        from fastapi.testclient import TestClient
        from main_api import app
    except ImportError as e:
        print(f"    [-] FastAPI TestClient cannot be initialized (missing fastapi/httpx): {e}")
        return

    # Setup database with test device key
    try:
        await init_db()
        # Clean existing
        await col_devices.delete_many({"device_id": TEST_DEVICE_ID})
        await col_devices.insert_one({
            "device_token": TEST_TOKEN,
            "device_id": TEST_DEVICE_ID,
            "device_secret": TEST_SECRET,
            "vin": TEST_VIN,
            "status": "paired"
        })
    except Exception as e:
        print(f"    [-] Pre-test DB setup failed: {e}")
        return

    client = TestClient(app)

    # 1. Ingestion Endpoint benchmark
    print("[*] Benchmarking POST /api/telemetry upload (10 iterations)...")
    payload = [{
        "vehicle_id": TEST_VIN,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active": False,
        "dtc_count": 0,
        "confirmed_dtcs": [],
        "pending_dtcs": [],
        "system_status": "healthy"
    }]
    
    endpoint_latencies = []
    success_count = 0
    
    for _ in range(10):
        # Generate dynamic signature
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        body_bytes = json.dumps(payload).encode('utf-8')
        signed_data = timestamp.encode('utf-8') + body_bytes
        sig = hmac.new(TEST_SECRET.encode('utf-8'), signed_data, hashlib.sha256).hexdigest()
        
        headers = {
            "X-Device-ID": str(TEST_DEVICE_ID),
            "X-Timestamp": timestamp,
            "X-Signature": sig
        }
        
        start = time.time()
        response = client.post("/api/telemetry", json=payload, headers=headers)
        latency = (time.time() - start) * 1000
        endpoint_latencies.append(latency)
        
        if response.status_code == 200:
            success_count += 1
        else:
            print(f"        [-] Upload failed with status {response.status_code}: {response.text}")
            
    # Cleanup DB again
    await col_devices.delete_many({"device_id": TEST_DEVICE_ID})
    await col_telemetry.delete_many({"vehicle_id": TEST_VIN})

    # Summary
    headers = ["Metric", "Value"]
    avg_latency = sum(endpoint_latencies) / len(endpoint_latencies) if endpoint_latencies else 0
    rows = [
        ["Target Endpoint", "POST /api/telemetry"],
        ["Successful Ingestions", f"{success_count}/10"],
        ["Min Latency (ms)", f"{min(endpoint_latencies):.2f}"],
        ["Max Latency (ms)", f"{max(endpoint_latencies):.2f}"],
        ["Average Latency (ms)", f"{avg_latency:.2f}"]
    ]
    print_table("API Ingestion End-to-End Metrics (In-Process)", headers, rows)

def main():
    parser = argparse.ArgumentParser(description="Edge-Service Performance Evaluation")
    parser.add_argument("--test", choices=['db', 'hmac', 'api', 'all'], default='all', help="Select specific test to run")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()

    print("==================================================")
    print(" OBD-Cortex Ingestion Service Performance Benchmarks")
    print("==================================================")

    if args.test in ['db', 'all']:
        loop.run_until_complete(test_database_latency())
    if args.test in ['hmac', 'all']:
        test_hmac_performance()
    if args.test in ['api', 'all']:
        loop.run_until_complete(test_api_endpoints())

    print("\n[+] Performance evaluation completed successfully.")

if __name__ == "__main__":
    main()
