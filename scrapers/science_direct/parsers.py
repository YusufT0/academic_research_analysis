"""
HTML parsing functions for Science Direct scraper
"""

from bs4 import BeautifulSoup


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
            print("\n📄 Sayfa taranıyor...")
            
            # BeautifulSoup ile parse et (çok daha hızlı)
            print("  → HTML parse ediliyor...")
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Publications list'i bul
            publication_list = soup.find('ul', class_='publications-list')
            if not publication_list:
                print("  ✗ publications-list bulunamadı")
                return []
            
            # Tüm div elementlerini al (her div bir harf grubu)
            letter_divs = publication_list.find_all('div', recursive=False)
            print(f"  ✓ {len(letter_divs)} adet harf grubu bulundu")
            
            journals = []
            
            for div in letter_divs:
                try:
                    # Harf başlığını al
                    letter_title = div.find('h2', class_='alphabet-heading')
                    current_letter = letter_title.get_text(strip=True) if letter_title else 'Unknown'
                    print(f"\n  📚 Harf grubu: {current_letter}")
                    
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
                    print(f"  ⚠ Harf grubu parse hatası: {e}")
                    continue
            
            print(f"\n✓ {len(journals)} journal bulundu (parse süresi: <1s)")
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
        Journal sayfasındaki 'latest-published-articles' div'inden makale URL'lerini çıkarır
        
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
                print(f"  ⚠ 'latest-published-articles' div'i bulunamadı")
                return []
            
            # Tüm article item'ları bul
            article_items = latest_articles_div.find_all('div', class_='js-article-item')
            print(f"  ✓ {len(article_items)} article item bulundu")
            
            article_urls = []
            
            for idx, item in enumerate(article_items, 1):
                try:
                    # Article title link'ini bul
                    title_link = item.find('a', class_='js-article__item__title__link')
                    
                    if title_link and title_link.get('href'):
                        article_url = title_link['href']
                        article_urls.append(article_url)
                        print(f"  {idx}. {article_url}")
                    
                except Exception as e:
                    print(f"  ⚠ Article {idx} parse hatası: {e}")
                    continue
            
            print(f"  ✓ Toplam {len(article_urls)} makale URL'i bulundu")
            return article_urls
            
        except Exception as e:
            print(f"  ✗ Latest articles çıkarma hatası: {e}")
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
            print(f"  → Başlık alınıyor...")
            title_span = soup.find('span', class_='title-text')
            if title_span:
                article_details['title'] = title_span.get_text(strip=True)
                print(f"  ✓ Başlık: {article_details['title'][:50]}...")
            else:
                print(f"  ⚠ Başlık bulunamadı")
            
            # 2. PDF URL'ini al
            print(f"  → PDF linki aranıyor...")
            pdf_link = soup.find('a', class_='link-button', attrs={'aria-label': lambda x: x and 'View PDF' in x})
            if not pdf_link:
                # Alternatif selektör
                pdf_link = soup.find('a', href=lambda x: x and 'pdfft' in x)
            
            if pdf_link and pdf_link.get('href'):
                article_details['pdf_url'] = pdf_link['href']
                print(f"  ✓ PDF URL: {article_details['pdf_url']}")
            else:
                print(f"  ⚠ PDF linki bulunamadı")
            
            # 3. Yazarları al
            print(f"  → Yazarlar alınıyor...")
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
                
                print(f"  ✓ {len(article_details['authors'])} yazar bulundu: {', '.join(article_details['authors'][:3])}{'...' if len(article_details['authors']) > 3 else ''}")
            else:
                print(f"  ⚠ Yazar bilgisi bulunamadı")
            
            # 4. DOI al
            print(f"  → DOI aranıyor...")
            doi_link = soup.find('a', class_='doi')
            
            if doi_link:
                doi_text = doi_link.get_text(strip=True)
                article_details['doi'] = doi_text
                print(f"  ✓ DOI: {doi_text}")
            else:
                print(f"  ⚠ DOI bulunamadı")
            
            # 5. Publication Date, Pages, Publisher al
            print(f"  → Meta bilgiler alınıyor...")
            
            # Publication Date - volume-issue-info veya article-dates alanlarından
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
            
            print(f"  ✓ Meta: Date={bool(article_details['publication_date'])}, Pages={bool(article_details['pages'])}")
            
            # 6. Abstract al
            print(f"  → Abstract alınıyor...")
            article_details['abstract'] = ArticleParser._extract_abstract(soup)
            
            if article_details['abstract']:
                print(f"  ✓ Abstract alındı ({len(article_details['abstract'])} karakter)")
            else:
                print(f"  ⚠ Abstract bulunamadı")
            
            # 7. Introduction (Giriş bölümü) al
            print(f"  → Introduction alınıyor...")
            article_details['introduction'] = ArticleParser._extract_introduction(soup)
            
            if article_details['introduction']:
                print(f"  ✓ Introduction alındı ({len(article_details['introduction'])} karakter)")
            else:
                print(f"  ⚠ Introduction bulunamadı")
            
            return article_details
            
        except Exception as e:
            print(f"  ✗ Makale detay çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
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
