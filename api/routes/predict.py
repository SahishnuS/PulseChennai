from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import logging
import torch

from model.spatial_gnn import SpatialGNN
from graph.graph_builder import DynamicGraphBuilder
from infrastructure.feature_store import FeatureStoreClient
from graph.data_fusion import DataFusion
from model.hmm_map_matching import HMMMapMatcher
from hardware.reliability_scorer import HardwareReliabilityScorer
from model.ghost_recovery import GhostBusRecovery
from api.inference_pipeline import InferencePipeline
from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Globals for lazy loading
_pipeline = None

class PredictRequest(BaseModel):
    trip_id: str
    lat: float
    lng: float
    speed: Optional[float] = None
    heading: Optional[float] = None
    top_k: int = 3

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        try:
            device = "cuda" if torch.cuda.is_available() and settings.inference.USE_CUDA else "cpu"
            logger.info(f"Initializing InferencePipeline on {device}...")
            
            # 1. Model
            model = SpatialGNN(
                h3_feature_dim=settings.gnn.H3_FEATURE_DIM,
                bus_feature_dim=settings.gnn.BUS_FEATURE_DIM,
                hidden_dim=128,
                num_heads=4,
                num_layers=3,
                lstm_hidden=settings.gnn.LSTM_HIDDEN,
                dropout=settings.gnn.DROPOUT,
            )
            
            # Load weights if available
            import os
            model_path = os.path.join("models", "pulse_gnn_best.pt")
            if os.path.exists(model_path):
                model.load_state_dict(torch.load(model_path, map_location=device))
                logger.info(f"Loaded GNN weights from {model_path}")
            else:
                logger.warning(f"No GNN weights found at {model_path}, using untrained model.")
                
            model.eval()
            
            # 2. Components
            graph_builder = DynamicGraphBuilder()
            feature_store = FeatureStoreClient(
                host=settings.redis.REDIS_HOST,
                port=settings.redis.REDIS_PORT,
                password=settings.redis.REDIS_PASSWORD
            )
            data_fusion = DataFusion(gmaps_api_key=settings.gmaps.GMAPS_API_KEY)
            map_matcher = HMMMapMatcher()
            reliability_scorer = HardwareReliabilityScorer()
            ghost_recovery = GhostBusRecovery(model=model, graph_builder=graph_builder)
            
            # 3. Pipeline
            _pipeline = InferencePipeline(
                model=model,
                graph_builder=graph_builder,
                feature_store=feature_store,
                data_fusion=data_fusion,
                map_matcher=map_matcher,
                reliability_scorer=reliability_scorer,
                ghost_recovery=ghost_recovery,
                device=device
            )
        except Exception as e:
            logger.error(f"Failed to initialize InferencePipeline: {e}")
            raise HTTPException(status_code=500, detail="Inference Pipeline uninitialized")
    
    return _pipeline

@router.post("/predict")
async def predict_position(req: PredictRequest):
    pipeline = get_pipeline()
    try:
        result = pipeline.predict_position(
            trip_id=req.trip_id,
            lat=req.lat,
            lng=req.lng,
            speed=req.speed,
            heading=req.heading,
            top_k=req.top_k
        )
        return result
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
