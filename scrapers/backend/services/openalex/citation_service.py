import logging
import re
from typing import List, Dict, Any
from datetime import datetime

from backend.services.openalex.client import openalex_client
from database.models import Article, Journal

logger = logging.getLogger(__name__)

def _normalize_doi(doi: str) -> str:
    """Herhangi bir DOI formatını temiz formata indirger (prefix'leri soyar, küçük harf yapar)."""
    return re.sub(r'^(https?://doi\.org/)+', '', doi.strip()).lower()

class CitationService:
    """
    OpenAlex Citation Service.
    Sorumlulukları:
    - Veritabanı modelleriyle (Article, Journal) haberleşerek atıf verilerini tazelemek
    - Toplu (Bulk) işlemleri asenkron olarak yönetmek
    """

    def _parse_historical_counts(self, counts_by_year: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        OpenAlex'in {"year": 2023, "cited_by_count": 10} formatını 
        {"2023": 10} dictionary yapısına çevirir.
        """
        history = {}
        for item in counts_by_year:
            year = str(item.get("year"))
            count = item.get("cited_by_count", 0)
            history[year] = count
        return history

    async def update_articles_citations_bulk(self, articles: List[Article]) -> int:
        """
        Toplu halde gelen Beanie Article objelerinin DOI'lerinden yola çıkarak
        OpenAlex üzerinden Atıf verilerini bulur ve günceller.
        
        Args:
            articles (List[Article]): Güncellenecek makale modelleri
            
        Returns:
            int: Güncellenen makale sayısı
        """
        if not articles:
            return 0

        # Filtreleme: Yalnızca DOI'ye sahip makaleler
        # Anahtar olarak normalize edilmiş DOI kullan (prefix'siz, küçük harf)
        # Böylece DB'de "https://doi.org/10.xxx" formatında saklanan DOI'ler de eşleşir
        doi_mapping = {_normalize_doi(a.doi): a for a in articles if a.doi}
        dois_to_fetch = list(doi_mapping.keys())
        
        if not dois_to_fetch:
            return 0

        works_data = await openalex_client.get_works_by_dois(dois_to_fetch)
        updated_count = 0

        for work in works_data:
            doi_url = work.get("doi", "")
            if not doi_url:
                continue
            # OpenAlex "https://doi.org/10.xxxx" formatında döndürür → normalize et
            normalized = _normalize_doi(doi_url)
            target_article = doi_mapping.get(normalized)

            if not target_article:
                continue

            # Verileri ata
            target_article.openalex_id = work.get("id")
            target_article.is_openalex_indexed = True
            
            target_article.citation_count = work.get("cited_by_count", 0)
            target_article.historical_citation_data = self._parse_historical_counts(work.get("counts_by_year", []))
            
            target_article.fwci = work.get("fwci")
            
            percentile = work.get("cited_by_percentile_year")
            if percentile and "min" in percentile:
                # OpenAlex genelde {"min": 85, "max": 90} şeklinde döndürür
                target_article.citation_percentile = float(percentile.get("min", 0))
            
            # Veritabanında güncelle
            await target_article.save()
            updated_count += 1
            
        return updated_count

    async def update_journal_citation_metrics(self, journal: Journal) -> bool:
        """
        Dergi için OpenAlex üzerindeki "Source" bilgilerini çeker, h-index, 
        i10-index gibi verilerle günceller.
        """
        source_data = await openalex_client.get_source_by_identifier(
            issn=journal.issn or journal.eissn, 
            name=journal.name
        )
        
        if not source_data:
            return False
            
        journal.openalex_id = source_data.get("id")
        
        summary_stats = source_data.get("summary_stats", {})
        if summary_stats:
            journal.h_index = summary_stats.get("h_index")
            journal.i10_index = summary_stats.get("i10_index")
            # OpenAlex source verilerinde cited_by_count var ise
            journal.total_citation_count = source_data.get("cited_by_count", 0)
            
            # Ortalama atıf sayısı mantığı: (Toplam atıf) / (İndekslenmiş makale sayısı)
            works_count = source_data.get("works_count", 0)
            if works_count > 0:
                journal.average_citation_count = round(journal.total_citation_count / works_count, 2)
                
        journal.historical_citation_data = self._parse_historical_counts(source_data.get("counts_by_year", []))
        journal.last_citation_update_date = datetime.utcnow()
        
        await journal.save()
        return True

citation_service = CitationService()
