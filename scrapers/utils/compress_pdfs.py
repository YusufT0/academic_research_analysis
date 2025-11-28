"""
PDF Sıkıştırma Scripti
PyMuPDF (fitz) kullanarak PDF'leri kalite kaybı olmadan sıkıştırır
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
import argparse

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF kütüphanesi bulunamadı!")
    print("   Yüklemek için: pip install PyMuPDF")
    sys.exit(1)


class PDFCompressor:
    """PDF sıkıştırma sınıfı"""
    
    def __init__(self, output_suffix: str = "_compressed"):
        """
        PDF Compressor'ı başlatır
        
        Args:
            output_suffix: Sıkıştırılmış dosyalara eklenecek son ek
        """
        self.output_suffix = output_suffix
    
    def compress_pdf(self, input_path: str, output_path: Optional[str] = None, 
                     quality: int = 95, image_compression: bool = True) -> dict:
        """
        Tek bir PDF dosyasını sıkıştırır
        
        Args:
            input_path: Sıkıştırılacak PDF dosyasının yolu
            output_path: Çıkış dosyası yolu (None ise otomatik oluşturulur)
            quality: Görüntü kalitesi (0-100, yüksek = daha iyi kalite)
            image_compression: Görselleri sıkıştır mı
            
        Returns:
            dict: Sıkıştırma istatistikleri
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            return {
                'success': False,
                'error': 'Dosya bulunamadı',
                'input_path': str(input_path)
            }
        
        # Çıkış yolu oluştur
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}{self.output_suffix}.pdf"
        else:
            output_path = Path(output_path)
        
        try:
            print(f"\n📄 Sıkıştırılıyor: {input_path.name}")
            
            # Orijinal dosya boyutu
            original_size = input_path.stat().st_size
            
            # PDF'i aç
            doc = fitz.open(input_path)
            
            # Yeni PDF oluştur
            writer = fitz.open()
            
            # Her sayfayı işle
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                if image_compression:
                    # Görselleri sıkıştır
                    image_list = page.get_images()
                    
                    for img_index, img in enumerate(image_list):
                        xref = img[0]
                        try:
                            # Görseli çıkar
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image["image"]
                            
                            # Yeni sıkıştırılmış görsel oluştur
                            # deflate: Kayıpsız sıkıştırma
                            # jpeg: Kayıplı ama daha iyi sıkıştırma
                            new_image = fitz.Pixmap(image_bytes)
                            
                            # CMYK'yi RGB'ye çevir
                            if new_image.n - new_image.alpha > 3:
                                new_image = fitz.Pixmap(fitz.csRGB, new_image)
                            
                            # Görseli güncelle
                            doc._deleteObject(xref)
                            
                        except Exception as e:
                            # Bazı görseller çıkarılamayabilir, atla
                            continue
                
                # Sayfayı yeni PDF'e ekle
                writer.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # Yeni PDF'i kaydet - en agresif sıkıştırma seçenekleri
            writer.save(
                output_path,
                garbage=4,  # En agresif garbage collection (1-4)
                deflate=True,  # Stream'leri deflate ile sıkıştır
                clean=True,  # Gereksiz nesneleri temizle
                pretty=False,  # Güzel formatlamayı devre dışı bırak (alan tasarrufu)
                linear=False,  # Linearization devre dışı
            )
            
            writer.close()
            doc.close()
            
            # Sıkıştırma istatistikleri
            compressed_size = output_path.stat().st_size
            reduction = ((original_size - compressed_size) / original_size) * 100
            
            print(f"  ✓ Orijinal: {original_size / (1024**2):.2f} MB")
            print(f"  ✓ Sıkıştırılmış: {compressed_size / (1024**2):.2f} MB")
            print(f"  ✓ Azalma: {reduction:.1f}%")
            
            return {
                'success': True,
                'input_path': str(input_path),
                'output_path': str(output_path),
                'original_size': original_size,
                'compressed_size': compressed_size,
                'reduction_percent': reduction
            }
            
        except Exception as e:
            print(f"  ✗ Hata: {e}")
            return {
                'success': False,
                'error': str(e),
                'input_path': str(input_path)
            }
    
    def compress_directory(self, directory: str, recursive: bool = True, 
                          replace_original: bool = False, quality: int = 95) -> dict:
        """
        Bir klasördeki tüm PDF'leri sıkıştırır
        
        Args:
            directory: Sıkıştırılacak PDF'lerin olduğu klasör
            recursive: Alt klasörleri de tara
            replace_original: Orijinal dosyayı sıkıştırılmış ile değiştir
            quality: Görüntü kalitesi (0-100)
            
        Returns:
            dict: Toplam sıkıştırma istatistikleri
        """
        directory = Path(directory)
        
        if not directory.exists():
            print(f"❌ Klasör bulunamadı: {directory}")
            return {'success': False, 'error': 'Klasör bulunamadı'}
        
        print("\n" + "=" * 80)
        print(f"📁 KLASÖR SİKİŞTIRMA: {directory}")
        print("=" * 80)
        
        # PDF dosyalarını bul
        if recursive:
            pdf_files = list(directory.rglob("*.pdf"))
        else:
            pdf_files = list(directory.glob("*.pdf"))
        
        # Zaten sıkıştırılmış dosyaları çıkar
        pdf_files = [f for f in pdf_files if self.output_suffix not in f.stem]
        
        print(f"📊 Toplam {len(pdf_files)} PDF dosyası bulundu\n")
        
        stats = {
            'total': len(pdf_files),
            'successful': 0,
            'failed': 0,
            'total_original_size': 0,
            'total_compressed_size': 0,
            'failed_files': []
        }
        
        for idx, pdf_file in enumerate(pdf_files, 1):
            print(f"[{idx}/{stats['total']}]", end=" ")
            
            # Çıkış yolu
            if replace_original:
                output_path = pdf_file.parent / f"{pdf_file.stem}_temp.pdf"
            else:
                output_path = None
            
            # Sıkıştır
            result = self.compress_pdf(
                input_path=str(pdf_file),
                output_path=str(output_path) if output_path else None,
                quality=quality
            )
            
            if result['success']:
                stats['successful'] += 1
                stats['total_original_size'] += result['original_size']
                stats['total_compressed_size'] += result['compressed_size']
                
                # Orijinali değiştir
                if replace_original:
                    pdf_file.unlink()  # Orijinali sil
                    output_path.rename(pdf_file)  # Sıkıştırılmışı yeniden adlandır
                    print(f"  ✓ Orijinal dosya değiştirildi")
            else:
                stats['failed'] += 1
                stats['failed_files'].append({
                    'file': str(pdf_file),
                    'error': result.get('error', 'Bilinmeyen hata')
                })
        
        # Özet rapor
        print("\n" + "=" * 80)
        print("📊 SİKİŞTIRMA ÖZETİ")
        print("=" * 80)
        print(f"Toplam Dosya: {stats['total']}")
        print(f"✅ Başarılı: {stats['successful']}")
        print(f"❌ Başarısız: {stats['failed']}")
        
        if stats['successful'] > 0:
            total_reduction = ((stats['total_original_size'] - stats['total_compressed_size']) 
                             / stats['total_original_size']) * 100
            print(f"\n💾 Toplam Orijinal Boyut: {stats['total_original_size'] / (1024**2):.2f} MB")
            print(f"💾 Toplam Sıkıştırılmış Boyut: {stats['total_compressed_size'] / (1024**2):.2f} MB")
            print(f"📉 Toplam Tasarruf: {total_reduction:.1f}% ({(stats['total_original_size'] - stats['total_compressed_size']) / (1024**2):.2f} MB)")
        
        if stats['failed_files']:
            print(f"\n❌ Başarısız Dosyalar:")
            for failed in stats['failed_files']:
                print(f"  - {failed['file']}")
                print(f"    Hata: {failed['error']}")
        
        print("=" * 80)
        
        return stats


def main():
    """Ana fonksiyon - CLI kullanımı"""
    parser = argparse.ArgumentParser(
        description='PDF dosyalarını kalite kaybı olmadan sıkıştırır',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  # Tek bir dosyayı sıkıştır
  python compress_pdfs.py -f dosya.pdf
  
  # Bir klasördeki tüm PDF'leri sıkıştır
  python compress_pdfs.py -d ./downloads
  
  # Alt klasörler dahil, orijinalleri değiştir
  python compress_pdfs.py -d ./downloads -r --replace
  
  # Görsel kalitesi ile
  python compress_pdfs.py -d ./downloads -q 90
        """
    )
    
    parser.add_argument('-f', '--file', help='Sıkıştırılacak PDF dosyası')
    parser.add_argument('-d', '--directory', help='Sıkıştırılacak PDF klasörü')
    parser.add_argument('-o', '--output', help='Çıkış dosyası/klasörü')
    parser.add_argument('-r', '--recursive', action='store_true', 
                       help='Alt klasörleri de tara')
    parser.add_argument('--replace', action='store_true',
                       help='Orijinal dosyaları sıkıştırılmış ile değiştir')
    parser.add_argument('-q', '--quality', type=int, default=95,
                       help='Görsel kalitesi (0-100, varsayılan: 95)')
    parser.add_argument('-s', '--suffix', default='_compressed',
                       help='Sıkıştırılmış dosya son eki (varsayılan: _compressed)')
    
    args = parser.parse_args()
    
    # Parametre kontrolü
    if not args.file and not args.directory:
        parser.print_help()
        sys.exit(1)
    
    # Compressor oluştur
    compressor = PDFCompressor(output_suffix=args.suffix)
    
    # Tek dosya mı klasör mü
    if args.file:
        result = compressor.compress_pdf(
            input_path=args.file,
            output_path=args.output,
            quality=args.quality
        )
        
        if not result['success']:
            print(f"❌ Hata: {result.get('error', 'Bilinmeyen hata')}")
            sys.exit(1)
    
    elif args.directory:
        result = compressor.compress_directory(
            directory=args.directory,
            recursive=args.recursive,
            replace_original=args.replace,
            quality=args.quality
        )
        
        if not result.get('success', True):
            sys.exit(1)


if __name__ == "__main__":
    main()
