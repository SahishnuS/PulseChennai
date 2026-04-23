<div align="center">
  <h1>🚇 Pulse-Chennai</h1>
  <h3>A Cloud-Native, Event-Driven Geospatial Engine for Reliable Urban Transit</h3>
</div>

<p align="center">
  Pulse-Chennai is a next-generation public transit tracking system built to eliminate <strong>"Ghost Buses"</strong> and provide ultra-accurate ETAs. It upgrades legacy transit tracking by fusing unreliable AIS 140 hardware telemetry with <strong>TomTom Live Traffic APIs</strong>, Crowdsourced Passenger Wi-Fi/GPS pings, and an H3-indexed Graph Neural Network (GNN).
</p>

---

## 🏗️ System Architecture

Pulse-Chennai transitions away from traditional CRUD-based tracking into a high-throughput **Lambda Architecture** designed for geospatial intelligence:

1. **The Ingestion Pipeline (Kafka):** Raw GPS pings from buses and passengers stream into Kafka topics.
2. **Hardware Reliability Scorer:** A real-time audit module assigns health scores to AIS 140 devices based on jitter, update frequency, and impossible speeds. Devices scoring `< 0.3` are flagged as **Ghost Buses**.
3. **Collaborative Telemetry (Data Fusion):** When a bus hardware fails (Ghost Bus), the system automatically blends nearby anonymized passenger smartphone pings and TomTom Traffic flow data to estimate the actual position.
4. **Speed Layer (Redis):** Caches live spatial node states and bus locations for sub-millisecond access.
5. **Batch Layer (AWS S3 & Parquet):** Cold-stores petabytes of historical trajectories keyed by Uber H3 cells for model retraining.
6. **Spatial-Temporal GNN:** A 3-layer Graph Attention Network (GAT) with LSTM time-encoding processes H3 hexagons to predict localized bottlenecks and accurate ETAs.
7. **HMM Map-Matching:** Viterbi Dynamic Programming snaps the GNN's predicted latent coordinates back onto the actual OpenStreetMap road network.

## 💻 Tech Stack

* **ML / AI Engine:** PyTorch, PyTorch Geometric (PyG), Scikit-Learn
* **Spatial & Tracking:** Uber H3 (Hexagonal Hierarchical Geospatial Indexing), TomTom Traffic Flow API
* **Streaming & Data:** Apache Kafka, Redis, AWS S3, Apache Parquet
* **Backend:** FastAPI, Uvicorn, Pydantic
* **Frontend Dashboard:** HTML, Vanilla JS, CSS Glassmorphism, TomTom Maps Web SDK
* **Deployment:** Docker (CUDA 12.1 multi-stage), Kubernetes (K8s)

## ✨ Core Innovations

* **Ghost Bus Recovery:** Uses latent state estimation and passenger crowdsourcing to track buses even when their official GPS hardware dies.
* **H3 K-Ring Graph:** Models the city of Chennai not as disconnected roads, but as a dynamic, interconnected graph of hex cells passing congestion "messages" to their neighbors.
* **TomTom Traffic Integration:** Replaces static time-of-day guesses with live `flowSegmentData`, fetching real-time gridlock ratios across key Chennai bottlenecks.
* **Kendall Multi-Task Loss:** The AI model simultaneously predicts graph node congestion (ranking) and Bus ETA (regression), balancing its own loss weights automatically during training.

---

## 🚀 Local Development Setup

### 1. Requirements
Ensure you have Docker installed (for Redis/Kafka) and Python 3.10+.

### 2. Clone and Install
```bash
git clone https://github.com/UnisysUIP/2026-Pulse-Chennai...
cd repo/pulse_chennai
pip install -r requirements.txt
```

### 3. Environment Variables
No mandatory API keys are required for the local demo (it will run using synthetic traffic generation), but for the full experience, add your TomTom API key in `config/settings.py` or export it:
```bash
export TOMTOM_API_KEY="your_tomtom_key_here"
```

### 4. Start the Dashboard & API Server
```bash
# This starts the FastAPI backend and serves the glassmorphism UI
python -m uvicorn pulse_chennai.api.dashboard_server:app --host 0.0.0.0 --port 8001 --reload
```
Navigate to **http://localhost:8001** to view the live tracking map, TomTom traffic rings, metrics panel, and Ghost Bus detection alerts.

### 5. Run the Simulation script (ML + Graph Engine)
Looking to see the core engine crunch data? Run the demo script:
```bash
python pulse_chennai/demo_simulation.py
```
This simulates a Kafka stream, triggers a ghost bus event, performs data fusion, and runs the PyTorch SpatialGNN over the H3 graph.

---
*Architected for the Unisys Innovation Program Hackathon 2026.*
