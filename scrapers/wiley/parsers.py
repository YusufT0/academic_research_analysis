"""
HTML parsers for Wiley Online Library scraper.
All selectors are based on draft.md HTML structures.
"""

import re
import sys
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup

sys.path.insert(0, str(__file__).rsplit('wiley', 1)[0])
from utils.logger import get_logger
logger = get_logger('wiley')


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, 'html.parser')


def _clean(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.replace('\u00a0', ' ')).strip()


# ══════════════════════════════════════════════════════════════════════════════
# JOURNAL PARSER
# ══════════════════════════════════════════════════════════════════════════════

class JournalParser:
    """Wiley journal list, detail ve issue list sayfalarını parse eder."""

    # ── Journal List ──────────────────────────────────────────────────────────

    @staticmethod
    def parse_journal_list(html: str) -> List[Dict[str, Any]]:
        """
        Journal arama sonuçları sayfasını parse eder.

        Selector: ul#search-result li.search__item (veya .cover-image__label)
        Her kartta: başlık, URL, ISSN, eISSN, Open Access flag.

        Returns:
            list: [{name, url, journal_id, issn, eissn, open_access}]
        """
        try:
            logger.info("Sayfa taranıyor...")

            soup = _soup(html)
            journals = []
            seen_ids = set()

            # Wiley journal listesi: Her kayıt bir <li class="search__item"> içinde
            items = soup.select('li.search__item')
            if not items:
                # Alternatif: div.cover-image__wrapper içindeki kartlar
                items = soup.select('div.cover-image')
            logger.found(len(items), "journal kartı")

            for idx, item in enumerate(items, 1):
                try:
                    journal = {}

                    # Başlık ve URL
                    title_el = item.select_one('h3.meta__title a, .cover-image__label a')
                    if not title_el:
                        # "Currently known as" journal'lar: h3 yerine span.no-link kullanır,
                        # asıl link span.meta__title__currentVersion içindedir
                        title_el = item.select_one('.meta__title__currentVersion a, span.meta__title a')
                    journal['name'] = _clean(title_el.get_text())
                    href = title_el.get('href', '')
                    if href:
                        journal['url'] = href if href.startswith('http') else f"https://onlinelibrary.wiley.com{href}"
                        # journal_id = URL'deki /journal/{id} kısmından
                        m = re.search(r'/journal/([a-zA-Z0-9\-\.]+)', href)
                        journal['journal_id'] = m.group(1) if m else ''
                    else:
                        continue

                    # ISSN / eISSN — format: <div class="meta__issns">ISSN: XXXX-XXXX</div>
                    #                        <div class="meta__eissn">EISSN: XXXX-XXXX</div>
                    issn_el = item.select_one('.meta__issns')
                    eissn_el = item.select_one('.meta__eissn')
                    if issn_el:
                        m = re.search(r'[\dX]{4}-[\dX]{4}', issn_el.get_text())
                        journal['issn'] = m.group(0) if m else ''
                    if eissn_el:
                        m = re.search(r'[\dX]{4}-[\dX]{4}', eissn_el.get_text())
                        journal['eissn'] = m.group(0) if m else ''

                    # Open Access
                    journal['open_access'] = bool(item.select_one('.access-type.open-access, .open-access-label'))

                    if journal.get('name') and journal.get('journal_id'):
                        if journal['journal_id'] not in seen_ids:
                            seen_ids.add(journal['journal_id'])
                            journals.append(journal)
                            logger.item(idx, len(items), journal['name'])

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

    @staticmethod
    def parse_pagination(html: str) -> Dict[str, Any]:
        """
        Pagination bilgisini çıkar.

        Önce sayı bazlı count elementiyle, sonra sayfalı nav linkleriyle,
        son olarak "next" butonuyla belirler.

        Returns:
            dict: {current_page, total_pages, total_items, page_size, has_next}
        """
        soup = _soup(html)
        result = {'current_page': 0, 'total_pages': 1, 'total_items': 0, 'page_size': 20, 'has_next': False}

        # Toplam sonuç sayısı — birden fazla olası selector
        count_selectors = [
            '.search-result__count', '.result-count', 'h2.search-title',
            '.publications__count', 'span.result-count', '[class*="result-count"]',
        ]
        for sel in count_selectors:
            count_el = soup.select_one(sel)
            if not count_el:
                continue
            count_text = _clean(count_el.get_text())
            m = re.search(r'([\d,]+)\s*(?:results?|journals?|publications?)', count_text, re.I)
            if not m:
                # "1-20 of 1,847" formatı
                m = re.search(r'of\s+([\d,]+)', count_text, re.I)
            if m:
                result['total_items'] = int(m.group(1).replace(',', ''))
                result['total_pages'] = (result['total_items'] + result['page_size'] - 1) // result['page_size']
                break

        # Pagination nav'ından en yüksek sayfa numarasını bul
        nav = soup.select_one('nav.pagination, ul.pagination, .rlist--inline.pagination')
        if nav:
            active = nav.select_one('li.active, li[aria-current="page"], .active')
            if active:
                try:
                    result['current_page'] = int(re.sub(r'\D', '', _clean(active.get_text()))) - 1
                except Exception:
                    pass

            max_page = 0
            for a in nav.select('a[href]'):
                try:
                    n = int(re.sub(r'\D', '', _clean(a.get_text())))
                    if n > max_page:
                        max_page = n
                except (ValueError, TypeError):
                    pass
            if max_page > result['total_pages']:
                result['total_pages'] = max_page

            # "Next" butonu varlığı
            next_btn = nav.select_one(
                'li.next a, a[aria-label*="next" i], a.pagination__btn--next, '
                'a[rel="next"], li[class*="next"] a'
            )
            if next_btn:
                result['has_next'] = True
                if result['total_pages'] <= 1:
                    result['total_pages'] = result['current_page'] + 2  # en az bir sonraki sayfa

        return result

    # ── Journal Detail (ISSN + Aims & Scope) ─────────────────────────────────

    @staticmethod
    def parse_journal_detail(html: str) -> Dict[str, Any]:
        """
        Journal detay sayfasından ISSN bilgisini çıkar.

        Selector: div.info-block → span.info_value veya meta[name="citation_issn"]

        Returns:
            dict: {issn, eissn}
        """
        soup = _soup(html)
        detail = {'issn': '', 'eissn': ''}

        # info-block içindeki ISSN
        for block in soup.select('div.info-block, .journal-info-block'):
            label = _clean(block.select_one('.info_label, label') and
                           block.select_one('.info_label, label').get_text() or "")
            value_el = block.select_one('.info_value, .value')
            if not value_el:
                continue
            value = _clean(value_el.get_text())
            if 'print issn' in label.lower() or (not detail['issn'] and re.match(r'[\dX]{4}-[\dX]{4}', value)):
                detail['issn'] = value
            elif 'online issn' in label.lower() or 'e-issn' in label.lower():
                detail['eissn'] = value

        # Fallback: <meta> tags
        if not detail['issn']:
            meta = soup.select_one('meta[name="citation_issn"]')
            if meta:
                detail['issn'] = meta.get('content', '')
        if not detail['eissn']:
            meta = soup.select_one('meta[name="citation_eissn"]')
            if meta:
                detail['eissn'] = meta.get('content', '')

        return detail

    @staticmethod
    def parse_aims_and_scope(html: str) -> Optional[str]:
        """
        Aims & Scope sayfasından içerik çıkar.

        URL: /hub/journal/{id}/overview
        Selector: div.pb-rich-text (aims başlığı altındaki tüm paragraflar)
        Alternatif: section.aims-and-scope, .journal-description

        Returns:
            str: HTML içerik veya None
        """
        soup = _soup(html)

        # Birincil: pb-rich-text div'i
        content_el = soup.select_one('div.pb-rich-text, div.aims-and-scope-content')
        if content_el:
            text = _clean(content_el.get_text())
            if len(text) > 50:
                return str(content_el)

        # Alternatif: "Aims and Scope" başlığını bul, altındaki paragraflara bak
        for heading in soup.find_all(['h2', 'h3', 'h4']):
            if 'aims' in heading.get_text().lower() and 'scope' in heading.get_text().lower():
                parts = []
                for sib in heading.find_next_siblings():
                    if sib.name in ['h2', 'h3', 'h4']:
                        break
                    if sib.name in ['p', 'div', 'ul']:
                        parts.append(str(sib))
                if parts:
                    return ''.join(parts)

        # Fallback: journal-description class
        desc_el = soup.select_one('.journal-description, .about-journal')
        if desc_el:
            return str(desc_el)

        return None

    # ── Journal Type Detection ────────────────────────────────────────────────

    @staticmethod
    def detect_journal_type(html: str) -> str:
        """
        Journal tipini tespit et: issue-based mi, article-based mi?

        Issue-based: Navigation menüde "All Issues" linki var (/loi/ prefix)
        Article-based: Navigation menüde "All articles" linki var (/index/ prefix)

        Returns:
            str: "issue_based" | "article_based" | "unknown"
        """
        soup = _soup(html)

        # Tüm navigasyon linklerini tara
        for a in soup.select('nav a, ul#menubar a, .pb-dropzone a'):
            href = a.get('href', '')
            label = _clean(a.get_text()).lower()
            data_label = a.get('data-menu-label', '').lower()

            combined = label + ' ' + data_label
            if '/loi/' in href or 'all issues' in combined:
                return 'issue_based'
            if '/index/' in href or 'all articles' in combined:
                return 'article_based'

        # Sayfa içeriğinde /loi/ veya /index/ bağlantısı ara
        if soup.select_one('a[href*="/loi/"]'):
            return 'issue_based'
        if soup.select_one('a[href*="/index/"]'):
            return 'article_based'

        return 'unknown'

    # ── Issue List ────────────────────────────────────────────────────────────

    @staticmethod
    def parse_issue_list(html: str) -> List[Dict[str, Any]]:
        """
        /loi/{journal_id} sayfasından issue listesini çıkar.

        İki format desteklenir:
        1. ul.loi__list li.nested → decade grupları, yıl/volume linkleri
        2. div.loi--aside → decade bazlı expandable listeler

        Her issue için: url, title, volume, year

        Returns:
            list: [{url, title, volume, year}]
        """
        soup = _soup(html)
        issues = []
        seen_urls = set()

        def add_issue(url: str, title: str):
            if url and url not in seen_urls:
                seen_urls.add(url)
                # /toc/{journal_id}/{year}/{volume}/{issue}
                vol, year, issue_num = '', '', ''
                m = re.search(r'/toc/[^/]+/(\d{4})/(\d+)(?:/(\d+))?', url)
                if m:
                    year = m.group(1)
                    vol = m.group(2)
                    issue_num = m.group(3) or ''
                clean_title = _clean(title)
                # If anchor text doesn't include issue number but URL has one, build a full title
                if issue_num and 'issue' not in clean_title.lower():
                    clean_title = f"Volume {vol}, Issue {issue_num}"
                issues.append({'url': url, 'title': clean_title, 'volume': vol, 'year': year, 'issue_number': issue_num})

        # Format 1: ul.loi__list
        for li in soup.select('ul.loi__list li, ul.loi__issues li'):
            a = li.select_one('a[href*="/toc/"]')
            if a:
                add_issue(a.get('href', ''), a.get_text())

        # Format 2: div.loi--aside / decade-based structure
        if not issues:
            for a in soup.select('a[href*="/toc/"]'):
                add_issue(a.get('href', ''), a.get_text())

        # Format 3: div.card içindeki h4 a linkleri
        if not issues:
            for card in soup.select('div.loi__issue, div.card'):
                a = card.select_one('h4 a[href*="/toc/"], h3 a[href*="/toc/"]')
                if a:
                    add_issue(a.get('href', ''), a.get_text())

        logger.info(f"Issue listesi: {len(issues)} issue bulundu")
        return issues

    @staticmethod
    def get_expandable_decade_selectors(html: str) -> List[Dict[str, str]]:
        """
        LOI sayfasındaki kapalı decade/yıl bölümlerinin CSS seçicilerini döndür.
        Scraper bu seçicileri tıklayarak AJAX içeriği yükler.

        Returns:
            list: [{selector, label}]
        """
        soup = _soup(html)
        sections = []
        for a in soup.select('a[data-menu-label], a.loi__decade, a[aria-expanded="false"]'):
            href = a.get('href', '') or a.get('data-url', '')
            if href:
                selector = f'a[href="{href}"]'
                sections.append({'selector': selector, 'label': _clean(a.get_text()), 'href': href})
        return sections

    # ── Article List (Issue ToC) ──────────────────────────────────────────────

    @staticmethod
    def parse_article_list_from_toc(html: str) -> List[Dict[str, Any]]:
        """
        Issue ToC sayfasından makale listesini çıkar.

        Selector: div.issue-items-container div.issue-item
        Full Text filtresi: ul.issue-item__links li a[title*="Full text"] varlığı

        Returns:
            list: [{title, doi, doi_url, authors, pub_date, access_type, has_full_text}]
        """
        try:
            soup = _soup(html)
            articles = []

            items = soup.select(
                'div.issue-item, li.issue-item, '
                'ul#search-result > li, li.search__item, li.bulkDownloadWrapper'
            )
            logger.found(len(items), "item")

            for idx, item in enumerate(items, 1):
                try:
                    art = {}

                    # Başlık
                    title_el = item.select_one(
                        'a.issue-item__title h2, h2.issue-item__title a, .issue-item__title, '
                        'h2.meta__title a.publication_title, span.hlFld-Title a.publication_title, '
                        'h2.meta__title a[href*="/doi/"]'
                    )
                    if not title_el:
                        continue
                    art['title'] = _clean(title_el.get_text())

                    # DOI / URL
                    doi_input = item.select_one(
                        '.bulkDownloadInput input[value], '
                        'input.bulkDownloadInput, input[name*="doi" i], '
                        'input[type="hidden"][value^="10."]'
                    )
                    doi_link = item.select_one('a[href*="/doi/"]')
                    if doi_input:
                        raw_doi = doi_input.get('value', '')
                        import urllib.parse
                        decoded_doi = urllib.parse.unquote(raw_doi).strip()
                        art['doi'] = decoded_doi
                        art['doi_url'] = f"/doi/full/{decoded_doi}" if decoded_doi else ''
                    elif doi_link:
                        href = doi_link.get('href', '')
                        m = re.search(r'/doi/(?:full|abs|epdf)?/?(10\.[^\s?#"\']+)', href)
                        if m:
                            art['doi'] = m.group(1)
                            art['doi_url'] = f"/doi/full/{art['doi']}"
                        else:
                            art['doi'] = ''
                            art['doi_url'] = href
                    else:
                        art['doi'] = ''
                        art['doi_url'] = ''

                    # Full Text kontrolü (makale filtresi)
                    full_text_link = item.select_one(
                        'a[title*="Full text"], a[aria-label*="Full Text"], '
                        'a[class*="full-text"], li.pdf-link a, a[href*="/doi/full/"]'
                    )
                    art['has_full_text'] = full_text_link is not None

                    # Yazarlar
                    art['authors'] = []
                    for author_el in item.select('.comma__item a, span.author-style, .loa span a'):
                        name = _clean(author_el.get_text())
                        if name:
                            art['authors'].append(name)

                    # Yayın tarihi
                    date_el = item.select_one('li.ePubDate span:last-child, .pub-date, time, p.meta__epubDate, .meta__epubDate')
                    art['pub_date'] = _clean(date_el.get_text()) if date_el else ''

                    # Erişim tipi
                    access_el = item.select_one('div.access-type, span.access-type')
                    art['access_type'] = _clean(access_el.get_text()) if access_el else ''

                    if art['title']:
                        articles.append(art)
                        logger.info(f"  {len(articles)}. {art['title'][:60]}")

                except Exception as e:
                    logger.warning(f"Makale listesi parse hatası: {e}")
                    continue

            logger.found(len(articles), "makale URL'i")
            return articles

        except Exception as e:
            logger.failed("Makale URL çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return []

    @staticmethod
    def parse_article_list_from_index(html: str) -> List[Dict[str, Any]]:
        """
        Article-based journal /index/ sayfasından makale listesi çıkar.
        Aynı parse mantığı, ToC ile ortak selector'lar.
        """
        return JournalParser.parse_article_list_from_toc(html)


# ══════════════════════════════════════════════════════════════════════════════
# ARTICLE PARSER
# ══════════════════════════════════════════════════════════════════════════════

class ArticleParser:
    """Wiley makale detay sayfasını parse eder."""

    @staticmethod
    def parse_article_detail(html: str, url: str = '') -> Dict[str, Any]:
        """
        /doi/full/{doi} sayfasından tüm metadata'yı çıkar.

        Returns:
            dict: {title, doi, authors, abstract, pub_date, article_type,
                   keywords, references, full_text, sections, url}
        """
        try:
            soup = _soup(html)
            article = {'url': url}

            # ── Başlık ────────────────────────────────────────────────────────────
            logger.info("Başlık alınıyor...")
            title_el = soup.select_one('h1.citation__title, h1.article-title, h1[class*="title"]')
            article['title'] = _clean(title_el.get_text()) if title_el else ''
            if article['title']:
                logger.success(f"Başlık: {article['title'][:60]}...")
            else:
                logger.warning("Başlık bulunamadı")

            # ── DOI ───────────────────────────────────────────────────────────────
            logger.info("DOI alınıyor...")
            doi_el = soup.select_one('a.epub-doi, a[href*="doi.org"]')
            if doi_el:
                href = doi_el.get('href', doi_el.get_text())
                m = re.search(r'10\.\d{4,}[^\s"<]+', href)
                article['doi'] = m.group(0) if m else _clean(doi_el.get_text())
            else:
                m = re.search(r'/doi/(?:full|abs)/(10\.[^\s?#]+)', url)
                article['doi'] = m.group(1) if m else ''
            if article['doi']:
                logger.success(f"DOI: {article['doi']}")
            else:
                logger.warning("DOI bulunamadı")

            # ── Makale Tipi ───────────────────────────────────────────────────────
            type_el = soup.select_one('span.primary-heading, .article-type, .article__type')
            article['article_type'] = _clean(type_el.get_text()) if type_el else ''

            # ── Yazarlar ─────────────────────────────────────────────────────────
            logger.info("Yazarlar alınıyor...")
            article['authors'] = ArticleParser._parse_authors(soup)
            if article['authors']:
                logger.found(len(article['authors']), "yazar")
            else:
                logger.warning("Yazar bilgisi bulunamadı")

            # ── Yayın Tarihi ──────────────────────────────────────────────────────
            logger.info("Yayın tarihi alınıyor...")
            date_el = soup.select_one('span.epub-date, time.epub-date, .citation__top__dates')
            article['pub_date'] = _clean(date_el.get_text()) if date_el else ''
            if article['pub_date']:
                logger.success(f"Yayın tarihi: {article['pub_date']}")
            else:
                logger.warning("Yayın tarihi bulunamadı")

            # ── Abstract ─────────────────────────────────────────────────────────
            logger.info("Abstract alınıyor...")
            abstract_el = soup.select_one(
                'section.article-section__abstract div.article-section__content, '
                'div.abstract-group p, div[class*="abstract"] p'
            )
            if abstract_el:
                article['abstract'] = _clean(abstract_el.get_text())
            else:
                abstract_section = soup.select_one('section[class*="abstract"]')
                article['abstract'] = _clean(abstract_section.get_text()) if abstract_section else ''
            if article['abstract']:
                logger.success(f"Abstract alındı ({len(article['abstract'])} karakter)")
            else:
                logger.warning("Abstract bulunamadı")

            # ── Anahtar Kelimeler ─────────────────────────────────────────────────
            logger.info("Anahtar kelimeler alınıyor...")
            article['keywords'] = []
            for kw_el in soup.select('a.keyword, li.keywords-section__keyword a, .kwd-group a'):
                kw = _clean(kw_el.get_text())
                if kw and kw not in article['keywords']:
                    article['keywords'].append(kw)
            if article['keywords']:
                logger.found(len(article['keywords']), "anahtar kelime")
            else:
                logger.warning("Anahtar kelime bulunamadı")

            # ── Bölüm Başlıkları ─────────────────────────────────────────────────
            article['sections'] = []
            for h in soup.select('section.article-section__full h2, section.article-section__content h2'):
                title = _clean(h.get_text())
                if title and title not in article['sections']:
                    article['sections'].append(title)
            if article['sections']:
                logger.info(f"Bölümler ({len(article['sections'])}): {article['sections'][:4]}")

            # ── Tam Metin ─────────────────────────────────────────────────────────
            logger.info("Tam metin alınıyor...")
            article['full_text'] = ''
            full_text_el = soup.select_one('section.article-section__full, div.article__body')
            if full_text_el:
                parts = []
                for el in full_text_el.select('p, h2, h3, h4'):
                    text = _clean(el.get_text())
                    if text:
                        parts.append(text)
                article['full_text'] = '\n\n'.join(parts)
            if article['full_text']:
                logger.success(f"Tam metin alındı ({len(article['full_text'])} karakter)")
            else:
                logger.warning("Tam metin bulunamadı")

            # ── Referanslar ───────────────────────────────────────────────────────
            logger.info("Referanslar alınıyor...")
            article['references'] = ArticleParser._parse_references(soup)
            if article['references']:
                logger.found(len(article['references']), "referans")
            else:
                logger.warning("Referans bulunamadı")

            logger.success(
                f"Meta özet: DOI={bool(article['doi'])}, "
                f"Tarih={bool(article['pub_date'])}, "
                f"Yazarlar={len(article['authors'])}, "
                f"Abstract={bool(article['abstract'])}, "
                f"Anahtar={len(article['keywords'])}"
            )

            return article

        except Exception as e:
            logger.failed("Makale detay çıkarma hatası", e)
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _parse_authors(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Yazar listesini parse et.

        Selector: div.article-citation a.author-name (popup ve Related bölümü hariç)
        Her yazar için: name, email, affiliation, is_corresponding
        """
        authors = []
        seen = set()

        # Yalnızca makale başlık/alıntı bölümünde ara — Related/sidebar paneli hariç tutar
        search_root = soup.select_one('div.article-citation') or soup

        for author_el in search_root.select('a.author-name'):
            # author-info popup'ı içindeki linkleri atla (email, orcid, moreInfoLink)
            if author_el.find_parent(class_='author-info'):
                continue

            name = _clean(author_el.get_text())
            if not name or name in seen:
                continue
            seen.add(name)

            author = {'name': name, 'email': '', 'affiliation': '', 'is_corresponding': False}

            # Yazara ait accordion container'ı bul
            container = (
                author_el.find_parent(class_='accordion-tabbed__tab-mobile')
                or author_el.find_parent(class_='accordion-tabbed')
            )
            if container:
                info_div = container.select_one('div.author-info')
                if info_div:
                    # Corresponding flag
                    author_type_el = info_div.select_one('p.author-type')
                    if author_type_el and 'corresponding' in author_type_el.get_text().lower():
                        author['is_corresponding'] = True

                    # Email
                    email_el = info_div.select_one('a[href^="mailto:"]')
                    if email_el:
                        author['email'] = email_el.get('href', '').replace('mailto:', '')

                    # Kurum bilgisi (author-type/author-name paragrafları ve yazışma/email satırları hariç)
                    aff_parts = []
                    for p in info_div.select('p'):
                        if any(c in p.get('class', []) for c in ['author-type', 'author-name']):
                            continue
                        text = _clean(p.get_text())
                        if text and not text.startswith('Correspondence') and '@' not in text:
                            aff_parts.append(text)
                    if aff_parts:
                        author['affiliation'] = '; '.join(aff_parts)

            authors.append(author)

        return authors

    @staticmethod
    def _parse_references(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Referans listesini parse et.

        Selector: section#references-section li[data-bib-id]
        (draft.md satır 4250+ yapısı)
        """
        refs = []

        ref_section = soup.select_one('section#references-section, section[id*="reference"], div.references')
        if not ref_section:
            return refs

        for li in ref_section.select('li[data-bib-id], li.reference'):
            try:
                ref = {}

                # Numara
                bullet = li.select_one('span.bullet')
                ref['index'] = _clean(bullet.get_text()) if bullet else ''

                # Yazarlar
                authors = [_clean(a.get_text()) for a in li.select('span.author')]
                ref['authors'] = ', '.join(authors)

                # Dergi adı
                journal_el = li.select_one('i.journalTitle, i[class*="journal"]')
                ref['journal'] = _clean(journal_el.get_text()) if journal_el else ''

                # Cilt
                vol_el = li.select_one('span.vol')
                ref['volume'] = _clean(vol_el.get_text()) if vol_el else ''

                # Yıl
                year_el = li.select_one('span.pubYear')
                ref['year'] = _clean(year_el.get_text()) if year_el else ''

                # Sayfa
                page_el = li.select_one('span.pageFirst')
                ref['pages'] = _clean(page_el.get_text()) if page_el else ''

                # DOI
                doi_el = li.select_one('span.hidden.data-doi, .data-doi')
                ref['doi'] = _clean(doi_el.get_text()) if doi_el else ''

                # Tam metin
                ref['raw'] = _clean(li.get_text())

                refs.append(ref)
            except Exception as e:
                logger.warning(f"Referans parse hatası: {e}")
                continue

        return refs

    @staticmethod
    def extract_journal_name_from_article(html: str) -> str:
        """Makale sayfasından dergi adını çıkar (resolve_name_from_url için)"""
        soup = _soup(html)
        el = soup.select_one('a.publication__title, .citation__top__info a, meta[name="citation_journal_title"]')
        if el:
            return _clean(el.get('content', '') or el.get_text())
        return ''
