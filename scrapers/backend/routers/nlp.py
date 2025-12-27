"""
Model Router

"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from analyzer.clustering_script import Clusterer


router = APIRouter(prefix="/nlp", tags=["AI Things"])

MODEL_PATH = "/home/yusuf/Desktop/academic_research_analysis/scrapers/analyzer/clustering_model.pkl"

clster = Clusterer() # Path=None because we aren't training, just loading
try:
    clster.load_state(MODEL_PATH)
    print("Successfully loaded NLP Clusterer into memory.")
except Exception as e:
    print(f"Failed to load model: {e}")

@router.get("/test_clustering", summary="Model ile anahtar kelimeye benzer makaleleri çek.")
async def fetch_similar_articles(
    keyword: str = Query(..., description="Arama yapılmak istenen anahtar kelime.")
):
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Please provide a keyword.")

    # Now this is LIGHTNING fast because 'clster' is already in RAM
    results, sim_rate = clster.test_model(keyword)
    
    return {
        "status": "success",
        "similarity_rate": float(sim_rate),
        "match_count": len(results),
        "data": results
    }
