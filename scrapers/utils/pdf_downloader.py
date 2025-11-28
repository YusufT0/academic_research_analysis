"""
PDF Downloader Modülü
Akademik makalelerden PDF'leri indirme ve yönetme
"""

import os
import re
import time
import requests
from pathlib import Path
from typing import Optional, List, Dict
import argparse
import json

from .logger import get_logger
logger = get_logger('pdf_downloader')

# SSL uyarılarını sustur
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# PDF Compressor import
try:
    from compress_pdfs import PDFCompressor
except ImportError:
    from .compress_pdfs import PDFCompressor


class ProxyConfig:
    """Proxy yapılandırma sınıfı"""
    
    def __init__(self, proxy_user: str = None, proxy_pass: str = None, 
                 proxy_host: str = None, proxy_port: str = None):
        """
        Proxy yapılandırmasını oluşturur
        
        Args:
            proxy_user: Proxy kullanıcı adı
            proxy_pass: Proxy şifresi
            proxy_host: Proxy host adresi
            proxy_port: Proxy port
        """
        self.proxy_user = proxy_user
        self.proxy_pass = proxy_pass
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
    
    def get_proxy_string(self) -> str:
        """Proxy bağlantı string'ini döndürür"""
        if self.proxy_user and self.proxy_pass:
            return f"http://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}"
        return None
    
    def is_configured(self) -> bool:
        """Proxy yapılandırılmış mı kontrol eder"""
        return bool(self.proxy_user and self.proxy_pass)


class PDFDownloader:
    """PDF dosyalarını indirme ve yönetme sınıfı"""
    
    def __init__(self, website_name: str = "sciencedirect", base_download_dir: str = "./downloads", 
                 compress: bool = False):
        """
        PDF Downloader'ı başlatır
        
        Args:
            website_name: Website adı (alt klasör olarak kullanılır)
            base_download_dir: Ana indirme klasörü
            compress: İndirilen PDF'leri sıkıştır ve orijinalleri sil
        """
        self.website_name = self._sanitize_filename(website_name)
        self.base_download_dir = Path(base_download_dir) / self.website_name
        self.base_download_dir.mkdir(parents=True, exist_ok=True)
        self.compress = compress
        
        logger.success(f"PDF indirme klasörü: {self.base_download_dir.absolute()}")
        if self.compress:
            logger.info("Otomatik sıkıştırma: AÇIK (orijinaller silinecek)")
    
    def _sanitize_filename(self, name: str) -> str:
        """
        Dosya/klasör adını temizler (geçersiz karakterleri kaldırır)
        
        Args:
            name: Temizlenecek isim
            
        Returns:
            str: Temizlenmiş isim
        """
        # Windows için geçersiz karakterleri kaldır
        invalid_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(invalid_chars, '_', name)
        
        # Başta/sonda boşluk ve nokta olmasın
        sanitized = sanitized.strip('. ')
        
        # Çok uzun isimleri kısalt (max 200 karakter)
        if len(sanitized) > 200:
            sanitized = sanitized[:200]
        
        return sanitized
    
    def download_pdfs(self, articles: List[Dict], proxy_config: Optional[ProxyConfig] = None) -> Dict:
        """
        Makale listesinden PDF'leri indirir, journal'lara göre klasörlere yerleştirir
        
        Args:
            articles: Makale detayları listesi (pdf_url, journal_name içermeli)
            proxy_config: Proxy yapılandırması (opsiyonel)
            
        Returns:
            dict: İndirme istatistikleri
        """
        logger.header(f"PDF İNDİRME BAŞLIYOR - {self.website_name.upper()}")
        
        stats = {
            'total': len(articles),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'failed_articles': []
        }
        
        # Proxy ayarları
        session = requests.Session()
        if proxy_config and proxy_config.is_configured():
            proxy_url = proxy_config.get_proxy_string()
            session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            session.verify = False  # SSL doğrulamasını devre dışı bırak
            logger.success(f"Proxy kullanılıyor: {proxy_config.proxy_host}:{proxy_config.proxy_port}")
        
        # User agent ekle
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        for idx, article in enumerate(articles, 1):
            try:
                logger.item(idx, stats['total'], article.get('url', 'Unknown URL'))
                
                # PDF URL kontrolü
                pdf_url = article.get('pdf_url')
                if not pdf_url:
                    logger.warning("PDF URL yok, atlanıyor")
                    stats['skipped'] += 1
                    continue
                
                # Journal ismini al ve temizle
                journal_name = article.get('journal_name', 'Unknown_Journal')
                journal_folder = self.base_download_dir / self._sanitize_filename(journal_name)
                journal_folder.mkdir(parents=True, exist_ok=True)
                
                # PDF dosya adını oluştur (DOI veya URL'den)
                doi = article.get('doi', '')
                if doi:
                    # DOI'dan dosya adı oluştur
                    filename = self._sanitize_filename(doi.replace('https://doi.org/', '').replace('/', '_'))
                else:
                    # URL'den dosya adı oluştur
                    filename = self._sanitize_filename(article.get('url', f'article_{idx}').split('/')[-1])
                
                filename = f"{filename}.pdf"
                filepath = journal_folder / filename
                
                # Dosya zaten var mı kontrol et
                if filepath.exists():
                    logger.info("Dosya zaten mevcut, atlanıyor")
                    stats['skipped'] += 1
                    continue
                
                # PDF'i indir
                logger.step(f"İndiriliyor: {filename}")
                
                # Full URL oluştur
                if pdf_url.startswith('/'):
                    # Website'e göre base URL ekle
                    if 'sciencedirect' in self.website_name.lower():
                        pdf_url = f"https://www.sciencedirect.com{pdf_url}"
                    elif 'ieee' in self.website_name.lower():
                        pdf_url = f"https://ieeexplore.ieee.org{pdf_url}"
                    elif 'arxiv' in self.website_name.lower():
                        pdf_url = f"https://arxiv.org{pdf_url}"
                    else:
                        logger.warning("Bilinmeyen website, relative URL işlenemiyor")
                        stats['failed'] += 1
                        continue
                
                response = session.get(pdf_url, timeout=60, stream=True)
                response.raise_for_status()
                
                # Dosyayı kaydet
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                file_size = filepath.stat().st_size / (1024 * 1024)  # MB
                logger.success(f"İndirildi: {file_size:.2f} MB")
                stats['successful'] += 1
                
                # Rate limiting
                time.sleep(1)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"İndirme hatası: {e}")
                stats['failed'] += 1
                stats['failed_articles'].append({
                    'url': article.get('url'),
                    'pdf_url': pdf_url,
                    'error': str(e)
                })
            except Exception as e:
                logger.error(f"Beklenmeyen hata: {e}")
                stats['failed'] += 1
                stats['failed_articles'].append({
                    'url': article.get('url'),
                    'pdf_url': pdf_url,
                    'error': str(e)
                })
        
        # Özet rapor
        logger.done("PDF İNDİRME ÖZETİ")
        logger.stats({
            'Website': self.website_name,
            'Toplam Makale': stats['total'],
            'Başarılı': stats['successful'],
            'Atlanan': stats['skipped'],
            'Başarısız': stats['failed']
        })
        
        if stats['failed_articles']:
            logger.section("Başarısız İndirmeler")
            for failed in stats['failed_articles']:
                logger.error(f"  - {failed['url']}")
                logger.info(f"    Hata: {failed['error']}")
        
# Otomatik sıkıştırma
        if self.compress and stats['successful'] > 0:
            logger.header("OTOMATIK SIKIŞTIRMA BAŞLIYOR")
            
            compressor = PDFCompressor(output_suffix="")  # Suffix yok, orijinali değiştireceğiz
            
            # İndirilen PDF'lerin bulunduğu klasörü sıkıştır
            compress_result = compressor.compress_directory(
                directory=str(self.base_download_dir),
                recursive=True,
                replace_original=True,
                quality=95
            )
            
            stats['compression'] = compress_result
        
        return stats
    
    def download_from_json(self, json_file: str, proxy_config: Optional[ProxyConfig] = None) -> Dict:
        """
        JSON dosyasından makale listesini okuyup PDF'leri indirir
        
        Args:
            json_file: Makale listesi JSON dosyası
            proxy_config: Proxy yapılandırması
            
        Returns:
            dict: İndirme istatistikleri
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            
            if not isinstance(articles, list):
                logger.error("JSON dosyası liste formatında olmalı")
                return {'success': False}
            
            return self.download_pdfs(articles, proxy_config)
            
        except FileNotFoundError:
            logger.error(f"JSON dosyası bulunamadı: {json_file}")
            return {'success': False}
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse hatası: {e}")
            return {'success': False}


def main():
    """Ana fonksiyon - CLI kullanımı"""
    parser = argparse.ArgumentParser(
        description='Akademik makalelerden PDF indir',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  # JSON dosyasından indir (ScienceDirect)
  python pdf_downloader.py -j articles.json -w sciencedirect
  
  # IEEE makaleleri için
  python pdf_downloader.py -j ieee_articles.json -w ieee
  
  # Otomatik sıkıştırma ile (orijinaller silinir)
  python pdf_downloader.py -j articles.json -w sciencedirect --compress
  
  # Proxy ile
  python pdf_downloader.py -j articles.json -w sciencedirect --proxy-user USER --proxy-pass PASS
  
  # Özel indirme klasörü
  python pdf_downloader.py -j articles.json -w sciencedirect -d ./my_pdfs
        """
    )
    
    parser.add_argument('-j', '--json', required=True,
                       help='Makale listesi JSON dosyası')
    parser.add_argument('-w', '--website', default='sciencedirect',
                       help='Website adı (klasör adı için, varsayılan: sciencedirect)')
    parser.add_argument('-d', '--directory', default='./downloads',
                       help='Ana indirme klasörü (varsayılan: ./downloads)')
    parser.add_argument('--compress', action='store_true',
                       help='İndirilen PDF\'leri otomatik sıkıştır ve orijinalleri sil')
    parser.add_argument('--proxy-user', help='Proxy kullanıcı adı')
    parser.add_argument('--proxy-pass', help='Proxy şifresi')
    parser.add_argument('--proxy-host', default='proxy.gazi.edu.tr',
                       help='Proxy host (varsayılan: proxy.gazi.edu.tr)')
    parser.add_argument('--proxy-port', default='8080',
                       help='Proxy port (varsayılan: 8080)')
    
    args = parser.parse_args()
    
    # Proxy yapılandırması
    proxy_config = None
    if args.proxy_user and args.proxy_pass:
        proxy_config = ProxyConfig(
            proxy_user=args.proxy_user,
            proxy_pass=args.proxy_pass,
            proxy_host=args.proxy_host,
            proxy_port=args.proxy_port
        )
        logger.success(f"Proxy yapılandırıldı: {args.proxy_host}:{args.proxy_port}")
    
    # Downloader oluştur
    downloader = PDFDownloader(
        website_name=args.website,
        base_download_dir=args.directory,
        compress=args.compress
    )
    
    # İndir
    result = downloader.download_from_json(args.json, proxy_config)
    
    if result.get('success', True):
        logger.done("İşlem tamamlandı!")
    else:
        logger.error("İşlem başarısız!")
        exit(1)


if __name__ == "__main__":
    main()
