"""
Academic Data Manager
Farklı journal kaynaklarından toplanan verileri standart JSON formatında yönetir

Hiyerarşik Yapı:
  Website
    └── Journal (dergi)
          └── Issue (sayı) 
                └── Article (makale)
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import hashlib

from .logger import get_logger
logger = get_logger('data_manager')


class AcademicDataManager:
    """
    Akademik makale verilerini standart JSON formatında yönetir
    Her website için ayrı JSON dosyası oluşturur
    
    Hiyerarşi: Website > Journal > Issue > Article
    """
    
    def __init__(self, website_name: str, output_dir: str = "./data"):
        """
        Academic Data Manager'ı başlatır
        
        Args:
            website_name: Website adı (sciencedirect, ieeexplore, arxiv, etc.)
            output_dir: JSON dosyalarının kaydedileceği klasör
        """
        self.website_name = website_name.lower()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON dosya yolu
        self.json_file = self.output_dir / f"{self.website_name}_articles.json"
        
        # Veri yapısı - Yeni hiyerarşik format
        self.data = self._create_empty_structure()
        
        # Eğer dosya varsa yükle
        if self.json_file.exists():
            self._load_existing_data()
        
        logger.success(f"Academic Data Manager başlatıldı: {self.website_name}")
        logger.info(f"JSON dosyası: {self.json_file.absolute()}")
    
    def _create_empty_structure(self) -> Dict:
        """Boş veri yapısı oluşturur"""
        return {
            'website': self.website_name,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'statistics': {
                'total_journals': 0,
                'total_issues': 0,
                'total_articles': 0
            },
            'journals': []
        }
    
    def _load_existing_data(self):
        """Mevcut JSON dosyasını yükler"""
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                
                # Eski format kontrolü ve migration
                if 'statistics' not in existing_data:
                    logger.info("Eski format algılandı, yeni formata dönüştürülüyor...")
                    self.data = self._migrate_old_format(existing_data)
                    self._save_to_json()  # Yeni formatı kaydet
                else:
                    self.data = existing_data
                    # Kullanılmayan alanları temizle ve volume->issue_number migration
                    self._cleanup_deprecated_fields()
                
                stats = self.data.get('statistics', {})
                logger.success(f"Mevcut veri yüklendi: {stats.get('total_journals', 0)} journal, "
                      f"{stats.get('total_issues', 0)} issue, {stats.get('total_articles', 0)} makale")
        except Exception as e:
            logger.warning(f"Mevcut veri yüklenemedi, yeni dosya oluşturulacak: {e}")
    
    def _cleanup_deprecated_fields(self):
        """Kullanılmayan alanları temizler ve volume->issue_number migration yapar"""
        needs_save = False
        
        for journal in self.data.get('journals', []):
            # ISSN alanını kaldır
            if 'issn' in journal:
                del journal['issn']
                needs_save = True
            
            # Issue'lardaki volume'u issue_number'a taşı
            for issue in journal.get('issues', []):
                if 'volume' in issue:
                    # Eğer issue_number boşsa volume'u oraya taşı
                    if not issue.get('issue_number') and issue.get('volume'):
                        issue['issue_number'] = issue['volume']
                    del issue['volume']
                    needs_save = True
        
        if needs_save:
            logger.info("Kullanılmayan alanlar temizlendi (issn, volume->issue_number)")
            self._save_to_json()
    
    def _migrate_old_format(self, old_data: Dict) -> Dict:
        """Eski formatı yeni Issue-bazlı formata dönüştürür"""
        new_data = self._create_empty_structure()
        new_data['created_at'] = old_data.get('created_at', datetime.now().isoformat())
        
        for old_journal in old_data.get('journals', []):
            # Issue bilgilerini makalelerden çıkar
            issues_map = {}
            
            for article in old_journal.get('articles', []):
                # Issue anahtarı oluştur
                issue_number = article.get('issue_volume') or 'Unknown'
                issue_date = article.get('issue_date') or 'Unknown'
                issue_key = f"{issue_number}_{issue_date}"
                
                if issue_key not in issues_map:
                    issues_map[issue_key] = {
                        'issue_number': issue_number if issue_number != 'Unknown' else None,
                        'date': issue_date if issue_date != 'Unknown' else None,
                        'articles': []
                    }
                
                # Makaleyi issue'ya ekle (eski alanları temizle)
                article_clean = {k: v for k, v in article.items() 
                               if k not in ['issue_volume', 'issue_date', 'journal_name', 'journal_url']}
                
                # ID ekle
                article_clean['id'] = self._generate_article_id(
                    article.get('doi'), article.get('url'), article.get('title'))
                
                issues_map[issue_key]['articles'].append(article_clean)
            
            # Journal'ı yeni formatta oluştur (ISSN olmadan)
            new_journal = {
                'name': old_journal.get('name'),
                'url': old_journal.get('url'),
                'type': old_journal.get('type', 'Journal'),
                'open_access': old_journal.get('open_access', False),
                'letter_group': old_journal.get('letter_group'),
                'publisher': old_journal.get('publisher'),
                'added_at': old_journal.get('added_at', datetime.now().isoformat()),
                'last_scraped_at': datetime.now().isoformat(),
                'issue_count': len(issues_map),
                'article_count': sum(len(issue['articles']) for issue in issues_map.values()),
                'issues': []
            }
            
            # Issue'ları ekle
            for issue_key, issue_data in issues_map.items():
                issue = {
                    'id': self._generate_issue_id(old_journal.get('name', ''), issue_data['issue_number'], issue_data['date']),
                    'issue_number': issue_data['issue_number'],
                    'date': issue_data['date'],
                    'status': None,
                    'url': None,
                    'scraped_at': datetime.now().isoformat(),
                    'article_count': len(issue_data['articles']),
                    'articles': issue_data['articles']
                }
                new_journal['issues'].append(issue)
            
            # ISSN alanını kaldır (artık kullanılmıyor)
            if 'issn' in new_journal:
                del new_journal['issn']
            
            new_data['journals'].append(new_journal)
        
        # İstatistikleri güncelle
        self._update_statistics_for_data(new_data)
        
        return new_data
    
    def _generate_issue_id(self, journal_name: str, issue_number: str, date: str) -> str:
        """Benzersiz issue ID'si oluşturur"""
        unique_str = f"{journal_name}_{issue_number}_{date}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:12]
    
    def _generate_article_id(self, doi: str = None, url: str = None, title: str = None) -> str:
        """Benzersiz article ID'si oluşturur"""
        if doi:
            return hashlib.md5(doi.encode()).hexdigest()[:12]
        elif url:
            return hashlib.md5(url.encode()).hexdigest()[:12]
        elif title:
            return hashlib.md5(title.encode()).hexdigest()[:12]
        else:
            return hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:12]
    
    def add_journal_with_issue(self, journal_info: Dict, issue_info: Dict, articles: List[Dict]) -> bool:
        """
        Bir journal'a yeni bir issue ve makaleleri ekler
        
        Args:
            journal_info: Journal bilgileri (name, url, type, open_access, etc.)
            issue_info: Issue bilgileri (volume, date, status, url)
            articles: Makale listesi
            
        Returns:
            bool: Başarılı ise True
        """
        try:
            # Journal adı zorunlu
            if not journal_info.get('name'):
                logger.warning("Journal adı bulunamadı, atlanıyor")
                return False
            
            journal_name = journal_info['name']
            
            # Journal zaten var mı kontrol et
            existing_journal_idx = None
            for idx, j in enumerate(self.data['journals']):
                if j['name'] == journal_name:
                    existing_journal_idx = idx
                    break
            
            # Issue bilgilerini oluştur
            issue_number = issue_info.get('issue_number')
            issue_date = issue_info.get('date')
            issue_id = self._generate_issue_id(journal_name, issue_number, issue_date)
            
            # Makale verilerini oluştur
            article_list = []
            for article in articles:
                article_data = self._create_article_data(article)
                article_list.append(article_data)
            
            # Issue verisi oluştur
            issue_data = {
                'id': issue_id,
                'issue_number': issue_number,
                'date': issue_date,
                'status': issue_info.get('status'),
                'url': issue_info.get('url'),
                'scraped_at': datetime.now().isoformat(),
                'article_count': len(article_list),
                'articles': article_list
            }
            
            if existing_journal_idx is not None:
                # Journal var, issue'yu kontrol et
                journal = self.data['journals'][existing_journal_idx]
                
                # Aynı issue var mı?
                existing_issue_idx = None
                for idx, iss in enumerate(journal.get('issues', [])):
                    if iss['id'] == issue_id:
                        existing_issue_idx = idx
                        break
                
                if existing_issue_idx is not None:
                    # Issue güncelle (duplicate kontrolü ile)
                    logger.info(f"Issue güncelleniyor: {issue_number} - {issue_date}")
                    existing_articles = journal['issues'][existing_issue_idx].get('articles', [])
                    
                    # DOI veya URL ile duplicate kontrolü
                    existing_dois = {a.get('doi') for a in existing_articles if a.get('doi')}
                    existing_urls = {a.get('url') for a in existing_articles if a.get('url')}
                    
                    new_articles = []
                    for article in article_list:
                        if article.get('doi') and article['doi'] in existing_dois:
                            continue  # DOI zaten var
                        if article.get('url') and article['url'] in existing_urls:
                            continue  # URL zaten var
                        new_articles.append(article)
                    
                    # Yeni makaleleri ekle
                    existing_articles.extend(new_articles)
                    journal['issues'][existing_issue_idx]['articles'] = existing_articles
                    journal['issues'][existing_issue_idx]['article_count'] = len(existing_articles)
                    journal['issues'][existing_issue_idx]['scraped_at'] = datetime.now().isoformat()
                    
                    logger.success(f"{len(new_articles)} yeni makale eklendi ({len(article_list) - len(new_articles)} duplicate atlandı)")
                else:
                    # Yeni issue ekle
                    logger.success(f"Yeni issue ekleniyor: {issue_number} - {issue_date}")
                    if 'issues' not in journal:
                        journal['issues'] = []
                    journal['issues'].append(issue_data)
                
                # Journal istatistiklerini güncelle
                journal['issue_count'] = len(journal.get('issues', []))
                journal['article_count'] = sum(iss['article_count'] for iss in journal.get('issues', []))
                journal['last_scraped_at'] = datetime.now().isoformat()
                
            else:
                # Yeni journal oluştur
                logger.success(f"Yeni journal ekleniyor: {journal_name}")
                journal_data = {
                    'name': journal_info.get('name'),
                    'url': journal_info.get('url'),
                    'type': journal_info.get('type', 'Journal'),
                    'open_access': journal_info.get('open_access', False),
                    'letter_group': journal_info.get('letter_group'),
                    'publisher': journal_info.get('publisher'),
                    'added_at': datetime.now().isoformat(),
                    'last_scraped_at': datetime.now().isoformat(),
                    'issue_count': 1,
                    'article_count': len(article_list),
                    'issues': [issue_data]
                }
                self.data['journals'].append(journal_data)
            
            # İstatistikleri güncelle
            self._update_statistics()
            
            # JSON'a kaydet
            self._save_to_json()
            
            logger.success(f"{journal_name} / {issue_number}: {len(articles)} makale kaydedildi")
            return True
            
        except Exception as e:
            logger.failed("Journal/Issue ekleme hatası", e)
            import traceback
            traceback.print_exc()
            return False
    
    def add_journal_with_articles(self, journal_info: Dict, articles: List[Dict], issue_info: Dict = None) -> bool:
        """
        Geriye uyumluluk için - Bir journal'ı ve makalelerini ekler
        Issue bilgisi makalelerden veya parametre olarak alınır
        
        Args:
            journal_info: Journal bilgileri
            articles: Makale listesi
            issue_info: İsteğe bağlı issue bilgisi {'issue_number', 'date', 'url', 'status'}
            
        Returns:
            bool: Başarılı ise True
        """
        # Issue bilgisini parametre, journal_info veya ilk makaleden al
        if issue_info and (issue_info.get('issue_number') or issue_info.get('date')):
            # Parametre olarak geçilen issue_info'yu kullan
            final_issue_info = {
                'issue_number': issue_info.get('issue_number'),
                'date': issue_info.get('date'),
                'status': issue_info.get('status'),
                'url': issue_info.get('url')
            }
        else:
            # Fallback: journal_info veya ilk makaleden al
            final_issue_info = {
                'issue_number': journal_info.get('latest_issue_number') or (articles[0].get('issue_volume') if articles else None),
                'date': journal_info.get('latest_issue_date') or (articles[0].get('issue_date') if articles else None),
                'status': journal_info.get('latest_issue_status'),
                'url': journal_info.get('latest_issue_url')
            }
        
        return self.add_journal_with_issue(journal_info, final_issue_info, articles)
    
    def _create_article_data(self, article: Dict) -> Dict:
        """
        Makale verisini standart formata dönüştürür
        
        Args:
            article: Makale bilgileri
            
        Returns:
            dict: Standart formatlı makale verisi
        """
        article_data = {
            'id': self._generate_article_id(article.get('doi'), article.get('url'), article.get('title')),
            'title': article.get('title'),
            'url': article.get('url'),
            'pdf_url': article.get('pdf_url'),
            'doi': article.get('doi'),
            'authors': article.get('authors', []),
            'abstract': article.get('abstract'),
            'introduction': article.get('introduction'),
            'keywords': article.get('keywords', []),
            'publication_date': article.get('publication_date'),
            'pages': article.get('pages'),
            'publisher': article.get('publisher'),
            'article_type': article.get('article_type', 'Research article'),
            'citation_count': article.get('citation_count', 0),
            'references': article.get('references', []),
            'added_at': datetime.now().isoformat()
        }
        
        return article_data
    
    def _update_statistics(self):
        """İstatistikleri günceller"""
        self._update_statistics_for_data(self.data)
    
    def _update_statistics_for_data(self, data: Dict):
        """Verilen data için istatistikleri günceller"""
        total_issues = 0
        total_articles = 0
        
        for journal in data['journals']:
            total_issues += journal.get('issue_count', len(journal.get('issues', [])))
            total_articles += journal.get('article_count', 
                sum(iss.get('article_count', len(iss.get('articles', []))) 
                    for iss in journal.get('issues', [])))
        
        data['statistics'] = {
            'total_journals': len(data['journals']),
            'total_issues': total_issues,
            'total_articles': total_articles
        }
        data['updated_at'] = datetime.now().isoformat()
    
    def _save_to_json(self):
        """Veriyi JSON dosyasına kaydeder"""
        try:
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON kaydedildi: {self.json_file.name}")
        except Exception as e:
            logger.error(f"JSON kaydetme hatası: {e}")
    
    def get_journal(self, journal_name: str) -> Optional[Dict]:
        """Belirli bir journal'ın verilerini getirir"""
        for journal in self.data['journals']:
            if journal['name'] == journal_name:
                return journal
        return None
    
    def get_issue(self, journal_name: str, issue_number: str = None, date: str = None) -> Optional[Dict]:
        """Belirli bir issue'yu getirir"""
        journal = self.get_journal(journal_name)
        if not journal:
            return None
        
        for issue in journal.get('issues', []):
            if issue_number and issue.get('issue_number') == issue_number:
                return issue
            if date and issue.get('date') == date:
                return issue
        return None
    
    def get_all_articles(self) -> List[Dict]:
        """Tüm makaleleri düz bir liste olarak döndürür"""
        all_articles = []
        for journal in self.data['journals']:
            for issue in journal.get('issues', []):
                for article in issue.get('articles', []):
                    article_copy = article.copy()
                    article_copy['journal_name'] = journal['name']
                    article_copy['journal_url'] = journal['url']
                    article_copy['issue_number'] = issue.get('issue_number')
                    article_copy['issue_date'] = issue.get('date')
                    all_articles.append(article_copy)
        return all_articles
    
    def get_articles_by_doi(self, doi: str) -> Optional[Dict]:
        """DOI ile makale arar"""
        for article in self.get_all_articles():
            if article.get('doi') == doi:
                return article
        return None
    
    def export_articles_only(self, output_file: Optional[str] = None) -> str:
        """Sadece makaleleri içeren ayrı bir JSON dosyası oluşturur"""
        if output_file is None:
            output_file = self.output_dir / f"{self.website_name}_articles_only.json"
        else:
            output_file = Path(output_file)
        
        articles = self.get_all_articles()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        
        logger.success(f"Sadece makaleler dışa aktarıldı: {output_file}")
        logger.info(f"Toplam {len(articles)} makale")
        
        return str(output_file)
    
    def get_statistics(self) -> Dict:
        """Detaylı istatistikler döndürür"""
        stats = {
            'website': self.website_name,
            'total_journals': self.data['statistics']['total_journals'],
            'total_issues': self.data['statistics']['total_issues'],
            'total_articles': self.data['statistics']['total_articles'],
            'created_at': self.data['created_at'],
            'updated_at': self.data['updated_at'],
            'journals_by_type': {},
            'open_access_journals': 0,
            'issues_per_journal': {},
            'articles_per_journal': {},
            'total_authors': set()
        }
        
        for journal in self.data['journals']:
            journal_type = journal.get('type', 'Unknown')
            stats['journals_by_type'][journal_type] = stats['journals_by_type'].get(journal_type, 0) + 1
            
            if journal.get('open_access'):
                stats['open_access_journals'] += 1
            
            stats['issues_per_journal'][journal['name']] = journal.get('issue_count', 0)
            stats['articles_per_journal'][journal['name']] = journal.get('article_count', 0)
            
            for issue in journal.get('issues', []):
                for article in issue.get('articles', []):
                    for author in article.get('authors', []):
                        stats['total_authors'].add(author)
        
        stats['total_unique_authors'] = len(stats['total_authors'])
        stats['total_authors'] = list(stats['total_authors'])[:50]
        
        return stats
    
    def print_statistics(self):
        """İstatistikleri ekrana yazdırır"""
        stats = self.get_statistics()
        
        logger.header(f"{self.website_name.upper()} İSTATİSTİKLERİ")
        logger.stats({
            'Toplam Journal': stats['total_journals'],
            'Toplam Issue': stats['total_issues'],
            'Toplam Makale': stats['total_articles'],
            'Benzersiz Yazar': stats['total_unique_authors'],
            'Open Access Journal': stats['open_access_journals']
        })
        
        logger.section("Journal Tipleri")
        for j_type, count in stats['journals_by_type'].items():
            logger.info(f"  {j_type}: {count}")
        
        logger.section("Journal Detayları (İlk 10)")
        sorted_journals = sorted(stats['articles_per_journal'].items(), key=lambda x: x[1], reverse=True)[:10]
        for idx, (name, article_count) in enumerate(sorted_journals, 1):
            issue_count = stats['issues_per_journal'].get(name, 0)
            logger.info(f"  {idx}. {name}: {issue_count} issue, {article_count} makale")
        
        logger.info(f"Oluşturulma: {stats['created_at']}")
        logger.info(f"Son Güncelleme: {stats['updated_at']}")
        logger.separator()


def main():
    """Test ve örnek kullanım"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Academic Data Manager - Test')
    parser.add_argument('-w', '--website', required=True, help='Website adı')
    parser.add_argument('-s', '--stats', action='store_true', help='İstatistikleri göster')
    parser.add_argument('-e', '--export', action='store_true', help='Sadece makaleleri dışa aktar')
    parser.add_argument('-m', '--migrate', action='store_true', help='Eski formatı yeni formata dönüştür')
    
    args = parser.parse_args()
    
    manager = AcademicDataManager(website_name=args.website)
    
    if args.migrate:
        logger.success("Veri yüklenirken otomatik olarak migrate edildi (eğer eski formattaysa)")
        manager._save_to_json()
    
    if args.stats:
        manager.print_statistics()
    
    if args.export:
        manager.export_articles_only()


if __name__ == "__main__":
    main()
