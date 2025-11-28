"""
HTML parsing functions for IEEE Xplore scraper
"""

from bs4 import BeautifulSoup


class JournalParser:
    """Journal bilgilerini parse eden sınıf"""
    
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
            print("\n📄 Sayfa taranıyor...")
            
            # BeautifulSoup ile parse et
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Ana results container'ı bul
            results_div = soup.find('div', class_='ng-SearchResults')
            if not results_div:
                print("  ✗ ng-SearchResults div'i bulunamadı")
                return []
            
            # xpl-browse-results-list içindeki tüm journal item'larını bul
            browse_results = results_div.find('xpl-browse-results-list')
            if not browse_results:
                print("  ✗ xpl-browse-results-list bulunamadı")
                return []
            
            # Tüm journal item'larını bul (xpl-browse-results-item)
            journal_items = browse_results.find_all('xpl-browse-results-item')
            print(f"  ✓ {len(journal_items)} adet journal bulundu")
            
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
                        print(f"  {idx}. {journal_name}")
                        print(f"     → Publisher: {publisher}, Years: {years}")
                        print(f"     → Most Recent Issue: {most_recent_issue_url}")
                    else:
                        print(f"  {idx}. {journal_name} (Most Recent Issue linki yok)")
                    
                except Exception as e:
                    print(f"  ⚠ Journal {idx} parse hatası: {e}")
                    continue
            
            print(f"\n✓ Toplam {len(journals)} journal bulundu")
            return journals
            
        except Exception as e:
            print(f"✗ Journal çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return []


class ArticleParser:
    """Makale bilgilerini parse eden sınıf"""
    
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
                print(f"  ⚠ Makale item'ları bulunamadı")
                return []
            
            print(f"  ✓ {len(result_items)} adet item bulundu")
            
            article_urls = []
            
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
                            article_urls.append(article_url)
                            print(f"  {len(article_urls)}. {article_url}")
                    
                except Exception as e:
                    continue
            
            print(f"  ✓ Toplam {len(article_urls)} makale URL'i bulundu")
            return article_urls
            
        except Exception as e:
            print(f"  ✗ Makale URL çıkarma hatası: {e}")
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
            print(f"  → Başlık alınıyor...")
            title_h1 = soup.find('h1', class_='document-title')
            if title_h1:
                title_span = title_h1.find('span')
                if title_span:
                    article_details['title'] = title_span.get_text(strip=True)
                    print(f"  ✓ Başlık: {article_details['title'][:50]}...")
            
            # 2. PDF URL'ini al
            print(f"  → PDF linki aranıyor...")
            pdf_link = soup.find('a', class_='xpl-btn-pdf')
            if pdf_link and pdf_link.get('href'):
                article_details['pdf_url'] = pdf_link['href']
                print(f"  ✓ PDF URL bulundu")
            else:
                print(f"  ⚠ PDF linki bulunamadı")
            
            # 3. Yazarları al
            print(f"  → Yazarlar alınıyor...")
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
                
                print(f"  ✓ {len(article_details['authors'])} yazar bulundu")
            else:
                print(f"  ⚠ Yazar bilgisi bulunamadı")
            
            # 4. DOI, Publication Date, Pages, Publisher al
            print(f"  → Makale meta bilgileri alınıyor...")
            
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
                    article_details['publication_date'] = pubdate.split('Help')[0].strip() if 'Help' in pubdate else pubdate
            
            # Publisher
            publisher_span = soup.find('xpl-publisher')
            if publisher_span:
                publisher_text = publisher_span.get_text(strip=True)
                publisher = publisher_text.replace('Publisher:', '').strip()
                article_details['publisher'] = publisher
            
            print(f"  ✓ Meta bilgiler: DOI={bool(article_details['doi'])}, Date={bool(article_details['publication_date'])}, Pages={bool(article_details['pages'])}")
            
            # 5. Abstract al
            print(f"  → Abstract alınıyor...")
            abstract_div = soup.find('div', class_='abstract-text')
            if abstract_div:
                # h2 başlığını kaldır
                for h2 in abstract_div.find_all('h2'):
                    h2.decompose()
                
                abstract_content_div = abstract_div.find('div', {'xplmathjax': ''})
                if abstract_content_div:
                    article_details['abstract'] = abstract_content_div.get_text(strip=True)
                    print(f"  ✓ Abstract alındı ({len(article_details['abstract'])} karakter)")
                else:
                    print(f"  ⚠ Abstract içeriği bulunamadı")
            else:
                print(f"  ⚠ Abstract div'i bulunamadı")
            
            # 6. Introduction (Section I) al
            print(f"  → Introduction alınıyor...")
            section_divs = soup.find_all('div', class_='section')
            for section in section_divs:
                section_id = section.get('id', '')
                
                # "sec1" veya "Introduction" içeren section'ı bul
                if 'sec1' in section_id.lower() or section.find('h2', string=lambda x: x and 'Introduction' in x):
                    # Section başlığını ve içeriğini al
                    section_text = section.get_text(separator='\n', strip=True)
                    article_details['introduction'] = section_text
                    print(f"  ✓ Introduction alındı ({len(article_details['introduction'])} karakter)")
                    break
            
            if not article_details['introduction']:
                print(f"  ⚠ Introduction bulunamadı")
            
            return article_details
            
        except Exception as e:
            print(f"  ✗ Makale detay çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
