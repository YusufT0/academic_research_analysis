"""
HTML parsing functions for IEEE Xplore scraper
"""

import re
import sys
from typing import Optional, List, Dict
from bs4 import BeautifulSoup

sys.path.insert(0, str(__file__).rsplit('ieee_xplore', 1)[0])
from utils.logger import get_logger
logger = get_logger('ieee_xplore')


class JournalParser:
    """Journal bilgilerini parse eden sınıf"""

    @staticmethod
    def extract_journal_name_from_journal_page(page_source: str) -> Optional[str]:
        """
        IEEE journal sayfasından dergi adını çıkarır.

        Hedef yapı:
        <div class="title-container ..."><h1>...</h1></div>
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')

            title_container = soup.find('div', class_=lambda c: c and 'title-container' in c)
            if title_container:
                h1 = title_container.find('h1')
                if h1:
                    journal_name = h1.get_text(strip=True)
                    if journal_name:
                        return journal_name

            # Fallback: genel h1 başlığı
            h1 = soup.find('h1')
            if h1:
                journal_name = h1.get_text(strip=True)
                return journal_name or None

            return None
        except Exception as e:
            logger.warning(f"Journal adı çıkarma hatası: {e}")
            return None

    @staticmethod
    def extract_aims_and_scope(page_source: str) -> Optional[str]:
        """
        Journal ana sayfasındaki <section class="aimsAndScope"> bileşeninden
        Aims & Scope metnini çıkarır.

        Args:
            page_source: Sayfa HTML içeriği

        Returns:
            str: Aims & scope düz metin veya None
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            section = soup.find('section', class_='aimsAndScope')
            if not section:
                return None
            # col-21-24 sütununu bul (varsa), yoksa section'ın kendisini kullan
            content_col = section.find('div', class_='col-21-24')
            if not content_col:
                content_col = section
            # h2 başlığını çıkar
            h2 = content_col.find('h2')
            if h2:
                h2.decompose()
            text = content_col.get_text(separator=' ', strip=True)
            return text if text else None
        except Exception as e:
            logger.warning(f"Aims & scope çıkarma hatası: {e}")
            return None

    @staticmethod
    def extract_all_issues_tab_url(page_source: str) -> Optional[str]:
        """
        Navigasyon çubuğundan 'All Issues' tab linkini çıkarır.

        Args:
            page_source: Sayfa HTML içeriği

        Returns:
            str: All Issues sayfasının relative URL'i veya None
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            # stats-jhp-AllIssues class'ına sahip link
            link = soup.find('a', class_='stats-jhp-AllIssues')
            if link and link.get('href'):
                return link['href']
            # Fallback: title="All Issues" olan link
            link = soup.find('a', title='All Issues')
            if link and link.get('href'):
                return link['href']
            # All Volumes butonu (bazı journal'larda All Issues yerine kullanılır)
            link = soup.find('a', class_='stats-jhp-AllVolumes')
            if link and link.get('href'):
                logger.info("All Volumes linki bulundu, All Issues yerine kullanılacak")
                return link['href']
            link = soup.find('a', title='All Volumes')
            if link and link.get('href'):
                logger.info("All Volumes linki bulundu (title), All Issues yerine kullanılacak")
                return link['href']
            # Fallback: metin içinde 'All Volumes' geçen link
            for a in soup.find_all('a', href=True):
                if a.get_text(strip=True) == 'All Volumes':
                    logger.info("All Volumes linki bulundu (text), All Issues yerine kullanılacak")
                    return a['href']
            return None
        except Exception as e:
            logger.warning(f"All Issues/Volumes linki çıkarma hatası: {e}")
            return None

    @staticmethod
    def extract_journals_from_page(page_source: str) -> list:
        """
        Sayfa HTML'inden journal bilgilerini çıkarır
        
        Args:
            page_source: Sayfanın HTML içeriği
            
        Returns:
            list: Journal bilgilerinin listesi
        """
        try:
            logger.info("Sayfa taranıyor...")
            
            # BeautifulSoup ile parse et
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Ana results container'ı bul
            results_div = soup.find('div', class_='ng-SearchResults')
            if not results_div:
                logger.error("ng-SearchResults div'i bulunamadı")
                return []
            
            # xpl-browse-results-list içindeki tüm journal item'larını bul
            browse_results = results_div.find('xpl-browse-results-list')
            if not browse_results:
                logger.error("xpl-browse-results-list bulunamadı")
                return []
            
            # Tüm journal item'larını bul (xpl-browse-results-item)
            journal_items = browse_results.find_all('xpl-browse-results-item')
            logger.found(len(journal_items), "journal")
            
            journals = []
            
            for idx, item in enumerate(journal_items, 1):
                try:
                    # Journal başlığını al (h2 içindeki link)
                    h2_title = item.find('h2')
                    if not h2_title:
                        continue
                    
                    title_link = h2_title.find('a')
                    if not title_link:
                        continue
                    
                    journal_name = title_link.get_text(strip=True)
                    journal_url = title_link.get('href', '')
                    
                    # Meta bilgileri al (Publisher, Years)
                    meta_list = item.find('ul', class_='result-meta')
                    publisher = 'Unknown'
                    years = 'Unknown'
                    most_recent_issue_url = None
                    
                    if meta_list:
                        list_items = meta_list.find_all('li')
                        
                        for li in list_items:
                            text = li.get_text(strip=True)
                            
                            # Publisher bilgisi
                            if 'Publisher:' in text:
                                publisher = text.replace('Publisher:', '').strip()
                            
                            # Years bilgisi
                            elif 'Years:' in text:
                                years = text.replace('Years:', '').strip()
                            
                            # Most Recent Issue linki
                            elif 'Most Recent Issue' in text:
                                issue_link = li.find('a')
                                if issue_link:
                                    most_recent_issue_url = issue_link.get('href', '')
                    
                    # Journal bilgisini sakla
                    journal_info = {
                        'name': journal_name,
                        'url': journal_url,
                        'publisher': publisher,
                        'years': years,
                        'most_recent_issue_url': most_recent_issue_url
                    }
                    
                    journals.append(journal_info)
                    
                    # İlerleme göster
                    if most_recent_issue_url:
                        logger.item(idx, len(journal_items), journal_name)
                        logger.info(f"  Publisher: {publisher}, Years: {years}")
                        logger.info(f"  Most Recent Issue: {most_recent_issue_url}")
                    else:
                        logger.item(idx, len(journal_items), f"{journal_name} (Most Recent Issue linki yok)")
                    
                except Exception as e:
                    logger.warning(f"Journal {idx} parse hatası: {e}")
                    continue
            
            logger.found(len(journals), "journal (toplam)")
            return journals
            
        except Exception as e:
            logger.failed("Journal çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return []


class ArticleParser:
    """Makale bilgilerini parse eden sınıf"""
    
    # Ay adı -> numara eşleştirmesi
    MONTH_MAP = {
        'january': '01', 'jan': '01', 'jan.': '01',
        'february': '02', 'feb': '02', 'feb.': '02',
        'march': '03', 'mar': '03', 'mar.': '03',
        'april': '04', 'apr': '04', 'apr.': '04',
        'may': '05',
        'june': '06', 'jun': '06', 'jun.': '06',
        'july': '07', 'jul': '07', 'jul.': '07',
        'august': '08', 'aug': '08', 'aug.': '08',
        'september': '09', 'sept': '09', 'sept.': '09', 'sep': '09', 'sep.': '09',
        'october': '10', 'oct': '10', 'oct.': '10', 'oct-': '10',
        'november': '11', 'nov': '11', 'nov.': '11',
        'december': '12', 'dec': '12', 'dec.': '12'
    }
    
    @staticmethod
    def _parse_ieee_date(date_text: str) -> str:
        """
        IEEE tarih formatını ISO formatına çevirir.
        
        Desteklenen formatlar:
        - "21 November 2025" -> "2025-11-21"
        - "08 April 2025" -> "2025-04-08"
        - "Oct.-2025" -> "2025-10"
        - "December-2025" -> "2025-12"
        - "2025" -> "2025"
        
        Args:
            date_text: Ham tarih metni
            
        Returns:
            str: ISO formatında tarih veya orijinal metin
        """
        if not date_text:
            return None
        
        date_text = date_text.strip()
        
        # Pattern 1: "21 November 2025" veya "08 April 2025"
        match = re.match(r'^(\d{1,2})\s+(\w+)\s+(\d{4})$', date_text)
        if match:
            day = match.group(1).zfill(2)
            month_name = match.group(2).lower()
            year = match.group(3)
            
            month = ArticleParser.MONTH_MAP.get(month_name)
            if month:
                return f"{year}-{month}-{day}"
        
        # Pattern 2: "Oct.-2025" veya "October-2025" veya "December-2025"
        match = re.match(r'^(\w+\.?)-(\d{4})$', date_text)
        if match:
            month_name = match.group(1).lower().rstrip('.')
            year = match.group(2)
            
            month = ArticleParser.MONTH_MAP.get(month_name)
            if month:
                return f"{year}-{month}"
        
        # Pattern 3: Sadece yıl "2025"
        match = re.match(r'^(\d{4})$', date_text)
        if match:
            return match.group(1)
        
        # Hiçbir pattern uymadıysa orijinal metni döndür
        return date_text
    
    @staticmethod
    def extract_issue_info(page_source: str) -> dict:
        """
        Issue sayfasından issue_number ve date bilgisini çıkarır.
        
        Desteklenen HTML formatları:
        <div class="u-m-1 u-mt-1 u-mr-1 text-base-md"><p><b>Issue 5 • Oct.-2025</b></p></div>
        <div class="u-m-1 u-mt-1 u-mr-1 text-base-md"><p><b>Volume 13: 2025</b></p></div>
        <div class="u-m-1 u-mt-1 u-mr-1 text-base-md"><p><b>Issue 6 • December-2025</b></p></div>
        
        Args:
            page_source: Sayfa HTML içeriği
            
        Returns:
            dict: {'issue_number': str, 'date': str} veya None
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # u-m-1 u-mt-1 u-mr-1 text-base-md sınıflı div'i bul
            issue_div = soup.find('div', class_='text-base-md')
            
            if not issue_div:
                # Alternatif selector
                issue_div = soup.find('div', class_=lambda c: c and 'u-m-1' in c and 'text-base-md' in c)
            
            if not issue_div:
                logger.warning("Issue info div'i bulunamadı")
                return None
            
            # b tag içindeki metni al
            b_tag = issue_div.find('b')
            if not b_tag:
                # p tag içinde doğrudan metin olabilir
                p_tag = issue_div.find('p')
                if p_tag:
                    text = p_tag.get_text(strip=True)
                else:
                    text = issue_div.get_text(strip=True)
            else:
                text = b_tag.get_text(strip=True)
            
            if not text:
                logger.warning("Issue info metni boş")
                return None
            
            logger.info(f"Issue info raw: {text}")
            
            issue_number = None
            date = None
            
            # Pattern 1: "Issue 5 • Oct.-2025" veya "Issue 6 • December-2025"
            # • karakteri farklı unicode olabilir (bullet, middle dot)
            match = re.match(r'^(Issue\s+\d+)\s*[•·]\s*(.+)$', text)
            if match:
                issue_number = match.group(1).strip()  # "Issue 5"
                date_part = match.group(2).strip()     # "Oct.-2025"
                date = ArticleParser._parse_ieee_date(date_part)
            
            # Pattern 2: "Volume 13: 2025"
            if not issue_number:
                match = re.match(r'^(Volume\s+\d+)\s*:\s*(\d{4})$', text)
                if match:
                    issue_number = match.group(1).strip()  # "Volume 13"
                    date = match.group(2)                   # "2025"
            
            # Pattern 3: Sadece "Volume X" (tarihsiz)
            if not issue_number:
                match = re.match(r'^(Volume\s+\d+)$', text)
                if match:
                    issue_number = match.group(1).strip()
                    date = None
            
            # Pattern 4: Sadece "Issue X" (tarihsiz)
            if not issue_number:
                match = re.match(r'^(Issue\s+\d+)$', text)
                if match:
                    issue_number = match.group(1).strip()
                    date = None
            
            # Hiçbir pattern uymadıysa tüm metni issue_number olarak al
            if not issue_number:
                issue_number = text
            
            result = {
                'issue_number': issue_number,
                'date': date
            }
            
            logger.success(f"Issue Info: issue_number='{issue_number}', date='{date}'")
            return result
            
        except Exception as e:
            logger.failed("Issue info çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def extract_article_urls(page_source: str) -> list:
        """
        Most Recent Issue sayfasındaki makale URL'lerini çıkarır
        
        Args:
            page_source: Sayfa HTML içeriği
            
        Returns:
            list: Makale URL'lerinin listesi
        """
        try:
            # BeautifulSoup ile parse et
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Tüm xpl-issue-results-items elementlerini bul
            result_items = soup.find_all('xpl-issue-results-items')
            
            if not result_items:
                # Fallback: bazı TOC varyantlarında custom element yerine doğrudan /document/ linkleri bulunur
                article_links = soup.select('a[href*="/document/"]')
                if not article_links:
                    logger.warning("Makale item'ları bulunamadı")
                    return []

                dedup = set()
                articles = []
                for link in article_links:
                    href = link.get('href', '').strip()
                    if not href or '/document/' not in href:
                        continue
                    if href in dedup:
                        continue
                    dedup.add(href)
                    title_text = link.get_text(strip=True)
                    if not title_text:
                        continue
                    articles.append({'url': href, 'title': title_text})

                logger.found(len(articles), "makale URL'i (fallback)")
                return articles
            
            logger.found(len(result_items), "item")
            
            articles = []

            for idx, item in enumerate(result_items, 1):
                try:
                    # h2 içindeki article linkini bul
                    h2_title = item.find('h2', class_='text-md-md-lh')
                    if not h2_title:
                        # Mobile için alternatif selector
                        h2_title = item.find('h2', class_='result-item-title')

                    if not h2_title:
                        # Başlık bulunamadı, muhtemelen "Table of Contents" gibi link olmayan item
                        continue

                    # h2 içindeki a tag'ini bul
                    article_link = h2_title.find('a', href=True)

                    if article_link and article_link.get('href'):
                        article_url = article_link['href']

                        # /document/ ile başlayan linkler makale linkleridir
                        if '/document/' in article_url:
                            title_text = article_link.get_text(strip=True)
                            articles.append({'url': article_url, 'title': title_text})
                            logger.info(f"  {len(articles)}. {title_text[:60]}")

                except Exception as e:
                    continue

            logger.found(len(articles), "makale URL'i")
            return articles
            
        except Exception as e:
            logger.failed("Makale URL çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def extract_article_details(page_source: str, article_url: str) -> dict:
        """
        Makale sayfasından detaylı bilgileri çıkarır
        
        Args:
            page_source: Makale sayfasının HTML içeriği
            article_url: Makale URL'i
            
        Returns:
            dict: Makale detayları
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            
            article_details = {
                'url': article_url,
                'title': None,
                'pdf_url': None,
                'authors': [],
                'doi': None,
                'publication_date': None,
                'pages': None,
                'publisher': None,
                'abstract': None,
                'introduction': None
            }
            
            # 1. Başlık al
            logger.info("Başlık alınıyor...")
            title_h1 = soup.find('h1', class_='document-title')
            if title_h1:
                title_span = title_h1.find('span')
                if title_span:
                    article_details['title'] = title_span.get_text(strip=True)
                    logger.success(f"Başlık: {article_details['title'][:50]}...")
            
            # 2. PDF URL'ini al
            logger.info("PDF linki aranıyor...")
            pdf_link = soup.find('a', class_='xpl-btn-pdf')
            if pdf_link and pdf_link.get('href'):
                article_details['pdf_url'] = pdf_link['href']
                logger.success("PDF URL bulundu")
            else:
                logger.warning("PDF linki bulunamadı")
            
            # 3. Yazarları al
            logger.info("Yazarlar alınıyor...")
            authors_container = soup.find('div', class_='authors-container')
            if authors_container:
                author_spans = authors_container.find_all('span', class_='authors-info')
                for author_span in author_spans:
                    author_link = author_span.find('a')
                    if author_link:
                        author_name_span = author_link.find('span')
                        if author_name_span:
                            author_name = author_name_span.get_text(strip=True)
                            article_details['authors'].append(author_name)
                
                logger.found(len(article_details['authors']), "yazar")
            else:
                logger.warning("Yazar bilgisi bulunamadı")
            
            # 4. DOI, Publication Date, Pages, Publisher al
            logger.info("Makale meta bilgileri alınıyor...")
            
            # DOI
            doi_div = soup.find('div', {'data-analytics_identifier': 'document_abstract_doi'})
            if doi_div:
                doi_link = doi_div.find('a')
                if doi_link:
                    article_details['doi'] = doi_link.get_text(strip=True)
            
            # Pages
            pages_strong = soup.find('strong', string=lambda x: x and 'Page(s):' in x)
            if pages_strong and pages_strong.parent:
                pages_text = pages_strong.parent.get_text(strip=True)
                pages = pages_text.replace('Page(s):', '').strip()
                article_details['pages'] = pages
            
            # Publication Date
            pubdate_div = soup.find('div', class_='doc-abstract-pubdate')
            if pubdate_div:
                pubdate_text = pubdate_div.get_text(strip=True)
                pubdate = pubdate_text.replace('Date of Publication:', '').strip()
                # "08 April 2025" gibi metin içinde tarih varsa al
                if pubdate:
                    # Sadece tarihi al (Help linkini çıkar)
                    raw_date = pubdate.split('Help')[0].strip() if 'Help' in pubdate else pubdate
                    # ISO formatına çevir
                    article_details['publication_date'] = ArticleParser._parse_ieee_date(raw_date)
            
            # Publisher
            publisher_span = soup.find('xpl-publisher')
            if publisher_span:
                publisher_text = publisher_span.get_text(strip=True)
                publisher = publisher_text.replace('Publisher:', '').strip()
                article_details['publisher'] = publisher
            
            logger.success(f"Meta bilgiler: DOI={bool(article_details['doi'])}, Date={bool(article_details['publication_date'])}, Pages={bool(article_details['pages'])}")
            
            # 5. Abstract al
            logger.info("Abstract alınıyor...")
            abstract_div = soup.find('div', class_='abstract-text')
            if abstract_div:
                # h2 başlığını kaldır
                for h2 in abstract_div.find_all('h2'):
                    h2.decompose()
                
                abstract_content_div = abstract_div.find('div', {'xplmathjax': ''})
                if abstract_content_div:
                    article_details['abstract'] = abstract_content_div.get_text(strip=True)
                    logger.success(f"Abstract alındı ({len(article_details['abstract'])} karakter)")
                else:
                    logger.warning("Abstract içeriği bulunamadı")
            else:
                logger.warning("Abstract div'i bulunamadı")
            
            # 6. Introduction (Section I) al
            logger.info("Introduction alınıyor...")
            section_divs = soup.find_all('div', class_='section')
            for section in section_divs:
                section_id = section.get('id', '')
                
                # "sec1" veya "Introduction" içeren section'ı bul
                if 'sec1' in section_id.lower() or section.find('h2', string=lambda x: x and 'Introduction' in x):
                    # Section başlığını ve içeriğini al
                    section_text = section.get_text(separator='\n', strip=True)
                    article_details['introduction'] = section_text
                    logger.success(f"Introduction alındı ({len(article_details['introduction'])} karakter)")
                    break
            
            if not article_details['introduction']:
                logger.warning("Introduction bulunamadı")

            return article_details

        except Exception as e:
            logger.failed("Makale detay çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return None


class IssuesPageParser:
    """All Issues sayfasını parse eden sınıf"""

    @staticmethod
    def has_decade_tabs(page_source: str) -> bool:
        """
        Sayfada onlık (2020s, 2010s …) sekmeleri var mı kontrol eder.

        Returns:
            bool: Decade sekmeleri mevcutsa True
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        for div in soup.find_all('div', class_='issue-details-past-tabs'):
            if 'year' not in (div.get('class') or []):
                return True
        return False

    @staticmethod
    def extract_decade_tab_texts(page_source: str) -> List[str]:
        """
        Decade sekme metinlerini sırayla döndürür: ['2020s', '2010s', ...].
        En üstteki (aktif) sekme ilk sıradadır.

        Returns:
            list[str]: Decade metinleri
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        for div in soup.find_all('div', class_='issue-details-past-tabs'):
            if 'year' not in (div.get('class') or []):
                texts = []
                for li in div.find_all('li'):
                    text = li.get_text(strip=True)
                    if text:
                        texts.append(text)
                return texts
        return []

    @staticmethod
    def extract_year_items(page_source: str) -> List[Dict]:
        """
        Yıl listesini döndürür.

        Yılda tek issue varsa <a href="..."> doğrudan issue linki içerir.
        Birden fazla issue varsa <a> href'siz olup tıklanarak genişletilir.

        Returns:
            list[dict]: [{'year': str, 'href': str|None}, ...]
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        year_div = None
        for div in soup.find_all('div', class_='issue-details-past-tabs'):
            if 'year' in (div.get('class') or []):
                year_div = div
                break
        if not year_div:
            return []

        items = []
        for li in year_div.find_all('li'):
            a = li.find('a')
            if a:
                year_text = a.get_text(strip=True)
                href = a.get('href')  # None → birden fazla issue (tıklanmalı)
                if year_text:
                    items.append({'year': year_text, 'href': href})
        return items

    @staticmethod
    def extract_issue_list(page_source: str) -> List[Dict]:
        """
        Yıl tıklandıktan sonra beliren issue listesini parse eder.

        Returns:
            list[dict]: [{'url': str, 'title': str}, ...]
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        issues = []
        for container in soup.find_all('section', class_='issue-container'):
            volume_el = container.find('strong')
            volume = volume_el.get_text(strip=True) if volume_el else ''
            for issue_div in container.find_all('div', class_='issue-details'):
                a = issue_div.find('a')
                if a and a.get('href'):
                    label = a.get_text(strip=True)
                    title = f"{volume} {label}".strip() if volume else label
                    issues.append({'url': a['href'], 'title': title})
        return issues

    @staticmethod
    def is_volumes_page(page_source: str) -> bool:
        """
        Sayfanın 'All Volumes' tipi olup olmadığını tespit eder.

        All Volumes sayfalarında decade sekmesi yoktur; bunun yerine yıl numaraları
        (2026, 2025, ...) doğrudan href ile 'issue-details-past-tabs' div'inde
        listelenir ve ayrı bir 'year'-classed div bulunmaz.

        Returns:
            bool: All Volumes tipi sayfa ise True
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        # year-classed div varsa bu normal bir All Issues sayfasıdır
        year_divs = [d for d in soup.find_all('div', class_='issue-details-past-tabs')
                     if 'year' in (d.get('class') or [])]
        if year_divs:
            return False
        # Non-year issue-details-past-tabs div'inde href'li linkler bulunuyorsa volumes sayfasıdır
        for div in soup.find_all('div', class_='issue-details-past-tabs'):
            if 'year' in (div.get('class') or []):
                continue
            links = div.find_all('a', href=True)
            if links:
                return True
        return False

    @staticmethod
    def extract_volumes_year_links(page_source: str) -> List[Dict]:
        """
        All Volumes sayfasındaki yıl → URL eşlemelerini döndürür.

        'issue-details-past-tabs' (non-year) div'indeki her <a> elementi birer
        volume/yıl kaydı olarak alınır.

        Returns:
            list[dict]: [{'url': str, 'title': str}, ...] (sayfadaki sıraya göre, yeni→eski)
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        items = []
        for div in soup.find_all('div', class_='issue-details-past-tabs'):
            if 'year' in (div.get('class') or []):
                continue
            for li in div.find_all('li'):
                a = li.find('a', href=True)
                if a:
                    title = a.get_text(strip=True)
                    href = a['href']
                    if title and href:
                        items.append({'url': href, 'title': title})
            if items:
                break  # İlk eşleşen div yeterli
        return items
