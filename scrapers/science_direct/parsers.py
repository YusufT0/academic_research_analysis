"""
HTML parsing functions for Science Direct scraper
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup

from utils.logger import get_logger
logger = get_logger('science_direct')


class JournalParser:
    """Journal bilgilerini parse eden sınıf"""
    
    @staticmethod
    def extract_journals_from_page(page_source: str) -> list:
        """
        Sayfa HTML'inden journal bilgilerini çıkarır (BeautifulSoup ile hızlı parse)
        
        Args:
            page_source: Sayfanın HTML içeriği
            
        Returns:
            list: Journal bilgilerinin listesi
        """
        try:
            logger.info("Sayfa taranıyor")
            
            # BeautifulSoup ile parse et (çok daha hızlı)
            logger.info("HTML parse ediliyor...")
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Publications list'i bul
            publication_list = soup.find('div', class_='publications-list')
            if not publication_list:
                logger.not_found("publications-list")
                return []
            
            # Tüm div elementlerini al (her div bir harf grubu)
            letter_divs = publication_list.find_all('div', recursive=False)
            logger.found(len(letter_divs), "harf grubu")
            
            journals = []
            
            for div in letter_divs:
                try:
                    # Harf başlığını al
                    letter_title = div.find('h2', class_='alphabet-heading')
                    current_letter = letter_title.get_text(strip=True) if letter_title else 'Unknown'
                    logger.info(f"Harf grubu: {current_letter}")
                    
                    # Bu div içindeki ul'u bul
                    inner_ul = div.find('ul')
                    if not inner_ul:
                        continue
                    
                    # Bu ul içindeki tüm li elementlerini al (sadece js-publication olanlar)
                    list_items = inner_ul.find_all('li', class_='js-publication')
                    
                    for item in list_items:
                        # Journal adını al
                        title_element = item.find('a', class_='js-publication-title')
                        if not title_element:
                            continue
                        
                        span_element = title_element.find('span', class_='anchor-text')
                        if not span_element:
                            continue
                        
                        journal_name = span_element.get_text(strip=True)
                        journal_href = title_element.get('href', '')
                        
                        # Journal tipini al
                        content_type_element = item.find('p', class_='js-publication-content-type')
                        content_type = content_type_element.get_text(strip=True) if content_type_element else 'Unknown'
                        
                        # Open access olup olmadığını kontrol et
                        is_open_access = False
                        open_access_element = item.find('span', class_='u-text-italic')
                        if open_access_element:
                            is_open_access = 'open access' in open_access_element.get_text(strip=True).lower()
                        
                        # Journal bilgisini sakla
                        journal_info = {
                            'name': journal_name,
                            'url': journal_href,
                            'type': content_type,
                            'open_access': is_open_access,
                            'letter_group': current_letter
                        }
                        
                        journals.append(journal_info)
                        
                except Exception as e:
                    # Harf grubu parse hatası, bir sonraki gruba geç
                    logger.warning(f"Harf grubu parse hatası: {e}")
                    continue
            
            logger.found(len(journals), "journal (parse süresi: <1s)")
            return journals
            
        except Exception as e:
            logger.error(f"Journal çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return []


class ArticleParser:
    """Makale bilgilerini parse eden sınıf"""
    
    @staticmethod
    def extract_latest_issue_url(page_source: str) -> str:
        """
        Journal ana sayfasından "Latest issue" linkini çıkarır
        
        Args:
            page_source: Journal ana sayfası HTML içeriği
            
        Returns:
            str: Latest issue URL'i veya None
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Articles & Issues accordion panel'ini bul
            accordion_panels = soup.find_all('li', class_='accordion-panel')
            
            for panel in accordion_panels:
                # Button'un text'ini kontrol et (Articles & Issues)
                button = panel.find('button', class_='accordion-panel-title')
                if button:
                    button_text = button.get_text(strip=True)
                    
                    if 'Articles' in button_text and 'Issues' in button_text:
                        # Bu panel içinde Latest issue linkini bul
                        latest_link = panel.find('a', string=lambda x: x and 'Latest issue' in x)
                        
                        if latest_link and latest_link.get('href'):
                            latest_url = latest_link['href']
                            logger.success(f"Latest issue linki bulundu: {latest_url}")
                            return latest_url
            
            # Alternatif: Doğrudan "Latest issue" text'i olan link'i ara
            latest_link = soup.find('a', class_='link-anchor', string=lambda x: x and 'Latest issue' in str(x))
            if latest_link and latest_link.get('href'):
                latest_url = latest_link['href']
                logger.success(f"Latest issue linki bulundu (alt): {latest_url}")
                return latest_url
            
            logger.warning("Latest issue linki bulunamadı")
            return None
            
        except Exception as e:
            logger.error(f"Latest issue URL çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def _parse_date_range(date_text: str) -> str:
        """
        Tarih aralığını ISO formatına dönüştürür
        Örn: '21-22 June 2014' -> '2014-06-21/2014-06-22'
             'June 2014' -> '2014-06'
             '15 March 2023' -> '2023-03-15'
        """
        import re
        from datetime import datetime
        
        if not date_text:
            return None
        
        # Ay isimleri mapping
        months = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }
        
        date_text = date_text.strip()
        
        try:
            # Pattern 1: "21-22 June 2014" veya "1-15 March 2023" (aralık)
            range_match = re.match(r'(\d{1,2})-(\d{1,2})\s+(\w+)\s+(\d{4})', date_text, re.IGNORECASE)
            if range_match:
                day1, day2, month, year = range_match.groups()
                month_num = months.get(month.lower())
                if month_num:
                    return f"{year}-{month_num}-{day1.zfill(2)}/{year}-{month_num}-{day2.zfill(2)}"
            
            # Pattern 2: "15 March 2023" (tek gün)
            single_day_match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_text, re.IGNORECASE)
            if single_day_match:
                day, month, year = single_day_match.groups()
                month_num = months.get(month.lower())
                if month_num:
                    return f"{year}-{month_num}-{day.zfill(2)}"
            
            # Pattern 3: "June 2014" veya "February 2026" (sadece ay-yıl)
            month_year_match = re.match(r'(\w+)\s+(\d{4})', date_text, re.IGNORECASE)
            if month_year_match:
                month, year = month_year_match.groups()
                month_num = months.get(month.lower())
                if month_num:
                    return f"{year}-{month_num}"
            
            # Pattern 4: Sadece yıl "2024"
            year_match = re.match(r'^(\d{4})$', date_text)
            if year_match:
                return year_match.group(1)
            
            # Dönüştürülemezse orijinal metni döndür
            return date_text
            
        except Exception:
            return date_text
    
    @staticmethod
    def extract_issue_info(page_source: str) -> dict:
        """
        Issue sayfasından issue bilgilerini çıkarır (Issue Number, Date)
        
        Args:
            page_source: Issue sayfası HTML içeriği
            
        Returns:
            dict: Issue bilgileri {issue_number, date, status, url}
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            
            issue_info = {
                'issue_number': None,
                'date': None,
                'status': None,
                'url': None
            }
            
            # 1. h2.js-vol-issue - Issue number bilgisi (örn: "Volume 187")
            volume_h2 = soup.find('h2', class_='js-vol-issue')
            if volume_h2:
                issue_info['issue_number'] = volume_h2.get_text(strip=True)
                logger.success(f"Issue Number: {issue_info['issue_number']}")
            
            # 2. h2.js-special-issue-title - Special Issue başlığı (alternatif/ek issue bilgisi)
            special_issue_h2 = soup.find('h2', class_='js-special-issue-title')
            if special_issue_h2:
                special_title = special_issue_h2.get_text(strip=True)
                # Issue number yoksa special title'ı kullan, varsa birleştir
                if not issue_info['issue_number']:
                    issue_info['issue_number'] = special_title
                else:
                    issue_info['issue_number'] = f"{issue_info['issue_number']} - {special_title}"
                logger.success(f"Special Issue: {special_title}")
            
            # 3. span.js-date-range - Tarih aralığı (örn: "21-22 June 2014")
            date_range_span = soup.find('span', class_='js-date-range')
            if date_range_span:
                raw_date = date_range_span.get_text(strip=True)
                # Tarihi ISO formatına dönüştür
                issue_info['date'] = ArticleParser._parse_date_range(raw_date)
                logger.success(f"Date (from js-date-range): {raw_date} -> {issue_info['date']}")
            
            # 4. h3.js-issue-status - Tarih ve durum bilgisi (örn: "In progress (February 2026)")
            status_h3 = soup.find('h3', class_='js-issue-status')
            if status_h3:
                status_text = status_h3.get_text(strip=True)
                issue_info['status'] = status_text
                
                # Eğer date henüz alınmadıysa, parantez içinden al
                if not issue_info['date']:
                    import re
                    date_match = re.search(r'\(([^)]+)\)', status_text)
                    if date_match:
                        raw_date = date_match.group(1)
                        issue_info['date'] = ArticleParser._parse_date_range(raw_date)
                        logger.success(f"Date (from status): {raw_date} -> {issue_info['date']}")
                    else:
                        # Parantez yoksa tüm metni date olarak dönüştür
                        issue_info['date'] = ArticleParser._parse_date_range(status_text)
                        logger.success(f"Date/Status: {status_text} -> {issue_info['date']}")
                
                logger.success(f"Status: {status_text}")
            
            return issue_info
            
        except Exception as e:
            logger.error(f"Issue bilgisi çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return {'issue_number': None, 'date': None, 'status': None, 'url': None}
    
    @staticmethod
    def extract_article_urls_from_issue(page_source: str) -> list:
        """
        Issue sayfasındaki 'ol.js-article-list' içinden makale URL'lerini çıkarır
        Sadece 'Research article' tipindeki makaleleri alır
        
        Args:
            page_source: Issue sayfası HTML içeriği
            
        Returns:
            list: Makale URL'lerinin listesi
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # ol.js-article-list içindeki makaleleri bul
            article_list = soup.find('ol', class_='js-article-list')
            
            if not article_list:
                logger.not_found("js-article-list")
                return []
            
            # Tüm li.js-article-list-item elementlerini bul
            article_items = article_list.find_all('li', class_='js-article-list-item')
            logger.found(len(article_items), "article item")
            
            article_urls = []
            skipped_count = 0
            
            for idx, item in enumerate(article_items, 1):
                try:
                    # dl.js-article içindeki article type'ı kontrol et
                    article_dl = item.find('dl', class_='js-article')
                    
                    if article_dl:
                        # js-article-subtype span'ını bul
                        subtype_span = article_dl.find('span', class_='js-article-subtype')
                        
                        if subtype_span:
                            article_type = subtype_span.get_text(strip=True)
                            
                            # Sadece "Research article" tipindeki makaleleri al
                            if article_type != 'Research article':
                                skipped_count += 1
                                logger.debug(f"{idx}. Atlandı (Tip: {article_type})")
                                continue
                    
                    # a.article-content-title linkini bul
                    title_link = item.find('a', class_='article-content-title')
                    
                    if title_link and title_link.get('href'):
                        article_url = title_link['href']
                        article_urls.append(article_url)
                        
                        # Makale başlığını da al (log için)
                        title_span = title_link.find('span', class_='js-article-title')
                        title_text = title_span.get_text(strip=True)[:60] if title_span else article_url
                        logger.success(f"{idx}. {title_text}...")
                    
                except Exception as e:
                    logger.warning(f"Article {idx} parse hatası: {e}")
                    continue
            
            logger.found(len(article_urls), "Research article URL'i")
            if skipped_count > 0:
                logger.info(f"{skipped_count} makale atlandı (Research article değil)")
            return article_urls
            
        except Exception as e:
            logger.error(f"Article URL çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def extract_article_urls(page_source: str) -> list:
        """
        Journal sayfasındaki 'latest-published-articles' div'inden makale URL'lerini çıkarır
        (Eski yöntem - geriye uyumluluk için korundu)
        
        Args:
            page_source: Sayfa HTML içeriği
            
        Returns:
            list: Makale URL'lerinin listesi
        """
        try:
            # BeautifulSoup ile parse et
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Latest published articles div'ini bul
            latest_articles_div = soup.find('div', id='latest-published-articles')
            
            if not latest_articles_div:
                logger.not_found("latest-published-articles div")
                return []
            
            # Tüm article item'ları bul
            article_items = latest_articles_div.find_all('div', class_='js-article-item')
            logger.found(len(article_items), "article item")
            
            article_urls = []
            
            for idx, item in enumerate(article_items, 1):
                try:
                    # Article title link'ini bul
                    title_link = item.find('a', class_='js-article__item__title__link')
                    
                    if title_link and title_link.get('href'):
                        article_url = title_link['href']
                        article_urls.append(article_url)
                        logger.debug(f"{idx}. {article_url}")
                    
                except Exception as e:
                    logger.warning(f"Article {idx} parse hatası: {e}")
                    continue
            
            logger.found(len(article_urls), "makale URL'i")
            return article_urls
            
        except Exception as e:
            logger.error(f"Latest articles çıkarma hatası: {e}")
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
            # BeautifulSoup ile parse et
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
            title_span = soup.find('span', class_='title-text')
            if title_span:
                article_details['title'] = title_span.get_text(strip=True)
                logger.success(f"Başlık: {article_details['title'][:50]}...")
            else:
                logger.warning("Başlık bulunamadı")
            
            # 2. PDF URL'ini al
            logger.info("PDF linki aranıyor...")
            pdf_link = soup.find('a', class_='link-button', attrs={'aria-label': lambda x: x and 'View PDF' in x})
            if not pdf_link:
                # Alternatif selektör
                pdf_link = soup.find('a', href=lambda x: x and 'pdfft' in x)
            
            if pdf_link and pdf_link.get('href'):
                article_details['pdf_url'] = pdf_link['href']
                logger.success(f"PDF URL: {article_details['pdf_url']}")
            else:
                logger.warning("PDF linki bulunamadı")
            
            # 3. Yazarları al
            logger.info("Yazarlar alınıyor...")
            author_group = soup.find('div', class_='author-group')
            
            if author_group:
                # Tüm yazar butonlarını bul
                author_buttons = author_group.find_all('button', class_='button-link')
                
                for author_btn in author_buttons:
                    try:
                        given_name_span = author_btn.find('span', class_='given-name')
                        surname_span = author_btn.find('span', class_='surname')
                        
                        if given_name_span and surname_span:
                            given_name = given_name_span.get_text(strip=True)
                            surname = surname_span.get_text(strip=True)
                            full_name = f"{given_name} {surname}"
                            article_details['authors'].append(full_name)
                    except:
                        continue
                
                logger.found(len(article_details['authors']), f"yazar: {', '.join(article_details['authors'][:3])}{'...' if len(article_details['authors']) > 3 else ''}")
            else:
                logger.warning("Yazar bilgisi bulunamadı")
            
            # 4. DOI al
            logger.info("DOI aranıyor...")
            doi_link = soup.find('a', class_='doi')
            
            if doi_link:
                doi_text = doi_link.get_text(strip=True)
                article_details['doi'] = doi_text
                logger.success(f"DOI: {doi_text}")
            else:
                logger.warning("DOI bulunamadı")
            
            # 5. Publication Date, Pages, Publisher al
            logger.info("Meta bilgiler alınıyor...")
            
            # Publication Date - Banner içindeki "Available online" tarihinden
            publication_date = ArticleParser._extract_available_online_date(soup)
            if publication_date:
                article_details['publication_date'] = publication_date
            else:
                # Fallback: volume-issue-info veya article-dates alanlarından
                volume_info = soup.find('div', class_='publication-volume')
                if volume_info:
                    volume_text = volume_info.get_text(strip=True)
                    article_details['publication_date'] = volume_text
                else:
                    # Alternatif: Online date alanı
                    date_span = soup.find('span', class_='online-date')
                    if date_span:
                        article_details['publication_date'] = date_span.get_text(strip=True)
            
            # Pages
            pages_span = soup.find('span', class_='page-info')
            if not pages_span:
                # Alternatif: Volume info içinde 'Pages' metni
                pages_div = soup.find('div', class_='text-xs')
                if pages_div:
                    pages_text = pages_div.get_text(strip=True)
                    if 'Pages' in pages_text or 'pp.' in pages_text:
                        article_details['pages'] = pages_text
            else:
                article_details['pages'] = pages_span.get_text(strip=True)
            
            # Publisher - genellikle "Elsevier" veya header'daki bilgi
            publisher_link = soup.find('a', href=lambda x: x and '/journal/' in str(x))
            if publisher_link:
                # Journal adını publisher olarak kullan (Science Direct için genellikle Elsevier)
                article_details['publisher'] = 'Elsevier'
            
            logger.success(f"Meta: Date={bool(article_details['publication_date'])}, Pages={bool(article_details['pages'])}")
            
            # 6. Abstract al
            logger.info("Abstract alınıyor...")
            article_details['abstract'] = ArticleParser._extract_abstract(soup)
            
            if article_details['abstract']:
                logger.success(f"Abstract alındı ({len(article_details['abstract'])} karakter)")
            else:
                logger.warning("Abstract bulunamadı")
            
            # 7. Introduction (Giriş bölümü) al
            logger.info("Introduction alınıyor...")
            article_details['introduction'] = ArticleParser._extract_introduction(soup)
            
            if article_details['introduction']:
                logger.success(f"Introduction alındı ({len(article_details['introduction'])} karakter)")
            else:
                logger.warning("Introduction bulunamadı")
            
            return article_details
            
        except Exception as e:
            logger.error(f"Makale detay çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def _extract_available_online_date(soup: BeautifulSoup) -> str:
        """
        Banner içindeki "Available online" tarihini çıkarır ve ISO formatına çevirir.
        
        Örnek HTML:
        <p class="u-margin-s-bottom">Available online 28 September 2014.</p>
        <p class="u-margin-s-bottom">Received 2 April 2025, Revised 6 August 2025, Accepted 7 November 2025, Available online 11 November 2025, Version of Record 12 November 2025.</p>
        
        Returns:
            str: ISO formatında tarih (örn: "2014-09-28") veya None
        """
        import re
        from datetime import datetime
        
        # Banner div'ini bul
        banner_div = soup.find('div', class_='Banner')
        if not banner_div:
            banner_div = soup.find('div', id='banner')
        
        if not banner_div:
            return None
        
        # u-margin-s-bottom sınıflı tüm p etiketlerini bul
        date_paragraphs = banner_div.find_all('p', class_='u-margin-s-bottom')
        
        for p in date_paragraphs:
            text = p.get_text(strip=True)
            
            # "Available online" içeren metni bul
            if 'Available online' in text:
                # "Available online 28 September 2014" veya "Available online 11 November 2025" formatını çıkar
                # Pattern: "Available online" + tarih
                match = re.search(r'Available online\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text)
                
                if match:
                    day = match.group(1)
                    month_name = match.group(2)
                    year = match.group(3)
                    
                    # Ay adını numaraya çevir
                    month_mapping = {
                        'January': '01', 'February': '02', 'March': '03', 'April': '04',
                        'May': '05', 'June': '06', 'July': '07', 'August': '08',
                        'September': '09', 'October': '10', 'November': '11', 'December': '12'
                    }
                    
                    month = month_mapping.get(month_name)
                    if month:
                        # ISO formatında döndür: YYYY-MM-DD
                        return f"{year}-{month}-{day.zfill(2)}"
        
        return None
    
    @staticmethod
    def _extract_abstract(soup: BeautifulSoup) -> str:
        """Abstract'ı çıkarır"""
        abstract_text = None
        
        # Yöntem 1: class='abstract author' ile id'ye bakılmaksızın
        abstract_div = soup.find('div', class_='abstract author')
        
        if abstract_div:
            # Abstract içindeki tüm div.u-margin-s-bottom paragraflarını al
            abstract_paragraphs = abstract_div.find_all('div', class_='u-margin-s-bottom')
            
            if abstract_paragraphs:
                abstract_text = '\n\n'.join([p.get_text(strip=True) for p in abstract_paragraphs])
            else:
                # Paragraf bulunamadıysa, doğrudan div içeriğini al
                # Başlığı (h2) hariç tut
                for h2 in abstract_div.find_all('h2'):
                    h2.decompose()
                abstract_text = abstract_div.get_text(strip=True)
        
        # Yöntem 2: Eğer bulunamadıysa, id='abstracts' ile dene
        if not abstract_text:
            abstracts_container = soup.find('div', id='abstracts')
            if abstracts_container:
                # İçindeki tüm paragrafları al
                abstract_paragraphs = abstracts_container.find_all('div', class_='u-margin-s-bottom')
                if abstract_paragraphs:
                    abstract_text = '\n\n'.join([p.get_text(strip=True) for p in abstract_paragraphs])
        
        # Yöntem 3: Son çare - 'Abstract' başlığı olan herhangi bir h2'den sonraki içerik
        if not abstract_text:
            abstract_headers = soup.find_all('h2', string=lambda x: x and 'Abstract' in x)
            for header in abstract_headers:
                parent_div = header.find_parent('div')
                if parent_div:
                    # h2'yi kaldır
                    for h2 in parent_div.find_all('h2'):
                        h2.decompose()
                    abstract_text = parent_div.get_text(strip=True)
                    if abstract_text:
                        break
        
        return abstract_text
    
    @staticmethod
    def _extract_introduction(soup: BeautifulSoup) -> str:
        """
        Makale giriş (Introduction) bölümünü çıkarır
        Science Direct'te genellikle 'sec1' veya '1. Introduction' şeklinde olur
        """
        body_div = soup.find('div', class_='Body', id='body')
        
        if not body_div:
            return None
        
        # Yöntem 1: sec1 id'li section'ı ara (genellikle Introduction)
        intro_section = body_div.find('section', id='sec1')
        
        if intro_section:
            # Section başlığını kontrol et (Introduction olduğundan emin ol)
            section_title_elem = intro_section.find(['h2', 'h3', 'h4'])
            
            if section_title_elem:
                section_title = section_title_elem.get_text(strip=True).lower()
                
                # Introduction bölümü olduğunu doğrula
                if 'introduction' in section_title or section_title.startswith('1.'):
                    # Tüm a tag'lerini kaldır
                    for a_tag in intro_section.find_all('a'):
                        a_tag.decompose()
                    
                    # Paragrafları al
                    paragraphs = intro_section.find_all('div', class_='u-margin-s-bottom')
                    intro_text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs])
                    
                    if intro_text:
                        return intro_text
        
        # Yöntem 2: Tüm section'ları tara ve "Introduction" başlıklı olanı bul
        sections = body_div.find_all('section')
        
        for section in sections:
            section_title_elem = section.find(['h2', 'h3', 'h4'])
            
            if section_title_elem:
                section_title = section_title_elem.get_text(strip=True).lower()
                
                # "introduction" veya "1." ile başlayan başlık
                if 'introduction' in section_title or section_title.startswith('1.'):
                    # Tüm a tag'lerini kaldır
                    for a_tag in section.find_all('a'):
                        a_tag.decompose()
                    
                    # Paragrafları al
                    paragraphs = section.find_all('div', class_='u-margin-s-bottom')
                    intro_text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs])
                    
                    if intro_text:
                        return intro_text
        
        # Yöntem 3: İlk section'ı al (eğer Introduction bulunamazsa)
        if sections:
            first_section = sections[0]
            
            # Tüm a tag'lerini kaldır
            for a_tag in first_section.find_all('a'):
                a_tag.decompose()
            
            # Paragrafları al
            paragraphs = first_section.find_all('div', class_='u-margin-s-bottom')
            intro_text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs])
            
            if intro_text:
                return intro_text
        
        return None
