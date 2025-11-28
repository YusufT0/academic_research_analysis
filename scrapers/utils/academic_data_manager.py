"""
Academic Data Manager
Farklı journal kaynaklarından toplanan verileri standart JSON formatında yönetir
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class AcademicDataManager:
    """
    Akademik makale verilerini standart JSON formatında yönetir
    Her website için ayrı JSON dosyası oluşturur ve journal/makale verilerini kaydeder
    """
    
    def __init__(self, website_name: str, output_dir: str = "./data"):
        """
        Academic Data Manager'ı başlatır
        
        Args:
            website_name: Website adı (sciencedirect, ieee, arxiv, etc.)
            output_dir: JSON dosyalarının kaydedileceği klasör
        """
        self.website_name = website_name.lower()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON dosya yolu
        self.json_file = self.output_dir / f"{self.website_name}_articles.json"
        
        # Veri yapısı
        self.data = {
            'website': self.website_name,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'total_journals': 0,
            'total_articles': 0,
            'journals': []
        }
        
        # Eğer dosya varsa yükle
        if self.json_file.exists():
            self._load_existing_data()
        
        print(f"✓ Academic Data Manager başlatıldı: {self.website_name}")
        print(f"✓ JSON dosyası: {self.json_file.absolute()}")
    
    def _load_existing_data(self):
        """Mevcut JSON dosyasını yükler"""
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                self.data = existing_data
                print(f"✓ Mevcut veri yüklendi: {self.data['total_journals']} journal, {self.data['total_articles']} makale")
        except Exception as e:
            print(f"⚠ Mevcut veri yüklenemedi, yeni dosya oluşturulacak: {e}")
    
    def add_journal_with_articles(self, journal_info: Dict, articles: List[Dict]) -> bool:
        """
        Bir journal'ı ve makalelerini ekler veya günceller
        
        Args:
            journal_info: Journal bilgileri (name, url, type, open_access, etc.)
            articles: Makale listesi
            
        Returns:
            bool: Başarılı ise True
        """
        try:
            # Journal adı zorunlu
            if not journal_info.get('name'):
                print("⚠ Journal adı bulunamadı, atlanıyor")
                return False
            
            journal_name = journal_info['name']
            
            # Journal zaten var mı kontrol et
            existing_journal = None
            for idx, j in enumerate(self.data['journals']):
                if j['name'] == journal_name:
                    existing_journal = idx
                    break
            
            # Journal verisi oluştur
            journal_data = {
                'name': journal_info.get('name'),
                'url': journal_info.get('url'),
                'type': journal_info.get('type', 'Unknown'),
                'open_access': journal_info.get('open_access', False),
                'letter_group': journal_info.get('letter_group'),
                'issn': journal_info.get('issn'),
                'publisher': journal_info.get('publisher'),
                'description': journal_info.get('description'),
                'added_at': datetime.now().isoformat(),
                'article_count': len(articles),
                'articles': []
            }
            
            # Makaleleri ekle
            for article in articles:
                article_data = self._create_article_data(article)
                journal_data['articles'].append(article_data)
            
            # Journal'ı ekle veya güncelle
            if existing_journal is not None:
                # Güncelle
                print(f"  ℹ Journal güncelleniyor: {journal_name}")
                self.data['journals'][existing_journal] = journal_data
            else:
                # Yeni ekle
                print(f"  ✓ Journal ekleniyor: {journal_name}")
                self.data['journals'].append(journal_data)
                self.data['total_journals'] += 1
            
            # Toplam makale sayısını güncelle
            self._update_statistics()
            
            # JSON'a kaydet
            self._save_to_json()
            
            print(f"  ✓ {journal_name}: {len(articles)} makale kaydedildi")
            return True
            
        except Exception as e:
            print(f"  ✗ Journal ekleme hatası: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_article_data(self, article: Dict) -> Dict:
        """
        Makale verisini standart formata dönüştürür
        
        Args:
            article: Makale bilgileri
            
        Returns:
            dict: Standart formatlı makale verisi
        """
        # Temel makale yapısı (tüm website'ler için ortak)
        article_data = {
            'title': article.get('title'),
            'url': article.get('url'),
            'pdf_url': article.get('pdf_url'),
            'doi': article.get('doi'),
            'authors': article.get('authors', []),
            'abstract': article.get('abstract'),
            'introduction': article.get('introduction'),  # content yerine introduction
            'keywords': article.get('keywords', []),
            'publication_date': article.get('publication_date'),
            'pages': article.get('pages'),
            'publisher': article.get('publisher'),
            'citation_count': article.get('citation_count', 0),
            'references': article.get('references', []),
            'added_at': datetime.now().isoformat()
        }
        
        # Website'e özgü ekstra alanlar
        if self.website_name == 'sciencedirect':
            article_data['journal_name'] = article.get('journal_name')
            article_data['journal_url'] = article.get('journal_url')
        elif self.website_name == 'arxiv':
            article_data['arxiv_id'] = article.get('arxiv_id')
            article_data['categories'] = article.get('categories', [])
            article_data['version'] = article.get('version')
        
        return article_data
    
    def _update_statistics(self):
        """İstatistikleri günceller"""
        self.data['total_journals'] = len(self.data['journals'])
        self.data['total_articles'] = sum(j['article_count'] for j in self.data['journals'])
        self.data['updated_at'] = datetime.now().isoformat()
    
    def _save_to_json(self):
        """Veriyi JSON dosyasına kaydeder"""
        try:
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            print(f"  💾 JSON kaydedildi: {self.json_file.name}")
        except Exception as e:
            print(f"  ✗ JSON kaydetme hatası: {e}")
    
    def add_batch_journals(self, journals_with_articles: List[Dict]) -> Dict:
        """
        Birden fazla journal'ı toplu olarak ekler
        
        Args:
            journals_with_articles: Journal ve makale listesi
                Format: [{'journal_info': {...}, 'articles': [...]}, ...]
        
        Returns:
            dict: İstatistikler
        """
        print("\n" + "=" * 80)
        print(f"📊 TOPLU JOURNAL KAYDETME - {self.website_name.upper()}")
        print("=" * 80)
        
        stats = {
            'total': len(journals_with_articles),
            'successful': 0,
            'failed': 0,
            'total_articles': 0
        }
        
        for idx, item in enumerate(journals_with_articles, 1):
            journal_info = item.get('journal_info', {})
            articles = item.get('articles', [])
            
            print(f"\n[{idx}/{stats['total']}] {journal_info.get('name', 'Unknown')}")
            
            if self.add_journal_with_articles(journal_info, articles):
                stats['successful'] += 1
                stats['total_articles'] += len(articles)
            else:
                stats['failed'] += 1
        
        print("\n" + "=" * 80)
        print("📊 KAYDETME ÖZETİ")
        print("=" * 80)
        print(f"Website: {self.website_name}")
        print(f"Toplam Journal: {stats['total']}")
        print(f"✅ Başarılı: {stats['successful']}")
        print(f"❌ Başarısız: {stats['failed']}")
        print(f"📄 Toplam Makale: {stats['total_articles']}")
        print(f"💾 JSON Dosyası: {self.json_file.name}")
        print("=" * 80)
        
        return stats
    
    def get_journal(self, journal_name: str) -> Optional[Dict]:
        """
        Belirli bir journal'ın verilerini getirir
        
        Args:
            journal_name: Journal adı
            
        Returns:
            dict: Journal verisi veya None
        """
        for journal in self.data['journals']:
            if journal['name'] == journal_name:
                return journal
        return None
    
    def get_all_articles(self) -> List[Dict]:
        """
        Tüm makaleleri düz bir liste olarak döndürür
        
        Returns:
            list: Tüm makaleler
        """
        all_articles = []
        for journal in self.data['journals']:
            for article in journal['articles']:
                # Journal bilgisini de ekle
                article_copy = article.copy()
                article_copy['journal_name'] = journal['name']
                article_copy['journal_url'] = journal['url']
                all_articles.append(article_copy)
        return all_articles
    
    def export_articles_only(self, output_file: Optional[str] = None) -> str:
        """
        Sadece makaleleri içeren ayrı bir JSON dosyası oluşturur (PDF downloader için)
        
        Args:
            output_file: Çıkış dosyası yolu (None ise otomatik oluşturulur)
            
        Returns:
            str: Oluşturulan dosya yolu
        """
        if output_file is None:
            output_file = self.output_dir / f"{self.website_name}_articles_only.json"
        else:
            output_file = Path(output_file)
        
        articles = self.get_all_articles()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        
        print(f"✓ Sadece makaleler dışa aktarıldı: {output_file}")
        print(f"  Toplam {len(articles)} makale")
        
        return str(output_file)
    
    def get_statistics(self) -> Dict:
        """
        Detaylı istatistikler döndürür
        
        Returns:
            dict: İstatistikler
        """
        stats = {
            'website': self.website_name,
            'total_journals': self.data['total_journals'],
            'total_articles': self.data['total_articles'],
            'created_at': self.data['created_at'],
            'updated_at': self.data['updated_at'],
            'journals_by_type': {},
            'open_access_journals': 0,
            'articles_per_journal': {},
            'total_authors': set()
        }
        
        for journal in self.data['journals']:
            # Tiplere göre
            journal_type = journal.get('type', 'Unknown')
            stats['journals_by_type'][journal_type] = stats['journals_by_type'].get(journal_type, 0) + 1
            
            # Open access
            if journal.get('open_access'):
                stats['open_access_journals'] += 1
            
            # Makale sayıları
            stats['articles_per_journal'][journal['name']] = journal['article_count']
            
            # Yazarlar
            for article in journal['articles']:
                for author in article.get('authors', []):
                    stats['total_authors'].add(author)
        
        stats['total_unique_authors'] = len(stats['total_authors'])
        stats['total_authors'] = list(stats['total_authors'])[:50]  # İlk 50 yazar
        
        return stats
    
    def print_statistics(self):
        """İstatistikleri ekrana yazdırır"""
        stats = self.get_statistics()
        
        print("\n" + "=" * 80)
        print(f"📊 {self.website_name.upper()} İSTATİSTİKLERİ")
        print("=" * 80)
        print(f"Toplam Journal: {stats['total_journals']}")
        print(f"Toplam Makale: {stats['total_articles']}")
        print(f"Benzersiz Yazar: {stats['total_unique_authors']}")
        print(f"Open Access Journal: {stats['open_access_journals']}")
        
        print(f"\nJournal Tipleri:")
        for j_type, count in stats['journals_by_type'].items():
            print(f"  - {j_type}: {count}")
        
        print(f"\nEn Çok Makaleye Sahip Journal'lar (İlk 10):")
        sorted_journals = sorted(stats['articles_per_journal'].items(), key=lambda x: x[1], reverse=True)[:10]
        for idx, (name, count) in enumerate(sorted_journals, 1):
            print(f"  {idx}. {name}: {count} makale")
        
        print(f"\nOluşturulma: {stats['created_at']}")
        print(f"Son Güncelleme: {stats['updated_at']}")
        print("=" * 80)


def main():
    """Test ve örnek kullanım"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Academic Data Manager - Test')
    parser.add_argument('-w', '--website', required=True, help='Website adı')
    parser.add_argument('-s', '--stats', action='store_true', help='İstatistikleri göster')
    parser.add_argument('-e', '--export', action='store_true', help='Sadece makaleleri dışa aktar')
    
    args = parser.parse_args()
    
    manager = AcademicDataManager(website_name=args.website)
    
    if args.stats:
        manager.print_statistics()
    
    if args.export:
        manager.export_articles_only()


if __name__ == "__main__":
    main()
