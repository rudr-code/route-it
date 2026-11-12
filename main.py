"""Unified entrypoint for Route.it API & Web Dashboard.
Runs Uvicorn listening on 0.0.0.0:$PORT (default 8001).
"""
import os
import uvicorn
from api.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port)
