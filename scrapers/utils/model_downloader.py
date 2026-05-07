"""
NLP Model Downloader

Automatically downloads sentence-transformer and cross-encoder models
to local disk on first use. Skips if models are already cached.

Usage:
    from utils.model_downloader import download_nlp_models
    download_nlp_models(model_dir, embedder_name, cross_encoder_name)
"""

import time
from pathlib import Path
from typing import List, Tuple

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger

logger = get_logger("model_downloader")


def download_nlp_models(
    model_dir: str = "nlp_models",
    embedder_name: str = "allenai/aspire-sentence-embedder",
    cross_encoder_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> List[Tuple[str, str]]:
    """
    Download NLP models to local disk if not already present.

    Args:
        model_dir: Directory to store models (resolved relative to project root)
        embedder_name: HuggingFace model name for SentenceTransformer
        cross_encoder_name: HuggingFace model name for CrossEncoder

    Returns:
        List of (status, message) tuples
    """
    base_dir = Path(__file__).parent.parent / model_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    embedder_path = base_dir / "embedder"
    cross_encoder_path = base_dir / "cross_encoder"

    results: List[Tuple[str, str]] = []
    downloaded = 0
    cached = 0
    errors = 0
    total_time = 0

    logger.header("NLP MODEL LOADER")
    logger.info(f"Model directory: {base_dir}")

    # --- Embedder ---
    logger.section("Step 1: Embedder Model")
    logger.info(f"Model: {embedder_name}")
    logger.info(f"Target: {embedder_path}")

    if (embedder_path / "config.json").exists():
        logger.success("Embedder model already cached on disk")
        results.append(("cached", "embedder"))
        cached += 1
    else:
        logger.info("Model not found locally, downloading...")
        start = time.time()
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading model from HuggingFace (this may take a while)...")
            model = SentenceTransformer(embedder_name)
            logger.info("Saving to local disk...")
            model.save(str(embedder_path))
            elapsed = time.time() - start
            total_time += elapsed
            logger.success(f"Embedder model downloaded and saved ({elapsed:.1f}s)")
            results.append(("downloaded", "embedder"))
            downloaded += 1
        except Exception as e:
            elapsed = time.time() - start
            total_time += elapsed
            logger.failed("Failed to download embedder model", e)
            results.append(("error", f"embedder: {e}"))
            errors += 1

    # --- Cross Encoder ---
    logger.section("Step 2: Cross-Encoder Model")
    logger.info(f"Model: {cross_encoder_name}")
    logger.info(f"Target: {cross_encoder_path}")

    if (cross_encoder_path / "config.json").exists():
        logger.success("Cross-encoder model already cached on disk")
        results.append(("cached", "cross_encoder"))
        cached += 1
    else:
        logger.info("Model not found locally, downloading...")
        start = time.time()
        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading model from HuggingFace (this may take a while)...")
            model = CrossEncoder(cross_encoder_name)
            logger.info("Saving to local disk...")
            model.save(str(cross_encoder_path))
            elapsed = time.time() - start
            total_time += elapsed
            logger.success(f"Cross-encoder model downloaded and saved ({elapsed:.1f}s)")
            results.append(("downloaded", "cross_encoder"))
            downloaded += 1
        except Exception as e:
            elapsed = time.time() - start
            total_time += elapsed
            logger.failed("Failed to download cross-encoder model", e)
            results.append(("error", f"cross_encoder: {e}"))
            errors += 1

    # --- Summary ---
    logger.section("Model Load Summary")
    logger.stats(
        {
            "Downloaded": downloaded,
            "Already Cached": cached,
            "Errors": errors,
            "Total Time": f"{total_time:.1f}s",
        },
        "NLP Models",
    )

    if errors > 0:
        logger.warning(
            "Some models failed to download. They will be retried on next use."
        )
    elif downloaded > 0:
        logger.success(f"All models ready ({downloaded} newly downloaded)")
    else:
        logger.success("All models already cached, nothing to download")

    return results
