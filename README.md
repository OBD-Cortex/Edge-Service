# OBD-Cortex: Edge Service

The **Edge Service** is an ultra-fast, lightweight FastAPI gateway designed specifically to ingest and route high-frequency telemetry from the OBD-Cortex Raspberry Pi IoT nodes installed in vehicles.

## Architecture Overview

1. **High Throughput Gateway**: This service acts strictly as a webhook endpoint. It handles incoming bulk CAN-bus diagnostic data, cryptographically verifies payloads, and queues them into the central database.
2. **Lean Execution**: Intentionally decoupled from the heavy SentenceTransformer and RAG systems (which live in the `MobileApp_Service`), this microservice requires minimal RAM and CPU to service hundreds of concurrent vehicle streams.
3. **Database Architecture**: Connects to the centralized MongoDB Atlas cluster. See `src/core/database.py` for connection semantics. The complex decoding of the ingested DTCs occurs asynchronously in the cloud, unblocking the edge hardware.

## Repository Structure

- `src/core/`: Configuration, database handles, and webhook security tools.
- `src/routes/`: Telemetry ingestion endpoints.
- `src/main_api.py`: The root Uvicorn entrypoint for the service.
- `systemd/`: Contains the daemon deployment configurations for Linux hosts.

## Local Development (Quick Start)

To run this telemetry gateway locally for development:
1. Ensure **Python 3.10+** is installed.
2. Create and activate a virtual environment: `python -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Copy the environment variables: `cp .env.example .env` and configure your MongoDB URI.
5. Start the development server: `uvicorn src.main_api:app --reload`

## Deployment

Please refer to `DEPLOYMENT.md` for a comprehensive, production-grade deployment guide on DigitalOcean using Nginx, Certbot, and Fish.
