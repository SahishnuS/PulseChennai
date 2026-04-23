"""
Standalone Dashboard Server
============================
Runs the Pulse-Chennai dashboard without requiring PyTorch/Redis/Kafka.
Serves the web UI and powers the live data APIs.

Usage:
    python -m pulse_chennai.api.dashboard_server
    # then open http://localhost:8001
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from pulse_chennai.api.dashboard_routes import router as dashboard_router

app = FastAPI(title="Pulse-Chennai Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(dashboard_router)

# Serve static files (the HTML dashboard)
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "ui")

if os.path.exists(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

@app.get("/")
async def serve_dashboard():
    index = os.path.join(_STATIC_DIR, "index.html")
    return FileResponse(index)

if __name__ == "__main__":
    uvicorn.run("pulse_chennai.api.dashboard_server:app", host="0.0.0.0", port=8001, reload=True)
