"""
Backend Runner Script

uvicorn ile FastAPI backend'i başlatır.
"""

import uvicorn
import sys
from pathlib import Path

# Path setup
scrapers_path = Path(__file__).parent
sys.path.insert(0, str(scrapers_path))

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Development için
        log_level="info",
    )
