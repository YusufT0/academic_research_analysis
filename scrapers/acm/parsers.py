"""
HTML parsing functions for ACM Digital Library scraper
"""

import re
import sys
from bs4 import BeautifulSoup

sys.path.insert(0, str(__file__).rsplit('acm', 1)[0])
from utils.logger import get_logger
logger = get_logger('acm')


class JournalParser:
    """ACM Journal bilgilerini parse eden sınıf"""

    @staticmethod
    def extract_aims_and_scope(page_source: str):
        """
        /journal/CODE sayfasındaki .item-meta__info > .truncate-text bölümünden
        aims & scope içeriğini çıkarır.

        (More) butonuna dışarıdan tıklandıktan sonra çağrılmalıdır; bu metot
        sadece mevcut DOM'u parse eder.

        Returns:
            str: Temizlenmiş inner HTML içeriği veya None
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')

            # .item-meta__info altındaki .truncate-text div'ini bul
            info_div = soup.find('div', class_='item-meta__info')
            if not info_div:
                logger.warning("Aims & scope: .item-meta__info bulunamadı")
                return None

            truncate_div = info_div.find('div', class_='truncate-text')
            if not truncate_div:
                logger.warning("Aims & scope: .truncate-text bulunamadı")
                return None

            # read-more ve read-less butonlarını kaldır
            for btn in truncate_div.find_all(['span', 'button'], class_=['read-more', 'read-less']):
                btn.decompose()

            # Boş mu kontrol et
            text_content = truncate_div.get_text(strip=True)
            if not text_content:
                logger.warning("Aims & scope: İçerik boş")
                return None

            html_content = truncate_div.decode_contents().strip()
            logger.success("Aims & scope bulundu (.item-meta__info .truncate-text)")
            return html_content

        except Exception as e:
            logger.error(f"ACM aims & scope çıkarma hatası: {e}")
            return None

    @staticmethod
    def extract_journals_from_page(page_source: str) -> list:
        """
        ACM Journals sayfasındaki HTML'den journal bilgilerini çıkarır.
        
        Hedef HTML yapısı:
        <ul class="search-result__body ... journalBrowse--lazyLoad">
          <li class="search__item search__item-journal ...">
            <a href="/journal/CODE" class="browse-item-cover">
              <img src="..." alt="...">
            </a>
            <div class="browse-item-body">
              <h3 class="search__item-title">
                <a href="/journal/CODE" class="browse-link">
                  <span class="browse-code">CODE</span>
                  <span class="browse-title">Journal Title</span>
                </a>
              </h3>
              <div class="meta">
                <div class="meta__abstract"><p>Description...</p></div>
                <div class="meta__editor">...</div>
              </div>
            </div>
          </li>
          ...
        </ul>
        
        Args:
            page_source: Sayfanın HTML içeriği
            
        Returns:
            list: Journal bilgilerinin listesi
        """
        try:
            logger.info("Sayfa taranıyor...")
            
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Journal item'larını bul
            journal_items = soup.find_all('li', class_=lambda c: c and 'search__item-journal' in c)
            
            if not journal_items:
                # Alternatif: tüm search__item-browse li'lerini dene
                journal_items = soup.find_all('li', class_=lambda c: c and 'search__item-browse' in c)
            
            if not journal_items:
                logger.error("Journal item'ları bulunamadı")
                return []
            
            logger.found(len(journal_items), "journal item")
            
            journals = []
            
            for idx, item in enumerate(journal_items, 1):
                try:
                    # browse-link içindeki bilgileri al
                    browse_link = item.find('a', class_='browse-link')
                    if not browse_link:
                        continue
                    
                    # Journal kodu
                    code_span = browse_link.find('span', class_='browse-code')
                    journal_code = code_span.get_text(strip=True) if code_span else None
                    
                    # Journal başlığı
                    title_span = browse_link.find('span', class_='browse-title')
                    journal_name = title_span.get_text(strip=True) if title_span else None
                    
                    if not journal_name:
                        continue
                    
                    # Journal URL'i
                    journal_url = browse_link.get('href', '')
                    
                    # Kapak resmi
                    cover_img = item.find('img', class_='lazy')
                    if not cover_img:
                        cover_img = item.find('img')
                    cover_url = cover_img.get('src', '') if cover_img else None
                    
                    # Açıklama (abstract)
                    meta_abstract = item.find('div', class_='meta__abstract')
                    description = None
                    if meta_abstract:
                        p_tag = meta_abstract.find('p')
                        if p_tag:
                            description = p_tag.get_text(strip=True)
                    
                    # Editör bilgisi
                    editors = []
                    meta_editor = item.find('div', class_='meta__editor')
                    if meta_editor:
                        author_links = meta_editor.find_all('a', class_='author')
                        for author_link in author_links:
                            name_span = author_link.find('span', class_='author-name')
                            if name_span:
                                editors.append(name_span.get_text(strip=True))
                    
                    journal_info = {
                        'code': journal_code,
                        'name': journal_name,
                        'url': journal_url,
                        'cover_url': cover_url,
                        'description': description,
                        'editors': editors
                    }
                    
                    journals.append(journal_info)
                    logger.item(idx, len(journal_items), f"{journal_code}: {journal_name}")
                    
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
    """ACM Issue sayfasından makale bilgilerini parse eden sınıf"""
    
    @staticmethod
    def extract_article_urls(page_source: str) -> list:
        """
        ACM Issue (toc) sayfasındaki makale URL'lerini çıkarır.
        
        Hedef HTML yapısı:
        <div class="issue-item-container">
          <div class="issue-item clearfix">
            <div class="issue-item__citation">
              <div class="issue-heading">research-article</div>
            </div>
            <div class="issue-item__content">
              <div class="issue-item__content-right">
                <h3 class="issue-item__title">
                  <a href="/doi/10.1145/XXXXXXX">Article Title</a>
                </h3>
                ...
              </div>
            </div>
          </div>
        </div>
        
        Args:
            page_source: Sayfa HTML içeriği
            
        Returns:
            list: Makale bilgilerinin listesi [{'url': ..., 'title': ..., 'type': ...}, ...]
        """
        try:
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Tüm issue-item-container'ları bul
            item_containers = soup.find_all('div', class_='issue-item-container')
            
            if not item_containers:
                logger.warning("Issue item container'ları bulunamadı")
                return []
            
            logger.found(len(item_containers), "item container")
            
            articles = []
            
            for idx, container in enumerate(item_containers, 1):
                try:
                    # Makale başlığı ve URL'ini al
                    title_h3 = container.find('h3', class_='issue-item__title')
                    if not title_h3:
                        continue
                    
                    title_link = title_h3.find('a', href=True)
                    if not title_link:
                        continue
                    
                    article_url = title_link.get('href', '')
                    article_title = title_link.get_text(strip=True)
                    
                    # /doi/ ile başlayan linkler makale linkleridir
                    if '/doi/' not in article_url:
                        continue
                    
                    # Makale türü (research-article, survey, correction vs.)
                    article_type = None
                    type_div = container.find('div', class_='issue-heading')
                    if type_div:
                        article_type = type_div.get_text(strip=True)
                    
                    # Yazarlar
                    authors = []
                    author_list = container.find('ul', attrs={'aria-label': 'authors'})
                    if author_list:
                        author_links = author_list.find_all('a', title=True)
                        for a in author_links:
                            author_name = a.get('title', '').strip()
                            if author_name:
                                authors.append(author_name)
                    
                    # Article No. ve Pages
                    article_no = None
                    pages = None
                    detail_div = container.find('div', class_='issue-item__detail')
                    if detail_div:
                        spans = detail_div.find_all('span')
                        for span in spans:
                            text = span.get_text(strip=True)
                            if 'Article No' in text:
                                article_no = text
                            elif 'Pages' in text:
                                pages = text
                    
                    # DOI
                    doi = None
                    doi_link = container.find('a', class_='issue-item__doi')
                    if doi_link:
                        doi = doi_link.get_text(strip=True)
                    
                    article_info = {
                        'url': article_url,
                        'title': article_title,
                        'type': article_type,
                        'authors': authors,
                        'article_no': article_no,
                        'pages': pages,
                        'doi': doi,
                    }
                    
                    articles.append(article_info)
                    logger.info(f"  {len(articles)}. {article_title[:60]}...")
                    
                except Exception as e:
                    logger.warning(f"Article {idx} parse hatası: {e}")
                    continue
            
            logger.found(len(articles), "makale URL'i")
            return articles
            
        except Exception as e:
            logger.failed("Makale URL çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return []


class IssueListParser:
    """ACM LOI (List of Issues / Archive) sayfasını parse eden sınıf"""

    @staticmethod
    def extract_decade_tabs(page_source: str) -> list:
        """
        LOI sayfasındaki decade sekme bilgilerini DOM sırasıyla döndürür.

        Returns:
            list: [{'text': '2000s', 'data_url': 'd2000', 'panel_id': 'pane-xxx-d2000', 'is_active': False}, ...]
            Çağıran taraf en güncel decade'den başlamak için reversed() kullanmalıdır.
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        tabs = []
        for a in soup.find_all('a', class_=lambda c: c and 'decade-item' in c):
            data_url = a.get('data-url', '')
            if not data_url:
                continue
            panel_id = a.get('aria-controls', '')
            text = a.get_text(strip=True)
            li = a.find_parent('li')
            is_active = bool(li and 'active' in (li.get('class') or []))
            tabs.append({
                'text': text,
                'data_url': data_url,
                'panel_id': panel_id,
                'is_active': is_active,
            })
        return tabs

    @staticmethod
    def extract_year_panel_info(page_source: str, decade_panel_id: str = None) -> list:
        """
        Belirli bir decade panelindeki year sekmelerini ve yüklenme durumlarını döndürür.

        Args:
            decade_panel_id: Sadece bu decade panel'inin içindeki year tab'ları aranır.
                             None verilirse tüm sayfada arar (eski davranış, önerilmez).

        Returns:
            list: [{'text': '2024', 'panel_id': 'pane-xxx-y2024', 'has_issues': True}, ...]
            DOM sırasıyla döner; çağıran reversed() ile en güncel yıldan başlamalıdır.
        """
        soup = BeautifulSoup(page_source, 'html.parser')

        if decade_panel_id:
            scope = soup.find('div', id=decade_panel_id)
            if not scope:
                return []
        else:
            scope = soup

        years = []
        seen_panels = set()

        for year_tab in scope.find_all('a', class_=lambda c: c and 'year-item' in c):
            panel_id = year_tab.get('aria-controls', '')
            if not panel_id or panel_id in seen_panels:
                continue
            seen_panels.add(panel_id)

            text = year_tab.get_text(strip=True)
            # Panel soup'un herhangi bir yerinde olabilir (scope dışında olsa bile)
            panel = soup.find('div', id=panel_id)
            has_issues = bool(panel and panel.find('a', class_='loi__issue')) if panel else False

            years.append({
                'text': text,
                'panel_id': panel_id,
                'has_issues': has_issues,
            })

        return years

    @staticmethod
    def extract_issues_from_panel(page_source: str, panel_id: str) -> list:
        """
        Belirli bir year panelindeki issue linklerini döndürür.

        Returns:
            list: [{'url': '/toc/CODE/YEAR/VOL/ISSUE', 'title': 'December 2024, Issue 4'}, ...]
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        panel = soup.find('div', id=panel_id)
        if not panel:
            return []
        return IssueListParser._extract_issues_from_soup(panel)

    @staticmethod
    def extract_all_issues_from_page(page_source: str) -> list:
        """
        Sayfadaki TÜM issue linklerini döndürür (tüm panellerden).

        Returns:
            list: [{'url': ..., 'title': ...}, ...]
        """
        soup = BeautifulSoup(page_source, 'html.parser')
        return IssueListParser._extract_issues_from_soup(soup)

    @staticmethod
    def _extract_issues_from_soup(soup) -> list:
        """BeautifulSoup nesnesinden a.loi__issue linklerini çıkarır."""
        issues = []
        seen = set()
        for link in soup.find_all('a', class_='loi__issue', href=True):
            href = link.get('href', '')
            if not href or href in seen:
                continue
            seen.add(href)

            cover_date = link.find('span', class_='coverDate')
            issue_span = link.find('span', class_='issue')
            parts = []
            if cover_date:
                parts.append(cover_date.get_text(strip=True))
            if issue_span:
                parts.append(issue_span.get_text(strip=True))
            title = ', '.join(parts) if parts else (link.get('title') or href)

            issues.append({'url': href, 'title': title})
        return issues


class ArticleDetailParser:
    """ACM makale detay sayfasından bilgileri parse eden sınıf"""
    
    # Ay adı -> numara eşleştirmesi
    MONTH_MAP = {
        'january': '01', 'jan': '01',
        'february': '02', 'feb': '02',
        'march': '03', 'mar': '03',
        'april': '04', 'apr': '04',
        'may': '05',
        'june': '06', 'jun': '06',
        'july': '07', 'jul': '07',
        'august': '08', 'aug': '08',
        'september': '09', 'sep': '09', 'sept': '09',
        'october': '10', 'oct': '10',
        'november': '11', 'nov': '11',
        'december': '12', 'dec': '12',
    }
    
    @staticmethod
    def _parse_acm_date(date_text: str) -> str:
        """
        ACM tarih formatını ISO formatına çevirir.
        
        "24 November 2025" -> "2025-11-24"
        "November 2025" -> "2025-11"
        "2025" -> "2025"
        
        Args:
            date_text: Ham tarih metni
            
        Returns:
            str: ISO formatında tarih veya orijinal metin
        """
        if not date_text:
            return None
        
        date_text = date_text.strip()
        
        # Pattern 1: "24 November 2025"
        match = re.match(r'^(\d{1,2})\s+(\w+)\s+(\d{4})$', date_text)
        if match:
            day = match.group(1).zfill(2)
            month_name = match.group(2).lower()
            year = match.group(3)
            month = ArticleDetailParser.MONTH_MAP.get(month_name)
            if month:
                return f"{year}-{month}-{day}"
        
        # Pattern 2: "November 2025"
        match = re.match(r'^(\w+)\s+(\d{4})$', date_text)
        if match:
            month_name = match.group(1).lower()
            year = match.group(2)
            month = ArticleDetailParser.MONTH_MAP.get(month_name)
            if month:
                return f"{year}-{month}"
        
        # Pattern 3: "2025"
        match = re.match(r'^(\d{4})$', date_text)
        if match:
            return match.group(1)
        
        return date_text
    
    @staticmethod
    def extract_article_details(page_source: str, article_url: str) -> dict:
        """
        ACM makale sayfasından detaylı bilgileri çıkarır.
        
        IEEE scraper'daki extract_article_details ile aynı dict yapısını döndürür:
        url, title, pdf_url, authors, doi, publication_date, pages, publisher,
        abstract, introduction, article_type, open_access, citation_count, keywords
        
        Args:
            page_source: Makale sayfasının HTML içeriği
            article_url: Makale URL'i
            
        Returns:
            dict: Makale detayları (DB Article modeli ile uyumlu)
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
                'publisher': 'ACM',
                'abstract': None,
                'introduction': None,
                'article_type': None,
                'open_access': False,
                'citation_count': 0,
                'keywords': [],
            }
            
            # ====== 1. BAŞLIK ======
            logger.info("Başlık alınıyor...")
            title_h1 = soup.find('h1', attrs={'property': 'name'})
            if title_h1:
                article_details['title'] = title_h1.get_text(strip=True)
                logger.success(f"Başlık: {article_details['title'][:60]}...")
            else:
                # Fallback: herhangi bir h1
                h1 = soup.find('h1')
                if h1:
                    article_details['title'] = h1.get_text(strip=True)
            
            # ====== 2. MAKALE TİPİ ve ERİŞİM ======
            logger.info("Makale tipi alınıyor...")
            meta_panel = soup.find('div', class_='meta-panel')
            if meta_panel:
                # Makale tipi: <div class="meta-panel__type"><span>research-article</span></div>
                type_div = meta_panel.find('div', class_='meta-panel__type')
                if type_div:
                    type_span = type_div.find('span')
                    if type_span:
                        article_details['article_type'] = type_span.get_text(strip=True)
                
                # Open access: <div class="meta-panel__access meta-panel__access--open">
                access_div = meta_panel.find('div', class_=lambda c: c and 'meta-panel__access--open' in c)
                if access_div:
                    article_details['open_access'] = True
            
            # ====== 3. YAZARLAR ======
            logger.info("Yazarlar alınıyor...")
            contributors_div = soup.find('div', class_='contributors')
            if contributors_div:
                # Her yazar: <span property="author" typeof="Person">
                author_spans = contributors_div.find_all('span', attrs={'property': 'author', 'typeof': 'Person'})
                
                for author_span in author_spans:
                    # İsim: <span property="givenName"> + <span property="familyName">
                    given = author_span.find('span', attrs={'property': 'givenName'})
                    family = author_span.find('span', attrs={'property': 'familyName'})
                    
                    if given and family:
                        full_name = f"{given.get_text(strip=True)} {family.get_text(strip=True)}"
                        article_details['authors'].append(full_name)
                    elif author_span.find('a', title=True):
                        # Fallback: title attribute
                        article_details['authors'].append(
                            author_span.find('a', title=True)['title']
                        )
                
                logger.found(len(article_details['authors']), "yazar")
            else:
                logger.warning("Yazar bilgisi bulunamadı")
            
            # ====== 4. DOI ======
            logger.info("DOI alınıyor...")
            doi_div = soup.find('div', class_='doi')
            if doi_div:
                doi_link = doi_div.find('a', attrs={'property': 'sameAs'})
                if doi_link:
                    doi_text = doi_link.get_text(strip=True)
                    # "https://doi.org/10.1145/XXXX" -> "10.1145/XXXX"
                    if 'doi.org/' in doi_text:
                        article_details['doi'] = doi_text.split('doi.org/')[-1]
                    else:
                        article_details['doi'] = doi_text
            
            # ====== 5. YAYIN TARİHİ ======
            logger.info("Yayın tarihi alınıyor...")
            published_div = soup.find('div', class_='core-published')
            if published_div:
                date_span = published_div.find('span', class_='core-date-published')
                if date_span:
                    raw_date = date_span.get_text(strip=True)
                    article_details['publication_date'] = ArticleDetailParser._parse_acm_date(raw_date)
                    logger.success(f"Yayın tarihi: {article_details['publication_date']}")
            
            # ====== 6. VOLUME / ISSUE / PAGES ======
            logger.info("Volume/Issue/Pages alınıyor...")
            citation_div = soup.find('div', class_='core-self-citation')
            if citation_div:
                # Pages: <span property="pageStart">1</span> - <span property="pageEnd">23</span>
                page_start = citation_div.find('span', attrs={'property': 'pageStart'})
                page_end = citation_div.find('span', attrs={'property': 'pageEnd'})
                if page_start and page_end:
                    article_details['pages'] = f"{page_start.get_text(strip=True)}-{page_end.get_text(strip=True)}"
                
                # Volume
                volume_span = citation_div.find('span', attrs={'property': 'volumeNumber'})
                if volume_span:
                    article_details['volume'] = volume_span.get_text(strip=True)
                
                # Issue
                issue_span = citation_div.find('span', attrs={'property': 'issueNumber'})
                if issue_span:
                    article_details['issue_number'] = issue_span.get_text(strip=True)
                
                # Journal name (from breadcrumb or self-citation)
                journal_name_span = citation_div.find('span', attrs={'property': 'name'})
                if journal_name_span:
                    article_details['journal_name'] = journal_name_span.get_text(strip=True)
            
            # ====== 7. PDF URL ======
            logger.info("PDF URL alınıyor...")
            pdf_link = soup.find('a', class_=lambda c: c and 'btn--eReader' in c, href=lambda h: h and '/epdf/' in h)
            if pdf_link:
                pdf_href = pdf_link.get('href', '')
                pdf_path = pdf_href.replace('/epdf/', '/pdf/')
                if pdf_path.startswith('/'):
                    article_details['pdf_url'] = f"https://dl.acm.org{pdf_path}?download=true"
                else:
                    article_details['pdf_url'] = f"{pdf_path}?download=true"
                logger.success(f"PDF URL bulundu: {article_details['pdf_url']}")
            else:
                logger.warning("PDF URL bulunamadı")
            
            # ====== 8. ABSTRACT ======
            logger.info("Abstract alınıyor...")
            abstract_section = soup.find('section', id='abstract')
            if abstract_section:
                # Abstract paragrafları
                paragraphs = abstract_section.find_all('div', attrs={'role': 'paragraph'})
                if paragraphs:
                    abstract_text = ' '.join(p.get_text(strip=True) for p in paragraphs)
                    article_details['abstract'] = abstract_text
                    logger.success(f"Abstract alındı ({len(abstract_text)} karakter)")
                else:
                    # Fallback: tüm section metni (h3 hariç)
                    for h in abstract_section.find_all(['h2', 'h3']):
                        h.decompose()
                    text = abstract_section.get_text(strip=True)
                    if text:
                        article_details['abstract'] = text
                        logger.success(f"Abstract alındı (fallback, {len(text)} karakter)")
            else:
                logger.warning("Abstract bulunamadı")
            
            # ====== 9. INTRODUCTION (body text) ======
            logger.info("Introduction alınıyor...")
            body_section = soup.find('section', id='bodymatter')
            if body_section:
                # İlk section genelde Introduction
                first_section = body_section.find('section')
                if first_section:
                    # Başlık + paragraflar
                    section_text = first_section.get_text(separator='\n', strip=True)
                    if section_text:
                        article_details['introduction'] = section_text
                        logger.success(f"Introduction alındı ({len(section_text)} karakter)")
            
            if not article_details.get('introduction'):
                logger.warning("Introduction bulunamadı")
            
            # ====== 10. KEYWORDS ======
            logger.info("Keywords alınıyor...")
            # ACM keywords genelde ayrı bir bölümde olabilir
            keyword_section = soup.find('section', class_='article-keywords')
            if not keyword_section:
                keyword_section = soup.find('ol', class_='rlist organizational-chart')
            
            if keyword_section:
                keyword_links = keyword_section.find_all('a')
                for kw_link in keyword_links:
                    kw_text = kw_link.get_text(strip=True)
                    if kw_text and len(kw_text) < 100:  # Çok uzun metinleri filtrele
                        article_details['keywords'].append(kw_text)
                
                if article_details['keywords']:
                    logger.found(len(article_details['keywords']), "keyword")
            
            # ====== 11. CITATION COUNT ======
            metrics_div = soup.find('div', class_='pub-metrics')
            if metrics_div:
                citation_span = metrics_div.find('span', class_='citation')
                if citation_span:
                    count_span = citation_span.find('span', string=re.compile(r'^\d+$'))
                    if count_span:
                        try:
                            article_details['citation_count'] = int(count_span.get_text(strip=True))
                        except ValueError:
                            pass
            
            logger.success(f"Meta bilgiler: DOI={bool(article_details['doi'])}, "
                          f"Date={bool(article_details['publication_date'])}, "
                          f"Pages={bool(article_details['pages'])}, "
                          f"Type={article_details['article_type']}, "
                          f"OpenAccess={article_details['open_access']}")
            
            return article_details
            
        except Exception as e:
            logger.failed("Makale detay çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return None

