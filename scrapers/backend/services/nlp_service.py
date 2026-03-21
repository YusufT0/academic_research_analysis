"""
NLP Service
Clustering ve embedding iş mantığı
"""

import re
# import pickle
import numpy as np
import spacy
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from beanie import PydanticObjectId
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sentence_transformers import SentenceTransformer, CrossEncoder
import umap
import hdbscan
from sklearn.metrics.pairwise import cosine_similarity
from keybert import KeyBERT
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
        self.clusterer = hdbscan.HDBSCAN(
                min_cluster_size=settings.nlp_min_cluster_size,
                min_samples=settings.nlp_min_samples
            )
        self.cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        self.reducer = umap.UMAP(
                n_neighbors=settings.nlp_umap_n_neighbors,
                n_components=settings.nlp_umap_n_components,
                metric='cosine',
                random_state=42
            )
        self.encoded_query = None
        self.query = None
        self.cleaner_guy = spacy.load("en_core_web_sm")
        self.kw_model = KeyBERT(model=settings.nlp_embedder_model)
        # Cached data for fast search
        self._cached_version: Optional[str] = None
        self._cached_centroids: Optional[np.ndarray] = None
        self._cached_cluster_ids: Optional[List[int]] = None
        self.articles = None    
        self._initialized = True
        logger.info("NLP Service initialized")
    
    @property
    def embedder(self) -> SentenceTransformer:
        """Lazy load embedder model"""
        if self._embedder is None:
            logger.info(f"Loading embedder: {settings.nlp_embedder_model}")
            try:
                self._embedder = SentenceTransformer(settings.nlp_embedder_model, device = "cuda")
            except:
                print("Cannot link to GPU. Switching to CPU")
                self._embedder = SentenceTransformer(settings.nlp_embedder_model)
                
        return self._embedder
    
    def _clean_text(self, text: str) -> str:
        """Metni NLP için temizle"""
        text = str(text).lower()
        text = re.sub(r'[^a-zçğıöşü\s]', ' ', text)
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
            embeddings_reduced = self.reducer.fit_transform(embeddings_full)
            logger.success(f"Reduced to {embeddings_reduced.shape[1]} dimensions")
            
            # 4. HDBSCAN ile clustering
            logger.info("Clustering with HDBSCAN...")
            cluster_labels = self.clusterer.fit_predict(embeddings_reduced)
            
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
    
    # searc_similar ve graph_input fonksiyonları _search_similar_clusters kullancak.
    # Sadece return typeları farklı.
    
    async def get_date_graph_input(self):

        """
        Bu servis dökümanların yazıldığı tarihleri temizleyip datetime olarak frontend'e gönderir.
        Bu fonksiyonun çalışabilmesi için self.articles boş olmamalı. Yani self._search_similar_articles en az 1 kez çalıştırılmalı.
        """
        prefix_dates = {
            "january" : "1",
            "february" : "2",
            "march" : "3",
            "april" : "4",
            "may" : "5",
            "june" : "6",
            "july" : "7",
            "august" : "8",
            "september" : "9",
            "october" : "10",
            "november" : "11",
            "december" : "12"
            }
        result = {

        }
        
        dates =  [art.publication_date for art in self.articles]
        for date in dates:
            try:
                dt_object = datetime.fromisoformat(date)
                result[dt_object] = result.get(dt_object, 0) + 1
            except:
                print(f"{date} is not convertable to datetime")
                print(f"Trying to fetch date from the string: {date}")
                d = date.lower()
                est_date = ""
                for month, number in prefix_dates.items():
                    if month in d:
                        # [\D]*? -> Skip any number of non-digit characters 
                        # (\d{4}) -> Capture exactly 4 digits 
                        pattern = rf"{month}[\D]*?(\d{{4}})"
                        match = re.search(pattern, d)
                        
                        if match:
                            year = match.group(1) # This is the 4-digit year
                            est_date = f"{year}-{number.zfill(2)}-01" # Adding -01 makes it a valid ISO date
                            
                            try:
                                dt_object = datetime.fromisoformat(est_date)
                                result[dt_object] = result.get(dt_object, 0) + 1
                                print(f"Success: {est_date}")
                            except ValueError:
                                print(f"Failed to parse: {est_date}")
                        else:
                            print(f"Found {month}, but couldn't find a 4-digit year near it.")
                        
                        break
                    
        return result
    
    async def get_scatter_graph_input():
        
        pass

    async def get_pie_chart_input():
        
        pass
    
    async def _extract_relevance_of_articles(self):
        scores = []
        article_ids = self.best_cluster.article_ids

        all_embeddings = await self.embedding_repo.find_many_by_article_ids(article_ids)
        emb_dict = {str(e.article_id): e.embedding_full for e in all_embeddings}
        matrix_embeddings = np.vstack([np.array(emb_dict[str(art.id)]) for art in self.articles])
        reshaped_query = np.array(self.encoded_query).reshape(1, -1)

        reshaped_query = np.array(self.encoded_query).reshape(1, -1)
        scores = cosine_similarity(reshaped_query, matrix_embeddings)[0] # Shape: (50,)
        ranked_results = []
        for i in range(len(self.articles)):
            ranked_results.append({
                "score": scores[i],
                "abstract": self.articles[i].abstract
            })

        ranked_results.sort(key=lambda x: x["score"], reverse=True)
        return ranked_results
    
    def _preprocess_scientific_text(self, text):

        doc = self.cleaner_guy(text) 
        
        tokens = []
        for token in doc:
            is_person = token.ent_type_ == "PERSON"
            
            if (token.pos_ in ["NOUN", "ADJ"] 
                and token.pos_ != "PROPN" 
                and not is_person
                and not token.is_stop 
                and len(token.text) > 2):
                
                tokens.append(token.lemma_.lower())
                
        return " ".join(tokens)
    
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

    async def _take_keywords_and_transform(self, words):
        '''
        
        Bir grup kelimeyi alır bunları kümeler ve kümeleri
        {cluster_idx : [words]}
        olarak döndürür. 
        
        '''

        embedded_words = [self.embedder.encode(word[0]) for word in words]
        embeddings_reduced = self.reducer.fit_transform(embedded_words)
        self.clusterer.set_params(min_cluster_size=3)
        cluster_labels = self.clusterer.fit_predict(embeddings_reduced)

        clusters = {}
        
        for idx, label in enumerate(cluster_labels):
            # if label != -1:
            if label not in clusters:
                clusters[label] = []
            
            word_text = words[idx][0]
            clusters[label].append(word_text)

        return clusters
        
    async def _take_cluster_and_find_word(self, cluster_list):
        '''
        Bir {cluster_idx : [words]} alır ve burada kelimelerden en kapsayıcı olanını belirler.
        Çıktı olarak en kapsayıcı kelimeyi döner. 
        '''
        
        n = len(cluster_list)
        
        running_totals = [0.0] * n 
        
        max_score = -1.0
        max_score_word = cluster_list[0]

        for i in range(n):
            for j in range(i+1, n):
                score = float(self.cross_encoder.predict([(cluster_list[i], cluster_list[j])])[0])
                
                running_totals[i] += score
                running_totals[j] += score

                # Check and update the max on the fly for word 'i'
                if running_totals[i] > max_score:
                    max_score = running_totals[i]
                    max_score_word = cluster_list[i]
                
                # Check and update the max on the fly for word 'j'
                if running_totals[j] > max_score:
                    max_score = running_totals[j]
                    max_score_word = cluster_list[j]

        return max_score_word


    async def _extract_cluster_keywords(self):
        abstracts = [self._preprocess_scientific_text(art.abstract) for art in self.articles]
        
        all_keywords_per_abstract = []
        all_pairs_to_score = []

        for text in abstracts:
            # Extract a few candidate keywords to compare against the query
            extracted = self.kw_model.extract_keywords(
                text, 
                keyphrase_ngram_range=(1, 2), 
                stop_words='english', 
                use_mmr=True,
                diversity=0.2,
                top_n=5 # Extract top 5 candidates to evaluate
            )
            
            # KeyBERT returns [('keyword', score), ...]. Extract just the text.
            kws = [item[0] for item in extracted]
            all_keywords_per_abstract.append(kws)
            
            for kw in kws:
                all_pairs_to_score.append([self.query, kw])

        if not all_pairs_to_score:
            return []
            
        all_scores = await self._eval_keywords(all_pairs_to_score)

        final_max_keywords = []
        score_idx = 0
        
        for kws in all_keywords_per_abstract:
            best_kw = None
            max_score = float('-inf')
            
            for kw in kws:
                score = all_scores[score_idx].item() 
                if score > max_score:
                    max_score = score
                    best_kw = kw
                score_idx += 1
            
            final_max_keywords.append((best_kw, max_score))
        
        return final_max_keywords

    async def word_finding_pipeline(self):
        '''
        Bu fonksiyonun çalışması için de benzer kümelerin oluşturulması gerekiyor.
        search_similar fonksiyonu 1 kez çalıştırıldıktan sonra bu fonksiyon kullanılabilir.


        '''
        words_and_counts = {}
        final_max_keywords = await self._extract_cluster_keywords()
        clusters = await self._take_keywords_and_transform(final_max_keywords)
        
        for key in clusters.keys():
            if key == -1:
                word = "Other"
            else:
                word = await self._take_cluster_and_find_word(clusters[key])
            
            words_and_counts[word] = words_and_counts.get(word, 0) + len(clusters[key])

        return words_and_counts
        
    async def _search_similar_clusters(self,
            query: str,
            model_version: Optional[str] = None,
            top_k: int = 10,
            auto_train: bool = False
        ):

        if not model_version:
            model_version = await self._resolve_model_db_first(auto_train)

        print("WE ARE SO BACK")
        if self._cached_version != model_version:
            await self._load_cache(model_version)

        if self._cached_centroids is None or len(self._cached_centroids) == 0:
            raise ValueError(f"Model versiyonu için cluster bulunamadı: {model_version}")
        self.query = query
        query_cleaned = self._clean_text(query)
        query_embedding = self.embedder.encode([query_cleaned])
        self.encoded_query = query_embedding
        clusters = await self.cluster_repo.find_by_model_version(model_version, include_noise=False)

       
        best_cluster = None
        max_similarity = -1
        centroid_list = [cluster.centroid_full for cluster in clusters]
        centroid_matrix = np.vstack(centroid_list)
        similarities = cosine_similarity(query_embedding, centroid_matrix)[0]

        best_index = np.argmax(similarities)
        max_similarity = similarities[best_index]
        best_cluster = clusters[best_index]

        self.best_cluster = best_cluster
        return best_cluster, max_similarity
   
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
        best_cluster, max_similarity = await self._search_similar_clusters(query, model_version, top_k, auto_train)

        if not best_cluster:
            return {
                "query": query,
                "model_version": model_version,
                "similarity_score": 0,
                "cluster_id": None,
                "cluster_label": None,
                "articles": []
            }

        self.articles = await Article.find(
            {"_id": {"$in": best_cluster.article_ids}}
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
                for a in self.articles[:top_k]
            ]
        }
    async def get_status(self) -> Dict[str, Any]:
        """Mevcut NLP durumunu getir"""
        latest_run = await self.analysis_repo.get_latest_completed()
        running = await self.analysis_repo.get_running()
        
        return {
            "has_trained_model": latest_run is not None,
            "latest_model_version": latest_run.model_version if latest_run else None,
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
                "centroid" : c.centroid_reduced,
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
