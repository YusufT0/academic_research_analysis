"""
NLP Service
Clustering ve embedding iş mantığı
"""

import re
import pickle
import numpy as np
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from beanie import PydanticObjectId
from collections import Counter

from sentence_transformers import SentenceTransformer
import umap
import hdbscan
from sklearn.metrics.pairwise import cosine_similarity

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.models import Article, ArticleEmbedding, Cluster, AnalysisRun
from database.repositories import (
    ArticleRepository,
    EmbeddingRepository,
    ClusterRepository,
    AnalysisRunRepository
)
from backend.core.config import settings
from utils.logger import get_logger

logger = get_logger('nlp_service')


class NLPService:
    """
    NLP Service
    
    Clustering, embedding ve benzerlik araması işlemlerini yönetir.
    Singleton pattern ile tek instance kullanılır.
    """
    
    _instance: Optional["NLPService"] = None
    
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
        self._embedder: Optional[SentenceTransformer] = None
        self._reducer: Optional[umap.UMAP] = None
        
        # Cached data for fast search
        self._cached_version: Optional[str] = None
        self._cached_centroids: Optional[np.ndarray] = None
        self._cached_cluster_ids: Optional[List[int]] = None
        
        # Legacy PKL model cache
        self._pkl_loaded: bool = False
        self._pkl_reducer: Optional[umap.UMAP] = None
        self._pkl_clusters: Optional[np.ndarray] = None
        self._pkl_clustered_data: Optional[Dict] = None
        self._pkl_embedded: Optional[np.ndarray] = None
        
        self._initialized = True
        logger.info("NLP Service initialized")
    
    @property
    def embedder(self) -> SentenceTransformer:
        """Lazy load embedder model"""
        if self._embedder is None:
            logger.info(f"Loading embedder: {settings.nlp_embedder_model}")
            self._embedder = SentenceTransformer(settings.nlp_embedder_model)
        return self._embedder
    
    def _clean_text(self, text: str) -> str:
        """Metni NLP için temizle"""
        text = str(text).lower()
        text = re.sub(r'[^a-zçğıöşü\s]', ' ', text)
        return " ".join(text.split())
    
    def _load_pkl_model(self) -> bool:
        """
        Mevcut PKL model dosyasını yükle (legacy support)
        
        Returns:
            bool: Yükleme başarılı ise True
        """
        if self._pkl_loaded:
            return True
        
        pkl_path = settings.nlp_model_full_path
        
        if not pkl_path.exists():
            logger.warning(f"PKL model bulunamadı: {pkl_path}")
            return False
        
        try:
            logger.info(f"Loading legacy PKL model: {pkl_path}")
            with open(pkl_path, "rb") as f:
                state = pickle.load(f)
            
            self._pkl_reducer = state.get("reducer")
            self._pkl_clusters = state.get("clusters")
            self._pkl_clustered_data = state.get("clustered_data", {})
            self._pkl_embedded = state.get("embedded_384")
            self._pkl_loaded = True
            
            n_clusters = len(set(self._pkl_clusters)) - (1 if -1 in self._pkl_clusters else 0)
            logger.success(f"PKL model loaded: {n_clusters} clusters, {len(self._pkl_clustered_data)} data groups")
            return True
            
        except Exception as e:
            logger.error(f"PKL model yüklenemedi: {e}")
            return False
    
    def _search_with_pkl(self, query: str, top_k: int = 10) -> Tuple[List[str], float, int]:
        """
        PKL model ile arama yap (legacy method)
        
        Returns:
            Tuple[data, similarity_score, cluster_id]
        """
        if not self._pkl_loaded:
            if not self._load_pkl_model():
                raise ValueError("PKL model yüklenemedi")
        
        query_cleaned = self._clean_text(query)
        query_vec = self.embedder.encode([query_cleaned])
        
        # UMAP transform
        query_reduced = self._pkl_reducer.transform(query_vec)
        
        # En yakın cluster'ı bul
        unique_labels = [l for l in set(self._pkl_clusters) if l != -1]
        
        if not unique_labels:
            return self._pkl_clustered_data.get(-1, []), 0.0, -1
        
        best_cluster = -1
        max_sim = -1
        
        for label in unique_labels:
            indices = np.where(self._pkl_clusters == label)[0]
            cluster_vectors = self._pkl_embedded[indices]
            centroid = np.mean(cluster_vectors, axis=0).reshape(1, -1)
            similarity = cosine_similarity(query_reduced, centroid)[0][0]
            
            if similarity > max_sim:
                max_sim = similarity
                best_cluster = label
        
        return self._pkl_clustered_data.get(best_cluster, []), float(max_sim), best_cluster
    
    async def _resolve_model_pkl_first(self, auto_train: bool = False) -> Optional[str]:
        """
        Model kaynağını belirle - PKL öncelikli
        
        1. PKL varsa -> "pkl_legacy" döndür
        2. DB'de analiz varsa -> model_version döndür
        3. auto_train=True ise -> eğitim başlat
        4. Hata fırlat
        """
        # 1. Önce PKL'yi dene
        if self._load_pkl_model():
            logger.info("PKL model kullanılıyor (prefer_pkl=true)")
            return "pkl_legacy"
        
        # 2. PKL yoksa DB'ye bak
        latest_run = await self.analysis_repo.get_latest_completed()
        if latest_run:
            logger.info(f"PKL bulunamadı, DB modeli kullanılıyor: {latest_run.model_version}")
            return latest_run.model_version
        
        # 3. İkisi de yoksa
        if auto_train:
            logger.info("Model bulunamadı, otomatik eğitim başlatılıyor...")
            train_result = await self.train_clustering()
            return train_result["model_version"]
        
        raise ValueError(
            "Model bulunamadı. PKL dosyası veya DB'de analiz yok. "
            "auto_train=True ile otomatik eğitim başlatabilirsiniz "
            "veya /nlp/analyze endpoint'ini kullanın."
        )
    
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
        if self._load_pkl_model():
            logger.info("DB'de analiz yok, PKL model kullanılıyor (prefer_pkl=false)")
            return "pkl_legacy"
        
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
    
    async def _search_with_pkl_fallback(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """
        PKL model ile arama yap ve DB formatında sonuç döndür
        
        Returns:
            SearchResponse formatında sonuç
        """
        data, similarity, cluster_id = self._search_with_pkl(query, top_k)
        
        # PKL'den gelen data temizlenmiş abstract metinleri içeriyor
        # Bu metinleri başlık olarak döndürelim (legacy format)
        return {
            "query": query,
            "model_version": "pkl_legacy",
            "similarity_score": similarity,
            "cluster_id": cluster_id,
            "cluster_label": f"PKL Cluster {cluster_id}",
            "total_in_cluster": len(data),
            "articles": [
                {
                    "id": f"pkl_{i}",
                    "title": text[:100] + "..." if len(text) > 100 else text,
                    "abstract": text,
                    "doi": None,
                    "url": None,
                    "keywords": []
                }
                for i, text in enumerate(data[:top_k])
            ]
        }
    
    async def train_clustering(
        self,
        model_version: Optional[str] = None,
        min_abstract_length: int = 50
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
        if not model_version:
            model_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        logger.section(f"NLP Training Started - {model_version}")
        
        # Mevcut analiz kontrolü
        existing_run = await self.analysis_repo.get_running()
        if existing_run:
            raise ValueError(f"Bir analiz zaten çalışıyor: {existing_run.model_version}")
        
        # Analiz kaydı oluştur
        run = await self.analysis_repo.create_run(
            model_version=model_version,
            embedder_model=settings.nlp_embedder_model,
            umap_n_neighbors=settings.nlp_umap_n_neighbors,
            umap_n_components=settings.nlp_umap_n_components,
            min_cluster_size=settings.nlp_min_cluster_size,
            min_samples=settings.nlp_min_samples
        )
        await self.analysis_repo.start_run(run)
        
        try:
            # 1. Makaleleri getir
            logger.info("Fetching articles from database...")
            articles = await Article.find(
                {"abstract": {"$exists": True, "$ne": None}}
            ).to_list()
            
            # Abstract'ı olan ve yeterli uzunlukta olanları filtrele
            valid_articles = []
            for article in articles:
                if article.abstract and len(article.abstract) >= min_abstract_length:
                    valid_articles.append(article)
            
            if len(valid_articles) < settings.nlp_min_cluster_size:
                raise ValueError(
                    f"Yetersiz makale sayısı: {len(valid_articles)} "
                    f"(minimum: {settings.nlp_min_cluster_size})"
                )
            
            logger.info(f"Found {len(valid_articles)} valid articles")
            
            # 2. Metinleri temizle ve embedding oluştur
            logger.info("Cleaning texts and generating embeddings...")
            cleaned_texts = []
            article_ids = []
            
            for article in valid_articles:
                cleaned = self._clean_text(article.abstract)
                if cleaned:
                    cleaned_texts.append(cleaned)
                    article_ids.append(article.id)
            
            # Embedding
            embeddings_full = self.embedder.encode(cleaned_texts, show_progress_bar=True)
            logger.success(f"Generated {len(embeddings_full)} embeddings (dim: {embeddings_full.shape[1]})")
            
            # 3. UMAP ile boyut indirgeme
            logger.info("Reducing dimensions with UMAP...")
            reducer = umap.UMAP(
                n_neighbors=settings.nlp_umap_n_neighbors,
                n_components=settings.nlp_umap_n_components,
                metric='cosine',
                random_state=42
            )
            embeddings_reduced = reducer.fit_transform(embeddings_full)
            logger.success(f"Reduced to {embeddings_reduced.shape[1]} dimensions")
            
            # 4. HDBSCAN ile clustering
            logger.info("Clustering with HDBSCAN...")
            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=settings.nlp_min_cluster_size,
                min_samples=settings.nlp_min_samples
            )
            cluster_labels = clusterer.fit_predict(embeddings_reduced)
            
            n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
            noise_count = (cluster_labels == -1).sum()
            logger.success(f"Found {n_clusters} clusters, {noise_count} noise points")
            
            # 5. Eski verileri temizle (aynı versiyon varsa)
            await self.embedding_repo.delete_by_model_version(model_version)
            await self.cluster_repo.delete_by_model_version(model_version)
            
            # 6. Embedding'leri kaydet
            logger.info("Saving embeddings to database...")
            embedding_docs = []
            for i, article_id in enumerate(article_ids):
                embedding_doc = ArticleEmbedding(
                    article_id=article_id,
                    embedding_full=embeddings_full[i].tolist(),
                    embedding_reduced=embeddings_reduced[i].tolist(),
                    text_cleaned=cleaned_texts[i],
                    model_version=model_version
                )
                embedding_docs.append(embedding_doc)
            
            await self.embedding_repo.bulk_create(embedding_docs)
            logger.success(f"Saved {len(embedding_docs)} embeddings")
            
            # 7. Cluster'ları kaydet
            logger.info("Saving clusters to database...")
            cluster_docs = await self._create_cluster_documents(
                cluster_labels=cluster_labels,
                embeddings_full=embeddings_full,
                embeddings_reduced=embeddings_reduced,
                article_ids=article_ids,
                valid_articles=valid_articles,
                model_version=model_version
            )
            
            await self.cluster_repo.bulk_create(cluster_docs)
            logger.success(f"Saved {len(cluster_docs)} clusters")
            
            # 8. Analiz kaydını tamamla
            await self.analysis_repo.complete_run(
                run=run,
                total_articles=len(valid_articles),
                total_clusters=n_clusters,
                noise_count=int(noise_count)
            )
            
            # Cache'i güncelle
            await self._load_cache(model_version)
            
            logger.section("Training Completed")
            
            return {
                "model_version": model_version,
                "total_articles": len(valid_articles),
                "total_clusters": n_clusters,
                "noise_count": int(noise_count),
                "embedding_dim_full": embeddings_full.shape[1],
                "embedding_dim_reduced": embeddings_reduced.shape[1],
                "status": "completed"
            }
            
        except Exception as e:
            await self.analysis_repo.fail_run(run, str(e))
            logger.error(f"Training failed: {e}")
            raise
    
    async def _create_cluster_documents(
        self,
        cluster_labels: np.ndarray,
        embeddings_full: np.ndarray,
        embeddings_reduced: np.ndarray,
        article_ids: List[PydanticObjectId],
        valid_articles: List[Article],
        model_version: str
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
            
            for idx in indices[:10]:  # İlk 10 makale
                article = id_to_article.get(article_ids[idx])
                if article:
                    if article.keywords:
                        top_keywords.extend(article.keywords)
                    if article.title and len(sample_titles) < 5:
                        sample_titles.append(article.title)
            
            # En sık geçen keywords
            keyword_counts = Counter(top_keywords)
            top_keywords = [kw for kw, _ in keyword_counts.most_common(10)]
            
            # Cluster label oluştur
            label_text = None
            if label != -1 and top_keywords:
                label_text = ", ".join(top_keywords[:3])
            elif label == -1:
                label_text = "Noise / Unclustered"
            
            cluster_doc = Cluster(
                cluster_id=int(label),
                centroid_full=centroid_full.tolist(),
                centroid_reduced=centroid_reduced.tolist(),
                article_ids=cluster_article_ids,
                label=label_text,
                top_keywords=top_keywords,
                sample_titles=sample_titles,
                article_count=len(indices),
                model_version=model_version
            )
            cluster_docs.append(cluster_doc)
        
        return cluster_docs
    
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
        auto_train: bool = False
    ) -> Dict[str, Any]:
        """
        Query'ye benzer makaleleri bul
        
        Args:
            query: Arama sorgusu
            model_version: Model versiyonu (None ise en son)
            top_k: Döndürülecek makale sayısı
            auto_train: Analiz yoksa otomatik eğitim başlat
            
        Returns:
            Benzer makaleler ve similarity skoru
        """
        # Model versiyonunu belirle
        if not model_version:
            # Tercih ayarına göre öncelik belirle
            if settings.nlp_prefer_pkl:
                # Önce PKL'yi dene
                model_version = await self._resolve_model_pkl_first(auto_train)
            else:
                # Önce DB'yi dene
                model_version = await self._resolve_model_db_first(auto_train)
        
        # PKL model kullanılacaksa direkt PKL ile ara
        if model_version == "pkl_legacy":
            return await self._search_with_pkl_fallback(query, top_k)
        
        # Cache kontrol
        if self._cached_version != model_version:
            await self._load_cache(model_version)
        
        if self._cached_centroids is None or len(self._cached_centroids) == 0:
            raise ValueError(f"Model versiyonu için cluster bulunamadı: {model_version}")
        
        # Query embedding
        query_cleaned = self._clean_text(query)
        query_embedding = self.embedder.encode([query_cleaned])
        
        # UMAP transform için mevcut reducer'ı kullanmamız gerekiyor
        # Şimdilik full embedding ile centroid karşılaştırması yapalım
        # Ya da reduced centroid yerine full centroid kullanalım
        
        # En yakın cluster'ı bul (full embedding ile)
        clusters = await self.cluster_repo.find_by_model_version(model_version, include_noise=False)
        
        best_cluster = None
        max_similarity = -1
        
        for cluster in clusters:
            centroid = np.array(cluster.centroid_full).reshape(1, -1)
            similarity = cosine_similarity(query_embedding, centroid)[0][0]
            
            if similarity > max_similarity:
                max_similarity = similarity
                best_cluster = cluster
        
        if not best_cluster:
            return {
                "query": query,
                "model_version": model_version,
                "similarity_score": 0,
                "cluster_id": None,
                "cluster_label": None,
                "articles": []
            }
        
        # Cluster'daki makaleleri getir
        articles = await Article.find(
            {"_id": {"$in": best_cluster.article_ids[:top_k]}}
        ).to_list()
        
        return {
            "query": query,
            "model_version": model_version,
            "similarity_score": float(max_similarity),
            "cluster_id": best_cluster.cluster_id,
            "cluster_label": best_cluster.label,
            "total_in_cluster": best_cluster.article_count,
            "articles": [
                {
                    "id": str(a.id),
                    "title": a.title,
                    "abstract": a.abstract[:300] + "..." if a.abstract and len(a.abstract) > 300 else a.abstract,
                    "doi": a.doi,
                    "url": a.url,
                    "keywords": a.keywords
                }
                for a in articles
            ]
        }
    
    async def get_status(self) -> Dict[str, Any]:
        """Mevcut NLP durumunu getir"""
        latest_run = await self.analysis_repo.get_latest_completed()
        running = await self.analysis_repo.get_running()
        
        # PKL model kontrolü
        pkl_available = settings.nlp_model_full_path.exists()
        pkl_loaded = self._pkl_loaded
        
        return {
            "has_trained_model": latest_run is not None or pkl_available,
            "latest_model_version": latest_run.model_version if latest_run else ("pkl_legacy" if pkl_available else None),
            "latest_training_date": latest_run.completed_at.isoformat() if latest_run and latest_run.completed_at else None,
            "latest_stats": {
                "total_articles": latest_run.total_articles,
                "total_clusters": latest_run.total_clusters,
                "noise_count": latest_run.noise_count
            } if latest_run else None,
            "is_training": running is not None,
            "running_version": running.model_version if running else None,
            "cache_loaded": self._cached_version is not None,
            "cached_version": self._cached_version,
            # PKL bilgileri
            "pkl_model_available": pkl_available,
            "pkl_model_loaded": pkl_loaded,
            "pkl_model_path": str(settings.nlp_model_full_path) if pkl_available else None
        }
    
    async def get_clusters(
        self,
        model_version: Optional[str] = None,
        include_noise: bool = False
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
                "article_count": c.article_count,
                "top_keywords": c.top_keywords,
                "sample_titles": c.sample_titles,
                "model_version": c.model_version
            }
            for c in sorted(clusters, key=lambda x: x.article_count, reverse=True)
        ]
    
    async def get_cluster_detail(
        self,
        cluster_id: int,
        model_version: Optional[str] = None,
        include_articles: bool = True,
        article_limit: int = 50
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
            "created_at": cluster.created_at.isoformat() if cluster.created_at else None
        }
        
        if include_articles:
            articles = await Article.find(
                {"_id": {"$in": cluster.article_ids[:article_limit]}}
            ).to_list()
            
            result["articles"] = [
                {
                    "id": str(a.id),
                    "title": a.title,
                    "doi": a.doi,
                    "url": a.url,
                    "keywords": a.keywords,
                    "publication_date": a.publication_date
                }
                for a in articles
            ]
        
        return result
    
    async def get_article_cluster(
        self,
        article_id: str,
        model_version: Optional[str] = None
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
            "model_version": model_version
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
                    "min_samples": r.min_samples
                }
            }
            for r in runs
        ]


# Singleton instance
nlp_service = NLPService()
