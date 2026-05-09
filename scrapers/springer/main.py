"""Standalone entry point for Springer scraper."""

import json

from springer.scraper import SpringerScraper


if __name__ == "__main__":
    scraper = SpringerScraper(headless=True)
    try:
        scraper.initialize()
        if not scraper.navigate_to_journals():
            raise RuntimeError("Journals page could not be opened")

        journals = scraper.scrape_all_journals()
        preview = journals[:5]
        print(json.dumps({"count": len(journals), "preview": preview}, ensure_ascii=False, indent=2))
    finally:
        scraper.close()
