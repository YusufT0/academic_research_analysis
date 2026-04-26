import asyncio
import os
import sys

scrapers_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scrapers_dir)

from database.connection import init_database, close_database
from backend.services.nlp_service import NLPService
from database.models import AnalysisRun

async def main():
    print("Initializing database...")
    await init_database()
    
    runs = await AnalysisRun.find({"status": "running"}).to_list()
    for run in runs:
        run.status = "failed"
        await run.save()
    
    nlp_service = NLPService()
    print("Pre-loading models in main thread...")
    # Initialize PyTorch/CUDA in main thread to avoid Windows deadlock
    _ = nlp_service.kw_model
    _ = nlp_service.embedder
    print("Models pre-loaded.")
    
    print("Starting train_clustering...")
    try:
        res = await nlp_service.train_clustering()
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        await close_database()

if __name__ == "__main__":
    asyncio.run(main())
