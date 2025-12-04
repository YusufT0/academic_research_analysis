"""
JSON to MongoDB Migration Script
Mevcut JSON verilerini MongoDB'ye aktarır
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_database_service, close_database
from database.models import Journal, Issue, Article
from utils.logger import get_logger

logger = get_logger('migration')


class JSONToMongoMigration:
    """JSON verilerini MongoDB'ye aktarır"""
    
    def __init__(self):
        self.service = None
        self.stats = {
            "journals_created": 0,
            "journals_updated": 0,
            "issues_created": 0,
            "issues_updated": 0,
            "articles_created": 0,
            "articles_updated": 0,
            "errors": 0
        }
    
    async def initialize(self):
        """Service'i başlat"""
        self.service = await init_database_service()
        logger.success("Migration service hazır")
    
    async def close(self):
        """Bağlantıyı kapat"""
        await close_database()
    
    async def migrate_json_file(self, json_path: str) -> Dict[str, int]:
        """
        Tek bir JSON dosyasını migrate et
        
        Args:
            json_path: JSON dosyasının yolu
        
        Returns:
            dict: İstatistikler
        """
        logger.header(f"MIGRATION: {Path(json_path).name}")
        
        # JSON'u oku
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"JSON okuma hatası: {e}")
            return self.stats
        
        source_website = data.get('website', 'unknown')
        journals_data = data.get('journals', [])
        
        logger.info(f"Kaynak: {source_website}")
        logger.info(f"Toplam dergi: {len(journals_data)}")
        
        # Her dergiyi işle
        for journal_idx, journal_data in enumerate(journals_data, 1):
            try:
                await self._migrate_journal(journal_data, source_website, journal_idx, len(journals_data))
            except Exception as e:
                import traceback
                logger.error(f"Dergi migration hatası: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                self.stats["errors"] += 1
        
        return self.stats
    
    async def _migrate_journal(
        self,
        journal_data: Dict[str, Any],
        source_website: str,
        index: int,
        total: int
    ):
        """Tek bir dergiyi migrate et"""
        journal_name = journal_data.get('name', 'Unknown')
        logger.subsection(f"[{index}/{total}] {journal_name}")
        
        # Dergi oluştur/güncelle
        journal, created = await self.service.add_journal(
            name=journal_name,
            source_website=source_website,
            url=journal_data.get('url'),
            publisher=journal_data.get('publisher'),
            open_access=journal_data.get('open_access', False),
            letter_group=journal_data.get('letter_group'),
            journal_type=journal_data.get('type', 'Journal')
        )
        
        if created:
            self.stats["journals_created"] += 1
        else:
            self.stats["journals_updated"] += 1
        
        # Issues işle
        issues_data = journal_data.get('issues', [])
        for issue_data in issues_data:
            await self._migrate_issue(issue_data, journal)
    
    async def _migrate_issue(
        self,
        issue_data: Dict[str, Any],
        journal: Journal
    ):
        """Tek bir sayıyı migrate et"""
        issue_number = issue_data.get('issue_number')
        
        # Issue oluştur/güncelle
        issue, created = await self.service.add_issue(
            journal=journal,
            issue_number=issue_number,
            date=issue_data.get('date'),
            url=issue_data.get('url'),
            status=issue_data.get('status')
        )
        
        if created:
            self.stats["issues_created"] += 1
        else:
            self.stats["issues_updated"] += 1
        
        # Articles işle
        articles_data = issue_data.get('articles', [])
        if articles_data:
            logger.info(f"  {len(articles_data)} makale işleniyor...")
            
            for article_data in articles_data:
                await self._migrate_article(article_data, issue)
    
    async def _migrate_article(
        self,
        article_data: Dict[str, Any],
        issue: Issue
    ):
        """Tek bir makaleyi migrate et"""
        title = article_data.get('title', '')
        url = article_data.get('url', '')
        
        if not title or not url:
            return
        
        try:
            article, created = await self.service.add_article(
                issue=issue,
                title=title,
                url=url,
                doi=article_data.get('doi'),
                authors=article_data.get('authors', []),
                abstract=article_data.get('abstract'),
                introduction=article_data.get('introduction'),
                keywords=article_data.get('keywords', []),
                publication_date=article_data.get('publication_date'),
                pages=article_data.get('pages'),
                publisher=article_data.get('publisher'),
                article_type=article_data.get('article_type'),
                pdf_url=article_data.get('pdf_url'),
                citation_count=article_data.get('citation_count', 0),
                references=article_data.get('references', [])
            )
            
            if created:
                self.stats["articles_created"] += 1
            else:
                self.stats["articles_updated"] += 1
                
        except Exception as e:
            logger.warning(f"Makale hatası: {title[:30]}... - {e}")
            self.stats["errors"] += 1
    
    def print_stats(self):
        """İstatistikleri yazdır"""
        logger.header("MIGRATION SONUÇLARI")
        logger.stats({
            "Yeni Dergiler": self.stats["journals_created"],
            "Güncellenen Dergiler": self.stats["journals_updated"],
            "Yeni Sayılar": self.stats["issues_created"],
            "Güncellenen Sayılar": self.stats["issues_updated"],
            "Yeni Makaleler": self.stats["articles_created"],
            "Güncellenen Makaleler": self.stats["articles_updated"],
            "Hatalar": self.stats["errors"]
        })


async def migrate_all():
    """Tüm JSON dosyalarını migrate et"""
    migration = JSONToMongoMigration()
    
    try:
        await migration.initialize()
        
        # JSON dosyalarının konumları (sadece scraper klasörlerindeki dosyalar)
        base_path = Path(__file__).parent.parent
        json_files = [
            base_path / "ieee_xplore" / "data" / "ieeexplore_articles.json",
            base_path / "science_direct" / "data" / "sciencedirect_articles.json",
        ]
        
        for json_file in json_files:
            if json_file.exists():
                logger.section(f"Dosya: {json_file.name}")
                await migration.migrate_json_file(str(json_file))
            else:
                logger.warning(f"Dosya bulunamadı: {json_file}")
        
        migration.print_stats()
        
        # Database istatistiklerini göster
        await migration.service.print_statistics()
        
    finally:
        await migration.close()


async def migrate_single_file(json_path: str):
    """Tek bir JSON dosyasını migrate et"""
    migration = JSONToMongoMigration()
    
    try:
        await migration.initialize()
        await migration.migrate_json_file(json_path)
        migration.print_stats()
    finally:
        await migration.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="JSON to MongoDB Migration")
    parser.add_argument(
        "--file", "-f",
        help="Migrate edilecek JSON dosyası (belirtilmezse tüm dosyalar)",
        default=None
    )
    
    args = parser.parse_args()
    
    if args.file:
        asyncio.run(migrate_single_file(args.file))
    else:
        asyncio.run(migrate_all())
