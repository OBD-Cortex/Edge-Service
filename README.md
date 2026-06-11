# OBD-Cortex: Edge Ingestion Service

The **Edge Service** is an ultra-fast, lightweight FastAPI gateway designed to ingest and validate high-frequency telemetry webhooks streamed from the OBD-Cortex IoT Raspberry Pi edge devices.

---

## Service Architecture

1.  **High-Throughput Gateway:** Exposes REST webhooks for batch uploads. It focuses exclusively on payload parsing, cryptographic signature verification, and database persistence.
2.  **Timing-Safe Security:** Integrates strict timing-safe signature checking using HMAC-SHA256, timestamps window drift evaluation (+/- 5 minutes), and LRU cache-based replay protection (nonces) in `src/core/auth.py`.
3.  **Database Connection:** Connects asynchronously to MongoDB Atlas (via Motor in `src/core/database.py`). It inserts bulk records and indexes collections for fast querying.
4.  **No Version Pins:** To ensure the deployment is secure and uses the latest stable packages, `requirements.txt` does not restrict package versions. They will resolve to the latest stable packages during pip install.

---

## Repository Structure

*   `src/core/auth.py`: Implements signature validation, drift verification, and anti-replay nonce caching.
*   `src/core/database.py`: Handles MongoDB connection pooling and collections initialization.
*   `src/routes/edge.py`: Telemetry batch uploads and hardware provisioning endpoints.
*   `src/main_api.py`: Service boot configurations and CORS initialization.
*   `systemd/`: Contains the systemd configuration file templates.

---

## Local Development Setup

To boot this service locally:
1.  Verify **Python 3.10+** is installed.
2.  Initialize virtual environment:
    ```bash
    python -m venv venv && source venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Copy environment variables:
    ```bash
    cp .env.example .env
    ```
5.  Configure your MongoDB Atlas connection details inside `.env`.
6.  Start development server:
    ```bash
    uvicorn src.main_api:app --reload
    ```

---

## Deployment Guide

*   Refer to [DEPLOYMENT.md](file:///home/bodz/OBD-Cortex/Edge_Service/DEPLOYMENT.md) for production VM setup using Nginx reverse proxying, UFW firewall configurations, and systemd automation templates.
