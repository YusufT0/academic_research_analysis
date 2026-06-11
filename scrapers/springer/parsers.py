"""HTML parsers for Springer scraper."""

import re
import sys
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

sys.path.insert(0, str(__file__).rsplit("springer", 1)[0])
from utils.logger import get_logger

logger = get_logger("springer")

BASE_URL = "https://link.springer.com"
FILTER_KEYWORDS = [
    "editorial",
    "book review",
    "news section",
    "erratum",
    "correction",
    "retraction",
    "preface",
    "foreword",
    "acknowledgement",
]


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _clean(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return f"{BASE_URL}{href}"


class JournalListParser:
    @staticmethod
    def parse_journals(html: str) -> List[Dict[str, Any]]:
        soup = _soup(html)
        journals: List[Dict[str, Any]] = []
        seen = set()

        for card in soup.select('li[data-test="journal-card"]'):
            title_el = card.select_one("h2.app-card-open__heading a")
            if not title_el:
                continue

            name = _clean(title_el.get_text())
            href = title_el.get("href", "")
            url = _abs_url(href)
            m = re.search(r"/journal/(\d+)", url)
            journal_id = m.group(1) if m else ""
            if not name or not url or not journal_id or journal_id in seen:
                continue

            metadata = {}
            labels = card.select("dl.app-card-open__metadata-list dt")
            values = card.select("dl.app-card-open__metadata-list dd")
            for dt, dd in zip(labels, values):
                key = _clean(dt.get_text()).lower().replace(" ", "_")
                metadata[key] = _clean(dd.get_text())

            journals.append(
                {
                    "name": name,
                    "url": url,
                    "journal_id": journal_id,
                    "description": _clean((card.select_one('p[data-test="description"]') or {}).get_text() if card.select_one('p[data-test="description"]') else ""),
                    "publication_model": metadata.get("publication_model", ""),
                    "impact_factor": metadata.get("impact_factor", ""),
                    "downloads": metadata.get("downloads", ""),
                    "open_access": "open" in metadata.get("publication_model", "").lower(),
                }
            )
            seen.add(journal_id)

        return journals

    @staticmethod
    def parse_pagination(html: str) -> Dict[str, Any]:
        soup = _soup(html)
        current_page = 1
        total_pages = 1

        nav = soup.select_one('div[data-test="brand-pagination"] nav[aria-label]')
        if nav:
            label = nav.get("aria-label", "")
            m = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", label, re.I)
            if m:
                current_page = int(m.group(1))
                total_pages = int(m.group(2))

        next_a = soup.select_one('li.eds-c-pagination__item--next a[href]')
        next_url = _abs_url(next_a.get("href", "")) if next_a else None
        return {
            "current_page": current_page,
            "total_pages": total_pages,
            "has_next": bool(next_url),
            "next_page_url": next_url,
        }


class JournalDetailParser:
    @staticmethod
    def parse_issn(html: str) -> Dict[str, str]:
        soup = _soup(html)
        return {
            "eissn": _clean(
                (soup.select_one('div[data-test="springer-electronic-issn"] dd.c-list-description__details') or {}).get_text()
                if soup.select_one('div[data-test="springer-electronic-issn"] dd.c-list-description__details')
                else ""
            ),
            "issn": _clean(
                (soup.select_one('div[data-test="springer-print-issn"] dd.c-list-description__details') or {}).get_text()
                if soup.select_one('div[data-test="springer-print-issn"] dd.c-list-description__details')
                else ""
            ),
        }


class AimsAndScopeParser:
    @staticmethod
    def parse_text(html: str) -> str:
        soup = _soup(html)
        holder = soup.select_one('div[data-test="aimsAndScope-placeholder-div"]')
        return _clean(holder.get_text(" ")) if holder else ""


class VolumesAndIssuesParser:
    @staticmethod
    def parse_issues(html: str) -> List[Dict[str, Any]]:
        soup = _soup(html)
        issues: List[Dict[str, Any]] = []

        for container in soup.select("li.app-vol-and-issues-item"):
            volume_name = _clean(
                (container.select_one("h2.eds-c-section-heading span:first-child") or {}).get_text()
                if container.select_one("h2.eds-c-section-heading span:first-child")
                else ""
            )
            for a in container.select("li.c-list-group__item a.c-list-group__link"):
                href = a.get("href", "")
                issue_text = _clean(a.get_text())
                time_el = a.select_one("time[datetime]")
                issue_date = time_el.get("datetime", "") if time_el else ""
                issues.append(
                    {
                        "url": _abs_url(href),
                        "title": issue_text,
                        "issue_number": issue_text,
                        "date": issue_date,
                        "volume": volume_name,
                        "year": issue_date[:4] if len(issue_date) >= 4 else "",
                    }
                )
        return issues


class ArticleListParser:
    @staticmethod
    def should_filter(title: str) -> bool:
        lowered = (title or "").lower()
        return any(k in lowered for k in FILTER_KEYWORDS)

    @staticmethod
    def parse_articles(html: str) -> List[Dict[str, Any]]:
        soup = _soup(html)
        articles: List[Dict[str, Any]] = []

        cards = soup.select('section[data-test="article-listing"] ol li article.app-card-open')
        for card in cards:
            title_el = card.select_one("h2.app-card-open__heading a")
            if not title_el:
                continue

            title = _clean(title_el.get_text())
            if ArticleListParser.should_filter(title):
                continue

            url = _abs_url(title_el.get("href", ""))
            doi_match = re.search(r"/article/(.+)$", url)
            doi = doi_match.group(1) if doi_match else ""

            authors = []
            for a in card.select("div.app-card-open__authors ul.app-author-list li"):
                n = _clean(a.get_text())
                if n:
                    authors.append(n)

            article_type = _clean((card.select_one("span.c-meta__type") or {}).get_text() if card.select_one("span.c-meta__type") else "")

            meta_items = [_clean(x.get_text()) for x in card.select("span.c-meta__item")]
            is_open_access = any("open access" in x.lower() for x in meta_items)
            publication_date = ""
            for item in meta_items:
                if re.search(r"\d{4}", item):
                    publication_date = item
                    break

            articles.append(
                {
                    "title": title,
                    "url": url,
                    "doi": doi,
                    "authors": authors,
                    "article_type": article_type,
                    "is_open_access": is_open_access,
                    "pub_date": publication_date,
                }
            )

        return articles

    @staticmethod
    def parse_pagination(html: str) -> Dict[str, Any]:
        soup = _soup(html)
        pagination = soup.select_one("div.eds-c-pagination")
        if not pagination:
            return {"has_next": False, "next_page_url": None}

        next_a = pagination.select_one('li.eds-c-pagination__item--next a[href]')
        next_url = _abs_url(next_a.get("href", "")) if next_a else None
        return {"has_next": bool(next_url), "next_page_url": next_url}


class ArticleDetailParser:
    @staticmethod
    def parse_article_detail(html: str, url: str = "") -> Dict[str, Any]:
        soup = _soup(html)

        title = _clean(
            (soup.select_one('h1.c-article-title[data-test="article-title"]') or {}).get_text()
            if soup.select_one('h1.c-article-title[data-test="article-title"]')
            else ""
        )
        article_type = _clean((soup.select_one('li[data-test="article-category"]') or {}).get_text() if soup.select_one('li[data-test="article-category"]') else "")
        is_open_access = soup.select_one('a[data-test="open-access"]') is not None

        date_el = soup.select_one("ul.c-article-identifiers time[datetime]")
        pub_date = date_el.get("datetime", "") if date_el else ""

        publication_year = _clean((soup.select_one('span[data-test="article-publication-year"]') or {}).get_text() if soup.select_one('span[data-test="article-publication-year"]') else "")
        journal_volume = _clean((soup.select_one('span[data-test="journal-volume"]') or {}).get_text() if soup.select_one('span[data-test="journal-volume"]') else "")

        pdf_a = soup.select_one('a[data-test="pdf-link"][href]')
        pdf_url = _abs_url(pdf_a.get("href", "")) if pdf_a else ""

        doi = ""
        from_url = re.search(r"/article/(.+)$", url)
        if from_url:
            doi = from_url.group(1)
        if not doi:
            biblio_text = " ".join(_clean(x.get_text()) for x in soup.select(".c-bibliographic-information__value"))
            m = re.search(r"doi\.org/(10\.[^\s]+)", biblio_text, re.I)
            if m:
                doi = m.group(1)

        authors = []
        for a in soup.select('ul[data-test="authors-list"] li a[data-test="author-name"]'):
            n = _clean(a.get_text())
            if n:
                authors.append({"name": n})

        abstract_parts = []
        for p in soup.select('section[data-title="Abstract"] .c-article-section__content p'):
            t = _clean(p.get_text())
            if t:
                abstract_parts.append(t)

        keywords = []
        for a in soup.select("ul.c-article-subject-list li.c-article-subject-list__subject a"):
            kw = _clean(a.get_text())
            if kw:
                keywords.append(kw)

        citations = 0
        cit_text = _clean((soup.select_one('li[data-test="citation-count"] p.app-article-metrics-bar__count') or {}).get_text() if soup.select_one('li[data-test="citation-count"] p.app-article-metrics-bar__count') else "")
        m = re.search(r"(\d+)", cit_text)
        if m:
            citations = int(m.group(1))

        references = []
        ref_section = soup.select_one('section[data-title="References"], section#references-section')
        if ref_section:
            for li in ref_section.select("li"):
                t = _clean(li.get_text())
                if t:
                    references.append(t)

        return {
            "title": title,
            "url": url,
            "doi": doi,
            "authors": authors,
            "abstract": "\n\n".join(abstract_parts),
            "pub_date": pub_date,
            "publication_year": publication_year,
            "volume_issue": journal_volume,
            "article_type": article_type,
            "keywords": keywords,
            "references": references,
            "citation_count": citations,
            "is_open_access": is_open_access,
            "pdf_url": pdf_url,
            "full_text": "",
            "sections": [],
        }

    @staticmethod
    def extract_journal_name_from_article(html: str) -> str:
        soup = _soup(html)
        el = soup.select_one('a[data-track-action="Journal title"]')
        if not el:
            el = soup.select_one('meta[name="citation_journal_title"]')
            if el:
                return _clean(el.get("content", ""))
        return _clean(el.get_text()) if el else ""


class JournalParser:
    """Compatibility wrapper used by scraper manager flow."""

    @staticmethod
    def parse_journal_list(html: str) -> List[Dict[str, Any]]:
        return JournalListParser.parse_journals(html)

    @staticmethod
    def parse_pagination(html: str) -> Dict[str, Any]:
        return JournalListParser.parse_pagination(html)

    @staticmethod
    def parse_journal_detail(html: str) -> Dict[str, Any]:
        return JournalDetailParser.parse_issn(html)

    @staticmethod
    def parse_aims_and_scope(html: str) -> Optional[str]:
        text = AimsAndScopeParser.parse_text(html)
        return text or None

    @staticmethod
    def detect_journal_type(html: str) -> str:
        soup = _soup(html)
        if soup.select_one('a[href*="/volumes-and-issues"]'):
            return "issue_based"
        return "unknown"

    @staticmethod
    def parse_issue_list(html: str) -> List[Dict[str, Any]]:
        return VolumesAndIssuesParser.parse_issues(html)

    @staticmethod
    def get_expandable_decade_selectors(html: str) -> List[Dict[str, str]]:
        _ = html
        return []

    @staticmethod
    def parse_article_list_from_toc(html: str) -> List[Dict[str, Any]]:
        return ArticleListParser.parse_articles(html)

    @staticmethod
    def parse_article_list_from_index(html: str) -> List[Dict[str, Any]]:
        return ArticleListParser.parse_articles(html)


class ArticleParser:
    """Compatibility wrapper used by scraper manager flow."""

    @staticmethod
    def parse_article_detail(html: str, url: str = "") -> Dict[str, Any]:
        return ArticleDetailParser.parse_article_detail(html, url)

    @staticmethod
    def extract_journal_name_from_article(html: str) -> str:
        return ArticleDetailParser.extract_journal_name_from_article(html)
