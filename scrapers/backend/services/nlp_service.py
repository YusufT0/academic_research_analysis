"""
NLP Service
Clustering ve embedding iş mantığı
"""

import re
import joblib

# import pickle
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING, Union, Set
from pymongo import UpdateOne
from beanie import PydanticObjectId
from collections import Counter
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.models import Article, ArticleEmbedding, Cluster, AnalysisRun
from database.repositories import (
    ArticleRepository,
    EmbeddingRepository,
    ClusterRepository,
    AnalysisRunRepository,
)
from backend.core.config import settings
from backend.schemas.article import ArticleNLPProjection
from utils.logger import get_logger
from collections import defaultdict

logger = get_logger("nlp_service")

# Ağır kütüphaneler lazy import edilir — modül yüklenirken değil,
# NLPService ilk kullanıldığında yüklenir.
np = None
# spacy = None  # unused — commented out
SentenceTransformer = None
CrossEncoder = None
umap = None
hdbscan = None
cosine_similarity = None
KeyBERT = None
TfidfVectorizer = None


def _ensure_nlp_imports():
    """Ağır NLP/ML kütüphanelerini ilk ihtiyaç anında yükle."""
    global \
        np, \
        SentenceTransformer, \
        CrossEncoder, \
        umap, \
        hdbscan, \
        cosine_similarity, \
        KeyBERT, \
        TfidfVectorizer
    if np is not None:
        return  # Zaten yüklendi
    import numpy as _np

    # import spacy as _spacy  # unused — commented out
    from sentence_transformers import SentenceTransformer as _ST, CrossEncoder as _CE
    import umap as _umap
    import hdbscan as _hdbscan
    from sklearn.metrics.pairwise import cosine_similarity as _cs
    from sklearn.feature_extraction.text import TfidfVectorizer as _tv
    from keybert import KeyBERT as _KB

    np = _np
    # spacy = _spacy  # unused — commented out
    SentenceTransformer = _ST
    CrossEncoder = _CE
    umap = _umap
    hdbscan = _hdbscan
    cosine_similarity = _cs
    KeyBERT = _KB
    TfidfVectorizer = _tv
    logger.info("NLP kütüphaneleri yüklendi")


class NLPService:
    """
    NLP Service

    Clustering, embedding ve benzerlik araması işlemlerini yönetir.
    Singleton pattern ile tek instance kullanılır.
    """

    _instance: Optional["NLPService"] = None
    PREFIX_DATES = {
        "january": "1",
        "february": "2",
        "march": "3",
        "april": "4",
        "may": "5",
        "june": "6",
        "july": "7",
        "august": "8",
        "september": "9",
        "october": "10",
        "november": "11",
        "december": "12",
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Repositories
        self.article_repo = ArticleRepository()
        self.embedding_repo = EmbeddingRepository()
        self.cluster_repo = ClusterRepository()
        self.analysis_repo = AnalysisRunRepository()

        # Models (lazy loading)
        self._embedder = None
        self._cross_encoder = None
        # self._cleaner_guy = None  # unused — spacy model commented out
        self._kw_model = None
        # Cached data for fast search
        self._cached_version = None
        self._cached_centroids = None
        self._cached_cluster_ids = None
        # DEPRECATED: Methods now use parameters/returns instead of these.
        # Kept as None for backward compatibility during migration — remove later.
        self.articles = None
        self.relevant_keywords = None
        self._initialized = True

        # Download/check models on disk at startup (always runs)
        self._ensure_models_downloaded()

        if not settings.nlp_lazy_init:
            logger.info("NLP Service tam ön yükleme yapıyor (NLP_LAZY_INIT=False)")
            _ensure_nlp_imports()
            try:
                _ = self.embedder
                _ = self.cross_encoder
                # _ = self.cleaner_guy  # unused — spacy model commented out
                _ = self.kw_model
            except Exception as e:
                logger.warning(f"NLP Service ön yükleme hatası: {e}")
        else:
            logger.info(
                "NLP Service initialized (lazy mode — modeller ilk kullanımda RAM'e yüklenecek)"
            )

    def _ensure_models_downloaded(self):
        """Download NLP models to local disk if not already cached."""
        from utils.model_downloader import download_nlp_models

        results = download_nlp_models(
            model_dir=settings.nlp_model_dir,
            embedder_name=settings.nlp_embedder_model,
            cross_encoder_name=settings.nlp_cross_encoder_model,
        )
        for status, name in results:
            if status == "downloaded":
                logger.info(f"NLP model downloaded: {name}")
            elif status == "cached":
                logger.debug(f"NLP model already cached: {name}")
            elif status == "error":
                logger.warning(f"NLP model download failed: {name}")

    @property
    def embedder(self) -> "SentenceTransformer":
        """Lazy load embedder model from local disk into RAM"""
        if self._embedder is None:
            _ensure_nlp_imports()
            local_path = settings.nlp_embedder_path
            logger.info(f"Loading embedder from local: {local_path}")
            try:
                self._embedder = SentenceTransformer(str(local_path), device="cuda")
            except Exception:
                logger.warning("Cannot link to GPU. Switching to CPU")
                self._embedder = SentenceTransformer(str(local_path))

        return self._embedder

    @property
    def cross_encoder(self) -> "CrossEncoder":
        """Lazy load cross encoder model from local disk into RAM"""
        if self._cross_encoder is None:
            _ensure_nlp_imports()
            local_path = settings.nlp_cross_encoder_path
            logger.info(f"Loading cross encoder from local: {local_path}")
            self._cross_encoder = CrossEncoder(str(local_path))
        return self._cross_encoder

    @cross_encoder.setter
    def cross_encoder(self, value):
        self._cross_encoder = value

    # @property
    # def cleaner_guy(self):
    #     """Lazy load spacy model"""
    #     if self._cleaner_guy is None:
    #         _ensure_nlp_imports()
    #         logger.info("Loading spacy model: en_core_web_sm")
    #         self._cleaner_guy = spacy.load("en_core_web_sm")
    #     return self._cleaner_guy

    # @cleaner_guy.setter
    # def cleaner_guy(self, value):
    #     self._cleaner_guy = value

    @property
    def kw_model(self):
        """Lazy load KeyBERT model using local embedder"""
        if self._kw_model is None:
            _ensure_nlp_imports()
            local_path = settings.nlp_embedder_path
            logger.info(f"Loading KeyBERT with local model: {local_path}")
            self._kw_model = KeyBERT(model=str(local_path))
        return self._kw_model

    @kw_model.setter
    def kw_model(self, value):
        self._kw_model = value

    def _clean_text(self, text: str) -> str:
        """Metni NLP için temizle"""
        text = str(text).lower()
        text = re.sub(r"[^a-zçğıöşü\s]", " ", text)
        return " ".join(text.split())

    async def _resolve_model_db_first(self, auto_train: bool = False) -> Optional[str]:
        """
        Model kaynağını belirle - DB öncelikli

        1. DB'de analiz varsa -> model_version döndür
        2. PKL varsa -> "pkl_legacy" döndür
        3. auto_train=True ise -> eğitim başlat
        4. Hata fırlat
        """
        # 1. Önce DB'ye bak
        latest_run = await self.analysis_repo.get_latest_completed()
        if latest_run:
            logger.info(f"DB modeli kullanılıyor: {latest_run.model_version}")
            return latest_run.model_version

        # 2. DB'de yoksa PKL'yi dene
        # if self._load_pkl_model():
        #     logger.info("DB'de analiz yok, PKL model kullanılıyor (prefer_pkl=false)")
        #     return "pkl_legacy"

        # 3. İkisi de yoksa
        if auto_train:
            logger.info("Model bulunamadı, otomatik eğitim başlatılıyor...")
            train_result = await self.train_clustering()
            return train_result["model_version"]

        raise ValueError(
            "Model bulunamadı. DB'de analiz veya PKL dosyası yok. "
            "auto_train=True ile otomatik eğitim başlatabilirsiniz "
            "veya /nlp/analyze endpoint'ini kullanın."
        )

    async def train_clustering(
        self, model_version: Optional[str] = None, min_abstract_length: int = 50
    ) -> Dict[str, Any]:
        """
        Yeni clustering modeli eğit ve sonuçları DB'ye kaydet

        Args:
            model_version: Model versiyon etiketi (None ise otomatik)
            min_abstract_length: Minimum abstract uzunluğu

        Returns:
            Eğitim sonuç istatistikleri
        """
        # Version oluştur
        _ensure_nlp_imports()
        if not model_version:
            model_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        logger.section(f"NLP Training Started - {model_version}")

        # Mevcut analiz kontrolü
        existing_run = await self.analysis_repo.get_running()
        if existing_run:
            raise ValueError(
                f"Bir analiz zaten çalışıyor: {existing_run.model_version}"
            )

        # Analiz kaydı oluştur
        run = await self.analysis_repo.create_run(
            model_version=model_version,
            embedder_model=settings.nlp_embedder_model,
            umap_n_neighbors=settings.nlp_umap_n_neighbors,
            umap_n_components=settings.nlp_umap_n_components,
            min_cluster_size=settings.nlp_min_cluster_size_all,
            min_samples=settings.nlp_min_samples_all,
        )
        await self.analysis_repo.start_run(run)

        try:
            # 1. Makaleleri getir
            logger.info("Fetching articles from database...")
            articles = (
                await Article.find({"abstract": {"$exists": True, "$ne": None}})
                .project(ArticleNLPProjection)
                .to_list()
            )

            # Abstract'ı olan ve yeterli uzunlukta olanları filtrele
            valid_articles = []
            for article in articles:
                if article.abstract and len(article.abstract) >= min_abstract_length:
                    valid_articles.append(article)

            if len(valid_articles) < settings.nlp_min_cluster_size_all:
                raise ValueError(
                    f"Yetersiz makale sayısı: {len(valid_articles)} "
                    f"(minimum: {settings.nlp_min_cluster_size_all})"
                )

            logger.info(f"Found {len(valid_articles)} valid articles")

            # 2. Metinleri temizle ve embedding oluştur
            logger.info(
                f"Extracting keywords for {len(valid_articles)} articles in batch..."
            )
            abstracts = [article.abstract for article in valid_articles]

            # Windows CUDA Deadlock Fix: Initialize PyTorch models in the main thread
            _ = self.kw_model
            _ = self.embedder

            def _extract_batch():
                import torch
                from tqdm import tqdm
                from keyphrase_vectorizers import KeyphraseCountVectorizer

                results = []
                batch_size = 32
                vectorizer = KeyphraseCountVectorizer()

                # Process in chunks to provide a progress bar
                for i in tqdm(
                    range(0, len(abstracts), batch_size), desc="Extracting keywords"
                ):
                    chunk = abstracts[i : i + batch_size]
                    chunk_res = self.kw_model.extract_keywords(
                        chunk,
                        vectorizer=vectorizer,
                        use_mmr=False,
                        top_n=3,
                    )
                    if i % 200 == 0 and torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    # KeyBERT returns List[Tuple] for single doc, List[List[Tuple]] for multiple
                    if len(chunk) == 1:
                        results.append(chunk_res)
                    else:
                        results.extend(chunk_res)
                return results

            batch_extracted = await asyncio.to_thread(_extract_batch)
            logger.success("Keywords extracted.")

            all_article_kws = [[item[0] for item in ext] for ext in batch_extracted]

            logger.info("Cleaning texts and arranging dates...")
            cleaned_texts = []
            article_ids = []
            article_keywords = []
            article_dates = []
            article_publishers = []
            article_journals = []
            article_objects = []

            for i, article in enumerate(valid_articles):
                cleaned = self._clean_text(article.abstract)
                kws = all_article_kws[i]
                date = await self._arrange_date(article.publication_date)
                if date == None:
                    continue
                if cleaned:
                    cleaned_texts.append(cleaned)
                    article_ids.append(article.id)
                    article_keywords.append(kws)
                    article_dates.append(str(date))
                    article_publishers.append(article.publisher)
                    article_journals.append(article.journal_id)
                    article_objects.append(article)

            # Merge keywords with original text for richer embeddings
            texts_for_embedding = [
                f"{article.abstract} Keywords: {', '.join(kws)}"
                for article, kws in zip(article_objects, article_keywords)
            ]

            # Embedding
            def _encode():
                return self.embedder.encode(
                    texts_for_embedding, batch_size=32, show_progress_bar=True
                )

            embeddings_full = await asyncio.to_thread(_encode)
            logger.success(
                f"Generated {len(embeddings_full)} embeddings (dim: {embeddings_full.shape[1]})"
            )

            # 3. UMAP ile boyut indirgeme
            logger.info("Reducing dimensions with UMAP...")

            def _reduce():
                import torch

                reducer = umap.UMAP(
                    n_neighbors=settings.nlp_umap_n_neighbors,
                    n_components=settings.nlp_umap_n_components,
                    metric="cosine",
                    n_jobs=-1,
                )
                reduced = reducer.fit_transform(embeddings_full)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                return reducer, reduced

            umap_reducer, embeddings_reduced = await asyncio.to_thread(_reduce)
            logger.success(f"Reduced to {embeddings_reduced.shape[1]} dimensions")

            # Save fitted UMAP model to disk
            models_dir = Path(__file__).parent.parent.parent / "nlp_models"
            models_dir.mkdir(parents=True, exist_ok=True)
            umap_path = models_dir / f"umap_{model_version}.joblib"
            joblib.dump(umap_reducer, umap_path)
            logger.info(f"UMAP model saved to {umap_path}")
            # Saving Embeddings.
            await self.embedding_repo.delete_by_model_version(model_version)
            await self.cluster_repo.delete_by_model_version(model_version)
            logger.info("Saving embeddings to database...")
            embedding_docs = []
            for i, article_id in enumerate(article_ids):
                embedding_doc = ArticleEmbedding(
                    article_id=article_id,
                    embedding_full=embeddings_full[i].tolist(),
                    embedding_reduced=embeddings_reduced[i].tolist(),
                    text_cleaned=cleaned_texts[i],
                    model_version=model_version,
                    article_dates=article_dates[i],
                    article_keywords=article_keywords[i],
                    article_publisher=article_publishers[i],
                    article_journal_id=article_journals[i],
                )
                embedding_docs.append(embedding_doc)

            batch_size_db = 1000
            for i in range(0, len(embedding_docs), batch_size_db):
                await self.embedding_repo.bulk_create(
                    embedding_docs[i : i + batch_size_db]
                )
            logger.success(f"Saved {len(embedding_docs)} embeddings")

            # 4. HDBSCAN ile clustering

            # 5. Eski verileri temizle (aynı versiyon varsa)

            def run_hdbscan(
                indices: list[int],
                min_cluster_size: int,
                min_samples: int,
                save_path: str = None,
            ):
                import torch

                subset_reduced = embeddings_reduced[indices]
                clusterer = hdbscan.HDBSCAN(
                    min_cluster_size=min_cluster_size,
                    min_samples=min_samples,
                    core_dist_n_jobs=2,
                    prediction_data=True,
                )
                labels = clusterer.fit_predict(subset_reduced)
                if save_path:
                    joblib.dump(clusterer, save_path)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                return labels

            # --- Clustering for All ---
            logger.info("Clustering for All.")
            all_indices = list(range(len(article_ids)))
            hdbscan_all_path = str(models_dir / f"hdbscan_all_{model_version}.joblib")
            from database.connection import get_database

            await get_database().client.admin.command("ping")
            all_labels = await asyncio.to_thread(
                run_hdbscan,
                all_indices,
                settings.nlp_min_cluster_size_all,
                settings.nlp_min_samples_all,
                hdbscan_all_path,
            )
            n_clusters_all = len(set(all_labels)) - (1 if -1 in all_labels else 0)
            logger.success(f"Found {n_clusters_all} clusters for all.")
            logger.info(f"HDBSCAN (all) model saved to {hdbscan_all_path}")

            # Build extracted_keywords_map: article_id -> extracted keywords from training
            extracted_keywords_map = {
                article_ids[i]: article_keywords[i] for i in range(len(article_ids))
            }

            cluster_docs_all = await self._create_cluster_documents(
                cluster_labels=all_labels,
                embeddings_full=embeddings_full[all_indices],
                embeddings_reduced=embeddings_reduced[all_indices],
                article_ids=[article_ids[i] for i in all_indices],
                valid_articles=article_objects,
                model_version=model_version,
                cluster_type="all",
                group_id=None,
                extracted_keywords_map=extracted_keywords_map,
            )
            await self.cluster_repo.bulk_create(cluster_docs_all)
            logger.success(f"Saved {len(cluster_docs_all)} clusters for all.")

            # --- Clustering for Publishers ---
            logger.info("Clustering for Publishers.")
            publisher_groups: dict[str, list[int]] = {}
            for i, source in enumerate(article_publishers):
                publisher_groups.setdefault(source, []).append(i)

            cluster_docs_publishers = []
            for pub_idx, (publisher, indices) in enumerate(publisher_groups.items()):
                if len(indices) == 1:
                    idx = indices[0]
                    cluster_docs_publishers.append(
                        Cluster(
                            cluster_id=0,
                            centroid_full=embeddings_full[idx].tolist(),
                            centroid_reduced=embeddings_reduced[idx].tolist(),
                            article_ids=[article_ids[idx]],
                            label=None,
                            top_keywords=[],
                            sample_titles=[article_objects[idx].title]
                            if article_objects[idx].title
                            else [],
                            article_count=1,
                            cluster_type="publisher",
                            group_id=publisher,
                            model_version=model_version,
                        )
                    )
                    continue
                if len(indices) < settings.nlp_min_cluster_size_publisher:
                    logger.warning(
                        f"Skipping publisher '{publisher}': only {len(indices)} articles."
                    )
                    continue
                await asyncio.sleep(0)
                if pub_idx % 3 == 0:
                    from database.connection import get_database

                    await get_database().client.admin.command("ping")
                labels = await asyncio.to_thread(
                    run_hdbscan,
                    indices,
                    settings.nlp_min_cluster_size_publisher,
                    settings.nlp_min_samples_publisher,
                )
                docs = await self._create_cluster_documents(
                    cluster_labels=labels,
                    embeddings_full=embeddings_full[indices],
                    embeddings_reduced=embeddings_reduced[indices],
                    article_ids=[article_ids[i] for i in indices],
                    valid_articles=[article_objects[i] for i in indices],
                    model_version=model_version,
                    cluster_type="publisher",
                    group_id=publisher,
                    extracted_keywords_map=extracted_keywords_map,
                )
                cluster_docs_publishers.extend(docs)

            await self.cluster_repo.bulk_create(cluster_docs_publishers)
            logger.success(
                f"Saved {len(cluster_docs_publishers)} clusters for publishers."
            )

            # --- Clustering for Journals ---
            logger.info("Clustering for Journals.")
            journal_groups: dict[str, list[int]] = {}
            for i, journal_id in enumerate(article_journals):
                journal_groups.setdefault(str(journal_id), []).append(i)

            cluster_docs_journals = []
            for jrn_idx, (journal_id, indices) in enumerate(journal_groups.items()):
                if len(indices) == 1:
                    idx = indices[0]
                    cluster_docs_journals.append(
                        Cluster(
                            cluster_id=0,
                            centroid_full=embeddings_full[idx].tolist(),
                            centroid_reduced=embeddings_reduced[idx].tolist(),
                            article_ids=[article_ids[idx]],
                            label=None,
                            top_keywords=[],
                            sample_titles=[article_objects[idx].title]
                            if article_objects[idx].title
                            else [],
                            article_count=1,
                            cluster_type="journal",
                            group_id=journal_id,
                            model_version=model_version,
                        )
                    )
                    continue
                if len(indices) < settings.nlp_min_cluster_size_journal:
                    logger.warning(
                        f"Skipping journal '{journal_id}': only {len(indices)} articles."
                    )
                    continue
                await asyncio.sleep(0)
                if jrn_idx % 3 == 0:
                    from database.connection import get_database

                    await get_database().client.admin.command("ping")
                labels = await asyncio.to_thread(
                    run_hdbscan,
                    indices,
                    settings.nlp_min_cluster_size_journal,
                    settings.nlp_min_samples_journal,
                )
                docs = await self._create_cluster_documents(
                    cluster_labels=labels,
                    embeddings_full=embeddings_full[indices],
                    embeddings_reduced=embeddings_reduced[indices],
                    article_ids=[article_ids[i] for i in indices],
                    valid_articles=[article_objects[i] for i in indices],
                    model_version=model_version,
                    cluster_type="journal",
                    group_id=journal_id,
                    extracted_keywords_map=extracted_keywords_map,
                )
                cluster_docs_journals.extend(docs)

            await self.cluster_repo.bulk_create(cluster_docs_journals)
            logger.success(f"Saved {len(cluster_docs_journals)} clusters for journals.")

            # 8. Analiz kaydını tamamla

            n_noise_all = int((all_labels == -1).sum())

            await self.analysis_repo.complete_run(
                run=run,
                total_articles=len(valid_articles),
                total_clusters=n_clusters_all,
                noise_count=n_noise_all,
            )

            # Cache'i güncelle
            await self._load_cache(model_version)

            logger.section("Training Completed")

            return {
                "model_version": model_version,
                "total_articles": len(valid_articles),
                "total_clusters": n_clusters_all,
                "noise_count": n_noise_all,
                "embedding_dim_full": embeddings_full.shape[1],
                "embedding_dim_reduced": embeddings_reduced.shape[1],
                "status": "completed",
            }

        except Exception as e:
            await self.analysis_repo.fail_run(run, str(e))
            logger.error(f"Training failed: {e}")
            raise

    async def assign_new_articles(
        self,
        model_version: Optional[str] = None,
        min_abstract_length: int = 50,
        journal_ids: Optional[List[PydanticObjectId]] = None,
    ) -> Dict[str, Any]:
        """
        Incremental clustering: yeni scrape edilen (henüz embedding'i olmayan)
        makaleleri mevcut UMAP + HDBSCAN modellerine göre kümelere atar.

        1. ArticleEmbedding koleksiyonunda ID'si bulunmayan Article'ları getirir ($nin).
        2. Embedding üretir.
        3. Kaydedilmiş UMAP reducer ile transform() yapar.
        4. Kaydedilmiş HDBSCAN clusterer ile approximate_predict() yapar.
        5. Yeni ArticleEmbedding dokümanlarını ve cluster güncellemelerini DB'ye yazar.
        """
        _ensure_nlp_imports()

        # Resolve model version
        if not model_version:
            model_version = await self._resolve_model_db_first(auto_train=False)

        logger.section(f"Incremental Assignment Started - {model_version}")

        models_dir = Path(__file__).parent.parent.parent / "nlp_models"
        umap_path = models_dir / f"umap_{model_version}.joblib"
        hdbscan_path = models_dir / f"hdbscan_all_{model_version}.joblib"

        if not umap_path.exists() or not hdbscan_path.exists():
            raise FileNotFoundError(
                f"Saved models not found for version '{model_version}'. "
                f"Expected: {umap_path}, {hdbscan_path}. "
                "Run train_clustering first to create the models."
            )

        # 1. Fetch article IDs that already have embeddings for this version
        logger.info("Fetching existing embedding article IDs...")
        existing_embeddings = await ArticleEmbedding.find(
            {"model_version": model_version}, projection_model=None
        ).to_list()
        existing_article_ids = [emb.article_id for emb in existing_embeddings]
        logger.info(f"Found {len(existing_article_ids)} articles already embedded.")

        # 2. Fetch new articles: have abstract, ID not in existing embeddings
        logger.info("Querying for new (un-embedded) articles...")
        article_query: Dict[str, Any] = {
            "abstract": {"$exists": True, "$ne": None},
            "_id": {"$nin": existing_article_ids},
        }
        if journal_ids:
            article_query["journal_id"] = {"$in": journal_ids}
        new_articles = (
            await Article.find(article_query).project(ArticleNLPProjection).to_list()
        )

        # Filter by abstract length
        valid_new = [
            a
            for a in new_articles
            if a.abstract and len(a.abstract) >= min_abstract_length
        ]

        if not valid_new:
            logger.info("No new articles to assign.")
            return {
                "model_version": model_version,
                "new_articles_found": 0,
                "assigned": 0,
                "noise": 0,
                "total_embeddings_saved": 0,
                "status": "no_new_articles",
                "affected_clusters": [],
            }

        logger.info(f"Found {len(valid_new)} new articles to assign.")

        # 3. Extract keywords for new articles
        logger.info("Extracting keywords for new articles...")
        abstracts = [a.abstract for a in valid_new]
        _ = self.kw_model
        _ = self.embedder

        def _extract_batch():
            import torch
            from tqdm import tqdm

            results = []
            batch_size = 32
            for i in tqdm(
                range(0, len(abstracts), batch_size), desc="Extracting keywords (new)"
            ):
                chunk = abstracts[i : i + batch_size]
                chunk_res = self.kw_model.extract_keywords(
                    chunk,
                    keyphrase_ngram_range=(1, 2),
                    stop_words="english",
                    use_mmr=True,
                    diversity=0.2,
                    top_n=5,
                )
                if i % 200 == 0 and torch.cuda.is_available():
                    torch.cuda.empty_cache()
                if len(chunk) == 1:
                    results.append(chunk_res)
                else:
                    results.extend(chunk_res)
            return results

        batch_extracted = await asyncio.to_thread(_extract_batch)
        all_article_kws = [[item[0] for item in ext] for ext in batch_extracted]
        logger.success("Keywords extracted for new articles.")

        # 4. Clean texts, arrange dates, build parallel lists
        logger.info("Cleaning texts and arranging dates for new articles...")
        cleaned_texts = []
        article_ids = []
        article_keywords = []
        article_dates = []
        article_publishers = []
        article_journals = []

        for i, article in enumerate(valid_new):
            cleaned = self._clean_text(article.abstract)
            kws = all_article_kws[i]
            date = await self._arrange_date(article.publication_date)
            if date is None:
                continue
            if cleaned:
                cleaned_texts.append(cleaned)
                article_ids.append(article.id)
                article_keywords.append(kws)
                article_dates.append(str(date))
                article_publishers.append(article.publisher)
                article_journals.append(article.journal_id)

        if not cleaned_texts:
            logger.info("No valid new articles after cleaning.")
            return {
                "model_version": model_version,
                "new_articles_found": len(valid_new),
                "assigned": 0,
                "noise": 0,
                "total_embeddings_saved": 0,
                "status": "no_valid_articles_after_cleaning",
                "affected_clusters": [],
            }

        # 5. Generate full embeddings (keywords + raw text)
        texts_for_embedding = [
            f"{article.abstract} Keywords: {', '.join(kws)}"
            for article, kws in zip(valid_new, article_keywords)
        ]
        logger.info(
            f"Generating embeddings for {len(texts_for_embedding)} new articles..."
        )

        def _encode():
            import torch

            result = self.embedder.encode(
                texts_for_embedding, batch_size=32, show_progress_bar=True
            )
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return result

        embeddings_full = await asyncio.to_thread(_encode)
        logger.success(
            f"Generated {len(embeddings_full)} embeddings (dim: {embeddings_full.shape[1]})"
        )

        # 6. Load saved UMAP and project into existing space
        logger.info(f"Loading UMAP model from {umap_path}...")

        def _transform():
            reducer = joblib.load(umap_path)
            return reducer.transform(embeddings_full)

        embeddings_reduced = await asyncio.to_thread(_transform)
        logger.success(
            f"Projected new articles to {embeddings_reduced.shape[1]} dimensions."
        )

        # 7. Load saved HDBSCAN and approximate_predict
        logger.info(f"Loading HDBSCAN model from {hdbscan_path}...")

        def _predict():
            import hdbscan as _hdbscan

            clusterer = joblib.load(hdbscan_path)
            labels, strengths = _hdbscan.approximate_predict(
                clusterer, embeddings_reduced
            )
            return labels, strengths

        cluster_labels, cluster_strengths = await asyncio.to_thread(_predict)
        n_assigned = int((cluster_labels != -1).sum())
        n_noise = int((cluster_labels == -1).sum())
        logger.success(
            f"Assigned {n_assigned} articles to clusters, {n_noise} marked as noise."
        )

        # 8. Save new ArticleEmbedding documents
        logger.info("Saving new embeddings to database...")
        embedding_docs = []
        for i, art_id in enumerate(article_ids):
            embedding_doc = ArticleEmbedding(
                article_id=art_id,
                embedding_full=embeddings_full[i].tolist(),
                embedding_reduced=embeddings_reduced[i].tolist(),
                text_cleaned=cleaned_texts[i],
                model_version=model_version,
                article_dates=article_dates[i],
                article_keywords=article_keywords[i],
                article_publisher=article_publishers[i],
                article_journal_id=article_journals[i],
            )
            embedding_docs.append(embedding_doc)

        batch_size_db = 1000
        for i in range(0, len(embedding_docs), batch_size_db):
            await self.embedding_repo.bulk_create(embedding_docs[i : i + batch_size_db])
        logger.success(f"Saved {len(embedding_docs)} new embeddings.")

        # 9. Update existing "all" clusters with newly assigned article IDs
        logger.info("Updating cluster documents with new article IDs...")
        cluster_updates: Dict[int, List[PydanticObjectId]] = {}
        for i, label in enumerate(cluster_labels):
            label_int = int(label)
            if label_int not in cluster_updates:
                cluster_updates[label_int] = []
            cluster_updates[label_int].append(article_ids[i])

        updated_count = 0
        for cluster_id, new_art_ids in cluster_updates.items():
            cluster_doc = await Cluster.find_one(
                {
                    "cluster_id": cluster_id,
                    "model_version": model_version,
                    "cluster_type": "all",
                }
            )
            if cluster_doc:
                await cluster_doc.update(
                    {
                        "$push": {"article_ids": {"$each": new_art_ids}},
                        "$inc": {"article_count": len(new_art_ids)},
                    }
                )
                updated_count += 1

        logger.success(f"Updated {updated_count} cluster documents.")

        # Collect affected cluster metadata for caller to highlight
        affected_clusters = []
        for cid in cluster_updates.keys():
            if cid == -1:
                continue
            doc = await Cluster.find_one(
                {
                    "cluster_id": cid,
                    "model_version": model_version,
                    "cluster_type": "all",
                }
            )
            if doc:
                tag = self._resolve_cluster_topic_tag(doc) or (
                    doc.top_keywords[0]
                    if doc.top_keywords
                    else f"Cluster {doc.cluster_id}"
                )
                affected_clusters.append(
                    {
                        "cluster_id": doc.cluster_id,
                        "topic_tag": tag,
                        "article_count": doc.article_count,
                    }
                )

        # Refresh cache
        await self._load_cache(model_version)

        logger.section("Incremental Assignment Completed")

        return {
            "model_version": model_version,
            "new_articles_found": len(valid_new),
            "assigned": n_assigned,
            "noise": n_noise,
            "total_embeddings_saved": len(embedding_docs),
            "status": "completed",
            "affected_clusters": affected_clusters,
        }

    async def _create_cluster_documents(
        self,
        cluster_labels: "np.ndarray",
        embeddings_full: "np.ndarray",
        embeddings_reduced: "np.ndarray",
        article_ids: List[PydanticObjectId],
        valid_articles: List[Article],
        model_version: str,
        cluster_type: str,
        group_id: Optional[str] = None,
        extracted_keywords_map: Optional[dict] = None,
    ) -> List[Cluster]:
        """Cluster dokümanları oluştur"""
        cluster_docs = []
        unique_labels = set(cluster_labels)

        # Article ID -> Article mapping
        id_to_article = {a.id: a for a in valid_articles}

        for label in unique_labels:
            indices = np.where(cluster_labels == label)[0]

            # Centroid hesapla
            centroid_full = np.mean(embeddings_full[indices], axis=0)
            centroid_reduced = np.mean(embeddings_reduced[indices], axis=0)

            # Cluster'daki makaleler
            cluster_article_ids = [article_ids[i] for i in indices]

            # Top keywords ve sample titles
            top_keywords = []
            sample_titles = []

            for idx in indices:  # İlk 10 makale
                art_id = article_ids[idx]
                article = id_to_article.get(art_id)
                # Önce eğitim sırasında extract edilen keywords'ü dene
                if extracted_keywords_map and art_id in extracted_keywords_map:
                    top_keywords.extend(extracted_keywords_map[art_id])
                elif article and article.keywords:
                    top_keywords.extend(article.keywords)
                if article and article.title and len(sample_titles) < 5:
                    sample_titles.append(article.title)

            # En sık geçen keywords
            keyword_counts = Counter(top_keywords)
            top_keywords = [kw for kw, _ in keyword_counts.most_common()]

            # Cluster label: cross-encoder ile en temsili keyword'ü bul ve DB'ye kaydet
            label_text = None
            if label == -1:
                label_text = "Noise / Unclustered"
            elif top_keywords:
                label_text = await self._take_cluster_and_find_word(top_keywords)

            cluster_doc = Cluster(
                cluster_id=int(label),
                centroid_full=centroid_full.tolist(),
                centroid_reduced=centroid_reduced.tolist(),
                article_ids=cluster_article_ids,
                label=label_text,
                top_keywords=top_keywords,
                sample_titles=sample_titles,
                article_count=len(indices),
                cluster_type=cluster_type,
                group_id=group_id,
                model_version=model_version,
            )
            cluster_docs.append(cluster_doc)

        return cluster_docs

    async def _arrange_date(self, publication_date):

        # prefix_dates = {
        #     "january" : "1",
        #     "february" : "2",
        #     "march" : "3",
        #     "april" : "4",
        #     "may" : "5",
        #     "june" : "6",
        #     "july" : "7",
        #     "august" : "8",
        #     "september" : "9",
        #     "october" : "10",
        #     "november" : "11",
        #     "december" : "12"
        #     }
        date_fin = None
        date = publication_date
        if date is None:
            return None
        try:
            dt_object = datetime.fromisoformat(date)
            date_fin = dt_object
        except:
            # print(f"{date} is not convertable to datetime")
            # print(f"Trying to fetch date from the string: {date}")
            d = date.lower()
            est_date = ""
            for month, number in self.PREFIX_DATES.items():
                if month in d:
                    # [\D]*? -> Skip any number of non-digit characters
                    # (\d{4}) -> Capture exactly 4 digits
                    pattern = rf"{month}[\D]*?(\d{{4}})"
                    match = re.search(pattern, d)

                    if match:
                        year = match.group(1)  # This is the 4-digit year
                        est_date = f"{year}-{number.zfill(2)}-01"  # Adding -01 makes it a valid ISO date

                        try:
                            dt_object = datetime.fromisoformat(est_date)
                            date_fin = dt_object
                            logger.debug(f"Date parsed successfully: {est_date}")
                        except ValueError:
                            logger.warning(f"Failed to parse date string: {est_date}")
                    else:
                        logger.debug(
                            f"Found month '{month}' but no 4-digit year near it in: {date}"
                        )

                    break
        return date_fin

    async def get_date_graph_input(
        self,
        query: Optional[str] = None,
        model_version: Optional[str] = None,
    ):
        """
        Dökümanların yazıldığı tarihleri temizleyip frontend'e gönderir.

        Eski versiyon (self.state bağımlı):
        # result = {}
        # dates = [art.article_dates for art in self.articles]
        # for date in dates:
        #     fin_date = self._arrange_date(date)
        #     if fin_date == None: continue
        #     result[fin_date] = result.get(fin_date, 0) + 1
        # return result
        """
        if query is not None:
            search_result = await self._search_similar_clusters(query, model_version)
            best_cluster = search_result["best_cluster"]
            model_version = search_result["model_version"]
            articles = await ArticleEmbedding.find(
                {
                    "article_id": {"$in": best_cluster.article_ids},
                    "model_version": model_version,
                }
            ).to_list()
        elif self.articles is not None:
            # DEPRECATED fallback — remove after router migration
            articles = self.articles
        else:
            raise ValueError(
                "query param required (self.articles legacy state removed)"
            )

        result = {}
        dates = [art.article_dates for art in articles]
        for date in dates:
            fin_date = await self._arrange_date(date)
            if fin_date is None:
                continue
            result[str(fin_date)] = result.get(str(fin_date), 0) + 1

        return result

    async def get_scatter_graph_input(
        self,
        query: Optional[str] = None,
        model_version: Optional[str] = None,
    ):
        """
        Eski versiyon (self.state bağımlı):
        # visualization_reducer = umap.UMAP(
        #     n_neighbors=5, n_components=2, metric="cosine", random_state=42
        # )
        # embedded_words = [
        #     self.embedder.encode(word[0]) for word in self.relevant_keywords
        # ]
        # coords = visualization_reducer.fit_transform(embedded_words)
        # scatter_data = []
        # for idx, word_tuple in enumerate(self.relevant_keywords):
        #     scatter_data.append({"x": float(coords[idx][0]), "y": float(coords[idx][1])})
        # return scatter_data
        """
        if query is not None:
            search_result = await self._search_similar_clusters(query, model_version)
            best_cluster = search_result["best_cluster"]
            model_version = search_result["model_version"]
            articles = await ArticleEmbedding.find(
                {
                    "article_id": {"$in": best_cluster.article_ids},
                    "model_version": model_version,
                }
            ).to_list()
            relevant_keywords = await self._extract_cluster_keywords(articles, query)
        elif self.relevant_keywords is not None:
            # DEPRECATED fallback
            relevant_keywords = self.relevant_keywords
        else:
            raise ValueError(
                "query param required (self.relevant_keywords legacy state removed)"
            )

        visualization_reducer = umap.UMAP(
            n_neighbors=5, n_components=2, metric="cosine", random_state=42
        )
        embedded_words = [self.embedder.encode(word[0]) for word in relevant_keywords]
        coords = visualization_reducer.fit_transform(embedded_words)

        scatter_data = []
        for idx, word_tuple in enumerate(relevant_keywords):
            scatter_data.append(
                {
                    "x": float(coords[idx][0]),
                    "y": float(coords[idx][1]),
                }
            )

        return scatter_data

    async def _extract_relevance_of_articles(
        self,
        best_cluster=None,
        articles=None,
        encoded_query=None,
    ):
        """
        Eski versiyon (self.state bağımlı):
        # scores = []
        # article_ids = self.best_cluster.article_ids
        # all_embeddings = await self.embedding_repo.find_many_by_article_ids(article_ids)
        # emb_dict = {str(e.article_id): e.embedding_full for e in all_embeddings}
        # matrix_embeddings = np.vstack(
        #     [np.array(emb_dict[str(art.id)]) for art in self.articles]
        # )
        # reshaped_query = np.array(self.encoded_query).reshape(1, -1)
        # scores = cosine_similarity(reshaped_query, matrix_embeddings)[0]
        # ranked_results = []
        # for i in range(len(self.articles)):
        #     ranked_results.append(
        #         {"score": scores[i], "abstract": self.articles[i].abstract}
        #     )
        # ranked_results.sort(key=lambda x: x["score"], reverse=True)
        # return ranked_results
        """
        if best_cluster is None or articles is None or encoded_query is None:
            raise ValueError(
                "best_cluster, articles, encoded_query must be provided "
                "(legacy self.* state removed)"
            )

        article_ids = best_cluster.article_ids

        all_embeddings = await self.embedding_repo.find_many_by_article_ids(article_ids)
        emb_dict = {str(e.article_id): e.embedding_full for e in all_embeddings}
        matrix_embeddings = np.vstack(
            [np.array(emb_dict[str(art.id)]) for art in articles]
        )
        reshaped_query = np.array(encoded_query).reshape(1, -1)

        scores = cosine_similarity(reshaped_query, matrix_embeddings)[0]
        ranked_results = []
        for i in range(len(articles)):
            ranked_results.append(
                {"score": scores[i], "abstract": articles[i].abstract}
            )

        ranked_results.sort(key=lambda x: x["score"], reverse=True)
        return ranked_results

    # def _preprocess_scientific_text(self, text):
    #     # unused — spacy/cleaner_guy commented out
    #     doc = self.cleaner_guy(text)
    #
    #     tokens = []
    #     for token in doc:
    #         is_person = token.ent_type_ == "PERSON"
    #
    #         if (
    #             token.pos_ in ["NOUN", "ADJ"]
    #             and token.pos_ != "PROPN"
    #             and not is_person
    #             and not token.is_stop
    #             and len(token.text) > 2
    #         ):
    #             tokens.append(token.lemma_.lower())
    #
    #     return " ".join(tokens)

    # async def _extract_cluster_keywords(self):
    #     cleaned_abstracts = [self._preprocess_scientific_text(art.abstract) for art in self.articles]

    #     vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
    #     tfidf_matrix = vectorizer.fit_transform(cleaned_abstracts)
    #     feature_names = vectorizer.get_feature_names_out()

    #     article_keywords = []
    #     for i in range(len(cleaned_abstracts)):
    #         row = tfidf_matrix[i].toarray()[0]
    #         top_indices = np.argsort(row)[-5:][::-1]
    #         keywords = [feature_names[idx] for idx in top_indices if row[idx] > 0]
    #         article_keywords.append(keywords)

    #     return article_keywords

    async def _eval_keywords(self, all_candidate_pairs):
        """
        Accepts a list of all [query, keyword] pairs across all abstracts
        to process them in a single batch.
        """
        # Batch processing is significantly faster than looping
        scores = self.cross_encoder.predict(all_candidate_pairs, batch_size=32)
        return scores

    async def _fetch_with_source(self, user_website):
        article_embeddings = await ArticleEmbedding.find(
            {"article_source_website": user_website}
        ).to_list()

        logger.debug(f"Sample embedding: {article_embeddings[0]}")
        return 0

    async def _generate_trends_from_clusters(
        self,
        clusters: list,
        model_version: str,
        top_n: int = None,
        allowed_article_ids: Optional[Set[PydanticObjectId]] = None,
    ):
        if not clusters:
            return {"graph_data": [], "clusters": []}

        allowed_ids = set(allowed_article_ids) if allowed_article_ids else None

        # 1. Fetch all embeddings once
        all_article_ids = set()
        for cluster in clusters:
            if cluster.cluster_id == -1:
                continue
            if allowed_ids is None:
                all_article_ids.update(cluster.article_ids)
            else:
                all_article_ids.update(
                    art_id for art_id in cluster.article_ids if art_id in allowed_ids
                )

        if not all_article_ids:
            return {"graph_data": [], "clusters": []}

        embeddings_list = await ArticleEmbedding.find(
            {
                "article_id": {"$in": list(all_article_ids)},
                "model_version": model_version,
            }
        ).to_list()

        # 2. Map ID to BOTH keywords and dates
        embedding_map = {
            embd.article_id: {
                "keywords": embd.article_keywords,
                "date": embd.article_dates,
            }
            for embd in embeddings_list
        }

        # This will store our graph data: { "2023": {"AI": 5, "Robotics": 2}, "2024": ... }
        timeline_data = defaultdict(lambda: defaultdict(int))
        cluster_summaries = []

        # 3. Process each cluster
        for cluster in clusters:
            if cluster.cluster_id == -1:
                continue
            raw_keywords = []
            cluster_dates = []
            matched_article_count = 0

            for art_id in cluster.article_ids:
                if allowed_ids is not None and art_id not in allowed_ids:
                    continue

                if art_id in embedding_map:
                    matched_article_count += 1
                    raw_keywords.extend(embedding_map[art_id]["keywords"])
                    raw_date = embedding_map[art_id]["date"]
                    year = str(raw_date)[:7] if raw_date else "Unknown"
                    cluster_dates.append(year)

            if matched_article_count == 0:
                continue

            unique_keywords = list(set(raw_keywords))

            if not unique_keywords and not cluster.label and not cluster.top_keywords:
                continue

            topic_tag = self._resolve_cluster_topic_tag(cluster)
            if topic_tag is None:
                topic_tag = await self._take_cluster_and_find_word(unique_keywords)

            # 4. Populate the timeline counts
            for year in cluster_dates:
                timeline_data[year][topic_tag] += 1

            cluster_summaries.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "topic_tag": topic_tag,
                    "article_count": matched_article_count,
                }
            )

        # 5. Format the data for the frontend graph (X/Y axis friendly)
        graph_data = []
        for year, topics in timeline_data.items():
            entry = {"date": year}  # X-axis
            entry.update(topics)  # Y-axis data points
            graph_data.append(entry)

        # Sort the graph data chronologically
        graph_data.sort(key=lambda x: x["date"])

        # Apply top_n filter — sort clusters by article_count desc, take first N
        cluster_summaries.sort(key=lambda x: x["article_count"], reverse=True)
        if top_n is not None:
            cluster_summaries = cluster_summaries[:top_n]

        allowed_topics = {c["topic_tag"] for c in cluster_summaries}
        filtered_graph_data = []
        for entry in graph_data:
            new_entry = {"date": entry["date"]}
            for topic in allowed_topics:
                if topic in entry:
                    new_entry[topic] = entry[topic]
            filtered_graph_data.append(new_entry)

        keyword_distribution: Dict[str, int] = {}
        for entry in filtered_graph_data:
            for topic, count in entry.items():
                if topic == "date":
                    continue
                keyword_distribution[topic] = keyword_distribution.get(topic, 0) + count

        return {
            "graph_data": filtered_graph_data,
            "clusters": cluster_summaries,
            "keyword_distribution": keyword_distribution,
        }

    async def _resolve_journal_group_id(
        self, journal_name: str
    ) -> Optional[PydanticObjectId]:
        """
        Dergi adını (journal_name) → journal ObjectId'ye çevirir.
        DB'de group_id hem ObjectId hem str olabilir; ObjectId ile sorgulayarak her ikisini yakalarız.
        Büyük/küçük harf farkını tolere eder; bulamazsa partial match dener.
        """
        pattern = re.compile(f"^{re.escape(journal_name.strip())}$", re.IGNORECASE)
        article = await Article.find_one({"journal_name": {"$regex": pattern}})
        if not article:
            partial = re.compile(re.escape(journal_name.strip()), re.IGNORECASE)
            article = await Article.find_one({"journal_name": {"$regex": partial}})
        if not article:
            logger.warning(
                f"_resolve_journal_group_id: no article found for journal_name='{journal_name}'"
            )
            return None
        return article.journal_id  # PydanticObjectId

    async def get_clusters_by_journal(self, journal_name: str, model_version: str):
        journal_oid = await self._resolve_journal_group_id(journal_name)
        if not journal_oid:
            return []

        # Incremental assignment only creates cluster_type="all" documents.
        # Derive journal trends by intersecting journal article IDs with all clusters.
        journal_embeddings = await ArticleEmbedding.find(
            {
                "model_version": model_version,
                "article_journal_id": {"$in": [journal_oid, str(journal_oid)]},
            }
        ).to_list()

        journal_article_ids = {emb.article_id for emb in journal_embeddings}
        if not journal_article_ids:
            logger.warning(
                f"get_clusters_by_journal: no embeddings found for journal='{journal_name}' and model_version='{model_version}'"
            )
            return []

        clusters = await Cluster.find(
            {
                "cluster_type": "all",
                "model_version": model_version,
                "cluster_id": {"$ne": -1},
                "article_ids": {"$in": list(journal_article_ids)},
            }
        ).to_list()

        return clusters

    # For Journals
    async def get_journal_topic_trends(
        self, journal_name: str, model_version: str, top_n: int = None
    ):
        journal_oid = await self._resolve_journal_group_id(journal_name)
        if not journal_oid:
            return {"graph_data": [], "clusters": []}

        journal_embeddings = await ArticleEmbedding.find(
            {
                "model_version": model_version,
                "article_journal_id": {"$in": [journal_oid, str(journal_oid)]},
            }
        ).to_list()
        journal_article_ids = {emb.article_id for emb in journal_embeddings}
        if not journal_article_ids:
            logger.warning(
                f"get_journal_topic_trends: no embeddings found for journal='{journal_name}' and model_version='{model_version}'"
            )
            return {"graph_data": [], "clusters": []}

        clusters = await self.get_clusters_by_journal(journal_name, model_version)
        return await self._generate_trends_from_clusters(
            clusters,
            model_version,
            top_n=top_n,
            allowed_article_ids=journal_article_ids,
        )

    # For Publishers
    async def get_publisher_topic_trends(
        self, publisher_name: str, model_version: str, top_n: int = None
    ):
        # publisher_name is source_website value: 'ieeexplore', 'sciencedirect', 'acm'
        clusters = await Cluster.find(
            {
                "group_id": publisher_name,
                "cluster_type": "publisher",
                "model_version": model_version,
            }
        ).to_list()
        return await self._generate_trends_from_clusters(
            clusters, model_version, top_n=top_n
        )

    async def get_keyword_topic_trends(
        self, keyword: str, model_version: str, top_n: int = None
    ) -> Dict[str, Any]:
        """
        Calculates cosine similarity between the query and all cluster centroids.
        Selects clusters with similarity >= 0.75.
        Returns a time series (graph_data) grouped by matched cluster labels and keyword_distribution.
        """
        _ensure_nlp_imports()

        if not model_version:
            model_version = await self._resolve_model_db_first(auto_train=False)

        if self._cached_version != model_version:
            await self._load_cache(model_version)

        if self._cached_centroids is None or len(self._cached_centroids) == 0:
            return {"graph_data": [], "keyword_distribution": {}}

        query_cleaned = self._clean_text(keyword)
        query_embedding = self.embedder.encode([query_cleaned])

        clusters = await self.cluster_repo.find_by_model_version_on_all(
            model_version, include_noise=False
        )
        if not clusters:
            return {"graph_data": [], "keyword_distribution": {}}

        centroid_list = [cluster.centroid_full for cluster in clusters]
        centroid_matrix = np.vstack(centroid_list)
        try:
            similarities = cosine_similarity(query_embedding, centroid_matrix)[0]
        except ValueError as e:
            if "Incompatible dimension" in str(e):
                logger.error(
                    f"Dimension mismatch: query is {query_embedding.shape[1]}d, centroids are {centroid_matrix.shape[1]}d."
                )
                raise ValueError(
                    "Dimension mismatch between the loaded embedder model and the database clusters. Please retrain the model for this version."
                )
            raise

        matched_clusters = []
        for i, cluster in enumerate(clusters):
            if similarities[i] >= 0.40:
                matched_clusters.append((cluster, similarities[i]))

        if not matched_clusters:
            return {"graph_data": [], "keyword_distribution": {}}

        # Sort by total article count descending
        matched_clusters.sort(key=lambda x: x[0].article_count or 0, reverse=True)
        if top_n is not None:
            matched_clusters = matched_clusters[:top_n]

        all_matched_article_ids = []
        for c, _ in matched_clusters:
            all_matched_article_ids.extend(c.article_ids)

        embeddings = await ArticleEmbedding.find(
            {
                "article_id": {"$in": all_matched_article_ids},
                "model_version": model_version,
            }
        ).to_list()

        article_dates_map = {emb.article_id: emb.article_dates for emb in embeddings}

        timeline: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        keyword_counter: Counter = Counter()

        for cluster, sim in matched_clusters:
            topic = (
                self._resolve_cluster_topic_tag(cluster)
                or f"Cluster {cluster.cluster_id}"
            )

            for article_id in cluster.article_ids:
                raw_date = article_dates_map.get(article_id)
                date_str = str(raw_date)[:7] if raw_date else None
                if not date_str:
                    continue
                timeline[date_str][topic] += 1
                keyword_counter[topic] += 1

        graph_data = []
        for date_str, topics in timeline.items():
            entry = {"date": date_str}
            entry.update(topics)
            graph_data.append(entry)

        graph_data.sort(key=lambda x: x["date"])

        return {
            "graph_data": graph_data,
            "keyword_distribution": dict(keyword_counter.most_common()),
        }

    async def list_clusters(
        self,
        model_version: str,
        cluster_type: str = "all",
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Graph data üretmeden sadece cluster metadatasını döndürür.
        Pagination amaçlı frontend kullanımı için.
        Journal tipinde incremental assignment cluster_type="all" kullandığından
        journal_article_ids ile kesişim yapılır.
        """
        if cluster_type == "journal" and group_id:
            # Incremental assignment only creates cluster_type="all" clusters.
            # Use journal article IDs intersection to find relevant clusters.
            clusters = await self.get_clusters_by_journal(group_id, model_version)
            journal_oid = await self._resolve_journal_group_id(group_id)
            if not journal_oid:
                return {"clusters": []}
            journal_embeddings = await ArticleEmbedding.find(
                {
                    "model_version": model_version,
                    "article_journal_id": {"$in": [journal_oid, str(journal_oid)]},
                }
            ).to_list()
            journal_article_ids = {emb.article_id for emb in journal_embeddings}

            result = []
            for cluster in clusters:
                if cluster.cluster_id == -1:
                    continue
                matched = sum(
                    1 for aid in cluster.article_ids if aid in journal_article_ids
                )
                if matched == 0:
                    continue
                topic_tag = (
                    self._resolve_cluster_topic_tag(cluster)
                    or f"Cluster {cluster.cluster_id}"
                )
                result.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "topic_tag": topic_tag,
                        "article_count": matched,
                    }
                )
            result.sort(key=lambda x: x["article_count"], reverse=True)
            return {"clusters": result}

        query: Dict[str, Any] = {
            "model_version": model_version,
            "cluster_type": cluster_type,
        }
        if group_id:
            query["group_id"] = group_id

        clusters = await Cluster.find(query).to_list()

        result = []
        for cluster in clusters:
            if cluster.cluster_id == -1:
                continue  # noise skip
            topic_tag = (
                self._resolve_cluster_topic_tag(cluster)
                or f"Cluster {cluster.cluster_id}"
            )
            result.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "topic_tag": topic_tag,
                    "article_count": cluster.article_count or 0,
                }
            )

        result.sort(key=lambda x: x["article_count"], reverse=True)
        return {"clusters": result}

    async def get_cluster_trend_series(
        self,
        cluster_id: int,
        model_version: str,
        cluster_type: str = "all",
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tek bir cluster için zaman serisi verisi döndürür.
        Frontend'in bir konuyu aktifleştirirken on-demand çağırması için.
        """
        query: Dict[str, Any] = {
            "cluster_id": cluster_id,
            "cluster_type": cluster_type,
            "model_version": model_version,
        }
        if group_id:
            if cluster_type == "journal":
                resolved = await self._resolve_journal_group_id(group_id)
                if not resolved:
                    return {"topic_tag": None, "series": {}}
                query["group_id"] = {"$in": [resolved, str(resolved)]}
            else:
                query["group_id"] = group_id

        cluster = await Cluster.find_one(query)
        if not cluster or cluster.cluster_id == -1:
            return {"topic_tag": None, "series": {}}

        topic_tag = (
            self._resolve_cluster_topic_tag(cluster) or f"Cluster {cluster.cluster_id}"
        )

        # Fetch embeddings for this cluster's articles only
        embeddings_list = await ArticleEmbedding.find(
            {
                "article_id": {"$in": cluster.article_ids},
                "model_version": model_version,
            }
        ).to_list()

        date_counts: Dict[str, int] = defaultdict(int)
        for embd in embeddings_list:
            raw_date = embd.article_dates
            year_month = str(raw_date)[:7] if raw_date else None
            if year_month:
                date_counts[year_month] += 1

        # Return as sorted list of {date, count} for easy merging on frontend
        series = [{"date": d, "count": c} for d, c in sorted(date_counts.items())]
        return {"topic_tag": topic_tag, "cluster_id": cluster_id, "series": series}

    async def patch_cluster_labels(
        self, model_version: str, force_recompute: bool = False
    ) -> Dict[str, Any]:
        """
        Mevcut bir model versiyonundaki label=null veya top_keywords=[] olan
        cluster'ları yeniden hesaplayıp DB'ye yazar. Train gerektirmez.
        """
        clusters = await Cluster.find({"model_version": model_version}).to_list()
        if not clusters:
            return {
                "patched": 0,
                "skipped": 0,
                "message": "No clusters found for this model version",
            }

        # Tüm cluster'lardaki article_id'leri topla
        all_article_ids = set()
        for cluster in clusters:
            if cluster.cluster_id != -1:
                all_article_ids.update(cluster.article_ids)

        # Embedding'lerden keywords'leri çek
        embeddings_list = await ArticleEmbedding.find(
            {
                "article_id": {"$in": list(all_article_ids)},
                "model_version": model_version,
            }
        ).to_list()
        keywords_map = {
            embd.article_id: embd.article_keywords for embd in embeddings_list
        }

        patched = 0
        skipped = 0

        for cluster in clusters:
            if cluster.cluster_id == -1:
                if not cluster.label:
                    cluster.label = "Noise / Unclustered"
                    await cluster.save()
                    patched += 1
                else:
                    skipped += 1
                continue

            # Zaten label ve keywords varsa atla
            if not force_recompute and cluster.label and cluster.top_keywords:
                skipped += 1
                continue

            # Keywords topla
            raw_keywords: list = []
            for art_id in cluster.article_ids[:10]:
                kws = keywords_map.get(art_id, [])
                raw_keywords.extend(kws)

            keyword_counts = Counter(raw_keywords)
            top_keywords = [kw for kw, _ in keyword_counts.most_common()]

            if not top_keywords:
                skipped += 1
                continue
            label_text = await self._take_cluster_and_find_word(top_keywords)

            cluster.top_keywords = top_keywords
            cluster.label = label_text
            await cluster.save()
            patched += 1
            logger.info(
                f"Patched cluster {cluster.cluster_id} ({cluster.cluster_type}): '{label_text}'"
            )

        return {
            "model_version": model_version,
            "total_clusters": len(clusters),
            "patched": patched,
            "skipped": skipped,
        }

    async def patch_cluster_group_ids(self, model_version: str) -> Dict[str, Any]:
        """
        group_id alanı null olan publisher/journal cluster'larını
        ArticleEmbedding tablosundan alınan publisher/journal bilgisiyle doldurur.
        Yeniden eğitim gerektirmez.
        """
        clusters = await Cluster.find(
            {
                "model_version": model_version,
                "cluster_type": {"$in": ["publisher", "journal"]},
                "group_id": None,
            }
        ).to_list()

        if not clusters:
            return {
                "patched": 0,
                "skipped": 0,
                "message": "Null group_id olan cluster bulunamadi.",
            }

        # Tüm article_id'leri topla
        all_article_ids = list(
            {art_id for c in clusters for art_id in c.article_ids[:1]}
        )

        embeddings_list = await ArticleEmbedding.find(
            {
                "article_id": {"$in": all_article_ids},
                "model_version": model_version,
            }
        ).to_list()

        emb_map: Dict[Any, ArticleEmbedding] = {
            e.article_id: e for e in embeddings_list
        }

        patched = 0
        skipped = 0
        bulk_ops = []
        for cluster in clusters:
            sample_id = next(iter(cluster.article_ids), None)
            if sample_id is None:
                skipped += 1
                continue

            emb = emb_map.get(sample_id)
            if emb is None:
                skipped += 1
                continue

            if cluster.cluster_type == "publisher":
                new_group_id = emb.article_publisher
            else:
                new_group_id = (
                    str(emb.article_journal_id) if emb.article_journal_id else None
                )

            if not new_group_id:
                skipped += 1
                continue

            bulk_ops.append(
                UpdateOne({"_id": cluster.id}, {"$set": {"group_id": new_group_id}})
            )
            patched += 1

        if bulk_ops:
            await Cluster.get_motor_collection().bulk_write(bulk_ops)

        logger.info(f"patch_cluster_group_ids: patched={patched}, skipped={skipped}")
        return {"model_version": model_version, "patched": patched, "skipped": skipped}

    # For the Entire Dataset ("All")
    async def get_all_topic_trends(self, model_version: str, top_n: int = None):
        clusters = await Cluster.find(
            {"cluster_type": "all", "model_version": model_version}
        ).to_list()
        return await self._generate_trends_from_clusters(
            clusters, model_version, top_n=top_n
        )

    # async def get_journal_topic_trends(self, journal_name: str, model_version: str) -> Optional[Dict[str, Any]]:
    #     clusters = await self.get_clusters_by_journal(journal_name, model_version)
    #     if not clusters:
    #         return None

    #     # 1. Fetch all embeddings once
    #     all_article_ids = set()
    #     for cluster in clusters:
    #         if cluster.cluster_id != -1:
    #             all_article_ids.update(cluster.article_ids)

    #     embeddings_list = await ArticleEmbedding.find({
    #         "article_id": {"$in": list(all_article_ids)},
    #         "model_version": model_version
    #     }).to_list()

    #     # 2. Map ID to BOTH keywords and dates
    #     embedding_map = {
    #         embd.article_id: {
    #             "keywords": embd.article_keywords,
    #             "date": embd.article_dates # Pulling the date from your schema
    #         }
    #         for embd in embeddings_list
    #     }

    #     # This will store our graph data: { "2023": {"AI": 5, "Robotics": 2}, "2024": ... }
    #     timeline_data = defaultdict(lambda: defaultdict(int))
    #     cluster_summaries = []

    #     # 3. Process each cluster
    #     for cluster in clusters:
    #         raw_keywords = []
    #         cluster_dates = []

    #         for art_id in cluster.article_ids:
    #             if art_id in embedding_map:
    #                 raw_keywords.extend(embedding_map[art_id]["keywords"])

    #                 # Extract the year for the X-axis (assuming dates are strings).
    #                 # Adjust this slice if your date format is different (e.g., 'YYYY-MM-DD')
    #                 raw_date = embedding_map[art_id]["date"]
    #                 year = str(raw_date)[:4] if raw_date else "Unknown"
    #                 cluster_dates.append(year)

    #         unique_keywords = list(set(raw_keywords))[:20]

    #         if not unique_keywords:
    #             continue

    #         # Find the topic tag
    #         topic_tag = await self._take_cluster_and_find_word(unique_keywords)

    #         # 4. Populate the timeline counts
    #         for year in cluster_dates:
    #             timeline_data[year][topic_tag] += 1

    #         cluster_summaries.append({
    #             "cluster_id": cluster.cluster_id,
    #             "topic_tag": topic_tag,
    #             "article_count": len(cluster.article_ids)
    #         })

    #     # 5. Format the data for the frontend graph (X/Y axis friendly)
    #     graph_data = []
    #     for year, topics in timeline_data.items():
    #         entry = {"date": year} # X-axis
    #         entry.update(topics)   # Y-axis data points
    #         graph_data.append(entry)

    #     # Sort the graph data chronologically
    #     graph_data.sort(key=lambda x: x["date"])

    #     return {
    #         "graph_data": graph_data,
    #         "clusters": cluster_summaries
    #     }

    async def _fetch_via_journal(self, journal_name: str, model_version: str):
        clusters = await self.get_clusters_by_journal(journal_name, model_version)
        if not clusters:
            return None

        # 1. Fetch all embeddings once
        all_article_ids = set()
        for cluster in clusters:
            all_article_ids.update(cluster.article_ids)

        embeddings_list = await ArticleEmbedding.find(
            {
                "article_id": {"$in": list(all_article_ids)},
                "model_version": model_version,
            }
        ).to_list()

        embedding_map = {
            embd.article_id: embd.article_keywords for embd in embeddings_list
        }

        # 2. Process each cluster to find its "Integral Word"
        cluster_results = []
        for cluster in clusters:
            raw_keywords = []
            for art_id in cluster.article_ids:
                if art_id in embedding_map:
                    raw_keywords.extend(embedding_map[art_id])

            unique_keywords = list(set(raw_keywords))

            if not unique_keywords:
                continue

            # 3. Find the most representative label using your Cross-Encoder logic
            cluster_label = await self._take_cluster_and_find_word(unique_keywords)

            cluster_results.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "integral_label": cluster_label,
                    "all_keywords": unique_keywords,
                    "article_count": len(cluster.article_ids),
                }
            )

        return cluster_results

    async def _take_keywords_and_transform(self, words):
        """
        Bir grup kelimeyi alır bunları kümeler ve kümeleri
        {cluster_idx : [words]}
        olarak döndürür.

        Küçük keyword listeleri için UMAP atlanır — sparse eigensolver
        çökmesini önler.
        """
        n = len(words)
        if n == 0:
            return {}
        if n == 1:
            return {0: [words[0][0]]}

        word_texts = [w[0] for w in words]

        # Skip UMAP for small inputs — spectral decomp fails when k >= N
        if n < 20:
            return {i: [word_texts[i]] for i in range(n)}

        embedded_words = [self.embedder.encode(wt) for wt in word_texts]

        n_neighbors = min(settings.nlp_umap_n_neighbors, n - 1)
        n_neighbors = max(n_neighbors, 2)

        reducer = umap.UMAP(
            n_neighbors=n_neighbors,
            n_components=min(settings.nlp_umap_n_components, n - 1),
            metric="cosine",
            random_state=42,
        )
        embeddings_reduced = reducer.fit_transform(embedded_words)

        min_cluster_size = min(5, n)
        min_samples = min(settings.nlp_min_samples_all, n - 1)
        min_samples = max(min_samples, 1)

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size, min_samples=min_samples
        )
        cluster_labels = clusterer.fit_predict(embeddings_reduced)

        clusters = {}

        for idx, label in enumerate(cluster_labels):
            if label not in clusters:
                clusters[label] = []

            clusters[label].append(word_texts[idx])

        return clusters

    def _resolve_cluster_topic_tag(self, cluster) -> Optional[str]:
        """DB'de saklanan label veya ilk keyword'ü döner; ikisi de yoksa None."""
        if cluster.label and cluster.label != "Noise / Unclustered":
            return cluster.label
        if cluster.top_keywords:
            return cluster.top_keywords[0]
        return None

    import re

    def clean_extracted_keywords(self, keywords):
        cleaned = []

        # Custom stop-words specific to academic paper abstracts
        academic_fluff = {
            "problem",
            "learning",
            "accuracy",
            "requirements",
            "memory",
            "performance",
            "method",
            "approach",
            "results",
            "study",
            "paper",
            "works",
            "challenges",
            "optimization",
            "formulation",
            "network",
            "image",
            "hardware",
            "system",
            "framework",
            "novel framework",
            "systems application",
            "generalization capability",
        }
        units = {"ghz", "mhz", "khz", "hz", "db", "mw", "kw", "hz"}
        for kw in keywords:
            kw_lower = kw.lower()

            # 1. Kill anything containing numbers (drops "80.3db", "syst.44")
            if re.search(r"\d", kw_lower):
                continue

            # 2. Kill broken punctuation (drops "poly(n")
            if "(" in kw_lower and ")" not in kw_lower:
                continue
            if kw_lower.startswith(".") or kw_lower.endswith("."):
                continue
            if any(char in kw_lower for char in ["\\", "{", "}", "_", "^", "="]):
                continue
            # 3. Kill meaningless academic fluff
            if kw_lower in academic_fluff:
                continue

            # 4. Drop single-character junk
            if len(kw_lower) <= 2:
                continue

            cleaned.append(kw)

        return cleaned

    async def _take_cluster_and_find_word(self, cluster_list):
        n = len(cluster_list)
        if n == 1:
            return cluster_list[0]

        def _compute_best_word():
            import torch
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity

            # 1. Generate embeddings for all candidate words
            embeddings = self.embedder.encode(cluster_list, show_progress_bar=False)

            # 2. Dynamic Outlier Rejection
            if n >= 3:
                sim_matrix = cosine_similarity(embeddings)
                avg_similarities = (np.sum(sim_matrix, axis=1) - 1) / (n - 1)

                # Keep words that are within 1 standard deviation of the mean similarity
                threshold = np.mean(avg_similarities) - np.std(avg_similarities)
                core_indices = np.where(avg_similarities >= threshold)[0]

                # Fallback if threshold is too aggressive
                if len(core_indices) < 2:
                    core_indices = np.argsort(avg_similarities)[-2:]

                core_embeddings = embeddings[core_indices]
                centroid = np.mean(core_embeddings, axis=0)
            else:
                centroid = np.mean(embeddings, axis=0)

            # 3. Find the exact word with a Length Penalty
            centroid_similarities = cosine_similarity([centroid], embeddings)[0]

            # Count words by splitting on spaces
            word_counts = np.array([len(w.split()) for w in cluster_list])

            # Penalty factor alpha. 0.05 means a 4-word phrase needs to be 0.15
            # more similar to the centroid than a 1-word phrase to beat it.
            alpha = 0.05
            length_penalty = alpha * (word_counts - 1)

            adjusted_scores = centroid_similarities - length_penalty
            best_idx = np.argmax(adjusted_scores)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Assuming logger is defined in your class/module
            logger.info(
                f"Selected '{cluster_list[best_idx]}' from the kwords '{cluster_list}'"
            )

            return cluster_list[best_idx]

        return await asyncio.to_thread(_compute_best_word)

    async def _extract_abstarct_keywords(self, text):
        def _extract():
            # Use KeyphraseCountVectorizer to extract grammatically correct noun phrases
            # instead of blindly crushing non-stop-words together into Frankenstein bigrams.
            from keyphrase_vectorizers import KeyphraseCountVectorizer

            vectorizer = KeyphraseCountVectorizer()

            return self.kw_model.extract_keywords(
                text,
                vectorizer=vectorizer,
                use_mmr=True,
                diversity=0.3,
                top_n=5,  # Extract top 5 candidates to evaluate
            )

        extracted = await asyncio.to_thread(_extract)

        kws = [item[0] for item in extracted]
        kws = self.clean_extracted_keywords(kws)
        return kws

    async def _extract_cluster_keywords(
        self, articles: List[ArticleEmbedding], query: str
    ) -> List[Tuple[str, float]]:
        """
        Makalelerin önceden çıkarılmış veri tabanındaki kelimelerini
        sorgumuzla kıyaslar ve en ilgili olanları döndürür.
        """
        all_keywords_per_abstract = []
        all_pairs_to_score = []

        for art in articles:
            kws = art.article_keywords

            if not kws:
                continue

            all_keywords_per_abstract.append(kws)

            for kw in kws:
                all_pairs_to_score.append([query, kw])

        if not all_pairs_to_score:
            return []

        all_scores = await self._eval_keywords(all_pairs_to_score)

        final_max_keywords = []
        score_idx = 0

        for kws in all_keywords_per_abstract:
            best_kw = None
            max_score = float("-inf")

            for kw in kws:
                score = all_scores[score_idx].item()
                if score > max_score:
                    max_score = score
                    best_kw = kw
                score_idx += 1

            final_max_keywords.append((best_kw, max_score))

        return final_max_keywords

    async def word_finding_pipeline(
        self,
        query: str,
        model_version: Optional[str] = None,
        top_k: int = 10,
        auto_train: bool = False,
    ) -> Dict[str, int]:
        """
        Keyword'ü cluster'lara eşler, ilgili kelimeleri çıkarır,
        bu kelimeleri tekrar cluster'layarak temsili kelime grupları üretir.

        Eski versiyon (self.state bağımlı):
        # words_and_counts = {}
        # final_max_keywords = await self._extract_cluster_keywords()
        # clusters = await self._take_keywords_and_transform(final_max_keywords)
        # for key in clusters.keys():
        #     if key == -1: word = "Other"
        #     else: word = await self._take_cluster_and_find_word(clusters[key])
        #     words_and_counts[word] = words_and_counts.get(word, 0) + len(clusters[key])
        # return words_and_counts
        """
        search_result = await self._search_similar_clusters(
            query, model_version, top_k, auto_train
        )
        best_cluster = search_result["best_cluster"]
        model_version = search_result["model_version"]

        articles = await ArticleEmbedding.find(
            {
                "article_id": {"$in": best_cluster.article_ids},
                "model_version": model_version,
            }
        ).to_list()

        final_max_keywords = await self._extract_cluster_keywords(articles, query)
        keyword_clusters = await self._take_keywords_and_transform(final_max_keywords)

        words_and_counts = {}
        for key, cluster_words in keyword_clusters.items():
            if key == -1:
                word = "Other"
            else:
                word = await self._take_cluster_and_find_word(cluster_words)
            words_and_counts[word] = words_and_counts.get(word, 0) + len(cluster_words)

        return words_and_counts

    async def _search_similar_clusters(
        self,
        query: str,
        model_version: Optional[str] = None,
        top_k: int = 10,
        auto_train: bool = False,
    ) -> Dict[str, Any]:

        _ensure_nlp_imports()
        if not model_version:
            model_version = await self._resolve_model_db_first(auto_train)

        logger.info("Cache kontrol ediliyor")
        if self._cached_version != model_version:
            await self._load_cache(model_version)

        if self._cached_centroids is None or len(self._cached_centroids) == 0:
            raise ValueError(
                f"Model versiyonu için cluster bulunamadı: {model_version}"
            )
        query_cleaned = self._clean_text(query)
        query_embedding = self.embedder.encode([query_cleaned])
        clusters = await self.cluster_repo.find_by_model_version_on_all(
            model_version, include_noise=False
        )

        centroid_list = [cluster.centroid_full for cluster in clusters]
        centroid_matrix = np.vstack(centroid_list)
        try:
            similarities = cosine_similarity(query_embedding, centroid_matrix)[0]
        except ValueError as e:
            if "Incompatible dimension" in str(e):
                logger.error(
                    f"Dimension mismatch: query is {query_embedding.shape[1]}d, centroids are {centroid_matrix.shape[1]}d."
                )
                raise ValueError(
                    "Dimension mismatch between the loaded embedder model and the database clusters. Please retrain the model for this version."
                )
            raise

        best_index = np.argmax(similarities)
        max_similarity = similarities[best_index]
        best_cluster = clusters[best_index]

        return {
            "best_cluster": best_cluster,
            "max_similarity": max_similarity,
            "encoded_query": query_embedding,
            "query": query,
            "model_version": model_version,
        }

    async def _load_cache(self, model_version: str) -> bool:
        """Hızlı arama için cluster centroid'lerini cache'le"""
        try:
            clusters = await self.cluster_repo.find_by_model_version(
                model_version, include_noise=False
            )

            if not clusters:
                return False

            self._cached_version = model_version
            self._cached_centroids = np.array([c.centroid_reduced for c in clusters])
            self._cached_cluster_ids = [c.cluster_id for c in clusters]

            logger.info(f"Loaded cache for {model_version}: {len(clusters)} clusters")
            return True

        except Exception as e:
            logger.error(f"Cache loading failed: {e}")
            return False

    async def search_similar(
        self,
        query: str,
        model_version: Optional[str] = None,
        top_k: int = 10,
        auto_train: bool = False,
    ) -> Dict[str, Any]:
        search_result = await self._search_similar_clusters(
            query, model_version, top_k, auto_train
        )
        best_cluster = search_result["best_cluster"]
        max_similarity = search_result["max_similarity"]
        model_version = search_result["model_version"]

        if not best_cluster:
            resolved_version = model_version or "unknown"
            return {
                "query": query,
                "model_version": resolved_version,
                "similarity_score": 0,
                "cluster_id": None,
                "cluster_label": None,
                "total_in_cluster": None,
                "articles": [],
            }

        articles = await ArticleEmbedding.find(
            {
                "article_id": {"$in": best_cluster.article_ids},
                "model_version": model_version,
            }
        ).to_list()

        top_embeddings = articles[:top_k]
        article_ids = [ae.article_id for ae in top_embeddings]
        article_docs = await Article.find({"_id": {"$in": article_ids}}).to_list()
        article_map = {str(a.id): a for a in article_docs}

        return {
            "query": query,
            "model_version": best_cluster.model_version,
            "similarity_score": float(max_similarity),
            "cluster_id": best_cluster.cluster_id,
            "cluster_label": best_cluster.label,
            "total_in_cluster": best_cluster.article_count,
            "articles": [
                {
                    "id": str(ae.article_id),
                    "title": article_map[str(ae.article_id)].title
                    if str(ae.article_id) in article_map
                    else None,
                    "abstract": article_map[str(ae.article_id)].abstract
                    if str(ae.article_id) in article_map
                    else None,
                    "doi": article_map[str(ae.article_id)].doi
                    if str(ae.article_id) in article_map
                    else None,
                    "url": article_map[str(ae.article_id)].url
                    if str(ae.article_id) in article_map
                    else None,
                    "keywords": ae.article_keywords,
                    "cluster_id": best_cluster.cluster_id,
                    "similarity_score": float(max_similarity),
                }
                for ae in top_embeddings
            ],
        }

    async def get_status(self) -> Dict[str, Any]:
        """Mevcut NLP durumunu getir"""
        latest_run = await self.analysis_repo.get_latest_completed()
        running = await self.analysis_repo.get_running()

        return {
            "has_trained_model": latest_run is not None,
            "latest_model_version": latest_run.model_version if latest_run else None,
            "latest_training_date": latest_run.completed_at.isoformat()
            if latest_run and latest_run.completed_at
            else None,
            "latest_stats": {
                "total_articles": latest_run.total_articles,
                "total_clusters": latest_run.total_clusters,
                "noise_count": latest_run.noise_count,
            }
            if latest_run
            else None,
            "is_training": running is not None,
            "running_version": running.model_version if running else None,
            "cache_loaded": self._cached_version is not None,
            "cached_version": self._cached_version,
        }

    async def get_clusters(
        self, model_version: Optional[str] = None, include_noise: bool = False
    ) -> List[Dict[str, Any]]:
        """Tüm cluster'ları getir"""
        if not model_version:
            latest_run = await self.analysis_repo.get_latest_completed()
            if not latest_run:
                return []
            model_version = latest_run.model_version

        clusters = await self.cluster_repo.find_by_model_version(
            model_version, include_noise=include_noise
        )

        return [
            {
                "id": str(c.id),
                "cluster_id": c.cluster_id,
                "label": c.label,
                "centroid": c.centroid_reduced,
                "article_count": c.article_count,
                "top_keywords": c.top_keywords,
                "sample_titles": c.sample_titles,
                "model_version": c.model_version,
            }
            for c in sorted(clusters, key=lambda x: x.article_count, reverse=True)
        ]

    async def get_cluster_articles_filtered(
        self,
        cluster_id: int,
        model_version: str,
        skip: int = 0,
        limit: int = 15,
        search: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Cluster'ın makalelerini backend'de sayfalama ve başlık araması ile döndürür.
        search varsa cache bypass edilir; yoksa önce cache'e bakılabilir (router üzerinden).
        """
        # Cluster'ı bul
        cluster = await self.cluster_repo.find_by_cluster_id(cluster_id, model_version)
        if not cluster:
            return None

        article_ids = cluster.article_ids

        # MongoDB sorgusu: önce ID kümesini kısıtla, sonra başlık araması uygula
        match_query: Dict[str, Any] = {"_id": {"$in": article_ids}}
        if search and search.strip():
            match_query["title"] = {"$regex": search.strip(), "$options": "i"}

        total = await Article.find(match_query).count()
        articles = await Article.find(match_query).skip(skip).limit(limit).to_list()

        return {
            "cluster_id": cluster_id,
            "total_count": total,
            "skip": skip,
            "limit": limit,
            "articles": [
                {
                    "id": str(a.id),
                    "title": a.title,
                    "doi": a.doi,
                    "url": a.url,
                    "keywords": a.keywords,
                    "publication_date": a.publication_date,
                }
                for a in articles
            ],
        }

    async def get_cluster_detail(
        self,
        cluster_id: int,
        model_version: Optional[str] = None,
        include_articles: bool = True,
        article_limit: int = 50,
    ) -> Optional[Dict[str, Any]]:
        """Cluster detayını getir"""
        if not model_version:
            latest_run = await self.analysis_repo.get_latest_completed()
            if not latest_run:
                return None
            model_version = latest_run.model_version

        cluster = await self.cluster_repo.find_by_cluster_id(cluster_id, model_version)
        if not cluster:
            return None

        result = {
            "id": str(cluster.id),
            "cluster_id": cluster.cluster_id,
            "label": cluster.label,
            "article_count": cluster.article_count,
            "top_keywords": cluster.top_keywords,
            "sample_titles": cluster.sample_titles,
            "model_version": cluster.model_version,
            "created_at": cluster.created_at.isoformat()
            if cluster.created_at
            else None,
        }

        if include_articles:
            # article_limit: sayfalama için ne kadar ID alacağımızı belirler;
            # ancak DB'de bulunmayan (silinmiş) makaleler de olabileceğinden
            # önce tüm ID'leri sorgulayıp sonucu slice'lıyoruz.
            ids_to_fetch = cluster.article_ids[:article_limit]
            articles = await Article.find({"_id": {"$in": ids_to_fetch}}).to_list()

            result["articles"] = [
                {
                    "id": str(a.id),
                    "title": a.title,
                    "doi": a.doi,
                    "url": a.url,
                    "keywords": a.keywords,
                    "publication_date": a.publication_date,
                }
                for a in articles
            ]

        return result

    async def get_article_cluster(
        self, article_id: str, model_version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Makalenin ait olduğu cluster'ı bul"""
        if not model_version:
            latest_run = await self.analysis_repo.get_latest_completed()
            if not latest_run:
                return None
            model_version = latest_run.model_version

        try:
            obj_id = PydanticObjectId(article_id)
        except Exception:
            return None

        cluster = await self.cluster_repo.find_cluster_by_article(obj_id, model_version)
        if not cluster:
            return None

        return {
            "article_id": article_id,
            "cluster_id": cluster.cluster_id,
            "cluster_label": cluster.label,
            "cluster_article_count": cluster.article_count,
            "model_version": model_version,
        }

    async def get_training_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Eğitim geçmişini getir"""
        runs = await self.analysis_repo.get_history(limit=limit)

        return [
            {
                "model_version": r.model_version,
                "status": r.status,
                "total_articles": r.total_articles,
                "total_clusters": r.total_clusters,
                "noise_count": r.noise_count,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "duration_seconds": r.duration_seconds,
                "error_message": r.error_message,
                "parameters": {
                    "embedder_model": r.embedder_model,
                    "umap_n_neighbors": r.umap_n_neighbors,
                    "umap_n_components": r.umap_n_components,
                    "min_cluster_size": r.min_cluster_size,
                    "min_samples": r.min_samples,
                },
            }
            for r in runs
        ]


# Singleton instance
nlp_service = NLPService()
