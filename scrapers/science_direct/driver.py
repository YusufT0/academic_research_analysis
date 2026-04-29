"""
Selenium WebDriver management for Science Direct scraper
"""

import sys
import random
from datetime import datetime
from pathlib import Path
from typing import Optional
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

# Selenium Wire import (proxy için)
from seleniumwire import webdriver as wire_webdriver
from seleniumwire.undetected_chromedriver import Chrome as WireChrome
SELENIUM_WIRE_AVAILABLE = True

# Undetected ChromeDriver import
try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False

sys.path.insert(0, str(__file__).rsplit('science_direct', 1)[0])
from utils.logger import get_logger
logger = get_logger('science_direct')

from .config import ProxyConfig


# Farklı User Agent'lar utils altından import ediliyor
from utils.user_agents import USER_AGENTS


class SeleniumDriver:
    """Selenium WebDriver yönetim sınıfı - Cloudflare bypass ve selenium-wire desteği ile"""
    
    def __init__(self, proxy_config: Optional[ProxyConfig] = None, headless: bool = False, 
                 use_undetected: bool = True, user_agent: str = None):
        """
        Selenium driver'ı başlatır
        
        Args:
            proxy_config: ProxyConfig nesnesi
            headless: Tarayıcıyı görünmez modda çalıştır
            use_undetected: undetected-chromedriver kullan (Cloudflare bypass için)
            user_agent: Özel user agent (None ise varsayılan kullanılır)
        """
        self.proxy_config = proxy_config
        self.headless = headless
        self.use_undetected = use_undetected and UNDETECTED_AVAILABLE
        # Her zaman selenium-wire kullan (proxy olsun olmasın)
        self.use_wire = SELENIUM_WIRE_AVAILABLE
        self.driver = None
        self.current_user_agent = user_agent
        self._used_user_agents = []  # Kullanılan user agent'ları takip et
        
        if use_undetected and not UNDETECTED_AVAILABLE:
            logger.warning("undetected-chromedriver bulunamadı, normal Chrome kullanılacak")
            logger.info("  Cloudflare bypass için: pip install undetected-chromedriver")
        
        if not SELENIUM_WIRE_AVAILABLE:
            logger.warning("selenium-wire bulunamadı")
            logger.info("  Gelişmiş destek için: pip install selenium-wire")
    
    def get_random_user_agent(self, exclude_current: bool = True) -> str:
        """
        Rastgele bir user agent seçer
        
        Args:
            exclude_current: Mevcut user agent'ı hariç tut
            
        Returns:
            str: Yeni user agent
        """
        available_agents = USER_AGENTS.copy()
        
        # Mevcut ve daha önce kullanılan agent'ları hariç tut
        if exclude_current and self.current_user_agent:
            if self.current_user_agent in available_agents:
                available_agents.remove(self.current_user_agent)
        
        for used_agent in self._used_user_agents:
            if used_agent in available_agents:
                available_agents.remove(used_agent)
        
        # Tüm agent'lar kullanıldıysa listeyi sıfırla
        if not available_agents:
            available_agents = USER_AGENTS.copy()
            self._used_user_agents.clear()
            if self.current_user_agent in available_agents:
                available_agents.remove(self.current_user_agent)
        
        new_agent = random.choice(available_agents)
        self._used_user_agents.append(new_agent)
        
        return new_agent
    
    def restart_with_new_user_agent(self) -> bool:
        """
        Mevcut tarayıcıyı kapatıp yeni user agent ile yeniden başlatır
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            logger.section("TARAYICI YENİDEN BAŞLATILIYOR (Yeni User Agent)")
            
            # Mevcut tarayıcıyı kapat
            if self.driver:
                try:
                    self.close()
                except:
                    pass
            
            # Yeni user agent seç
            new_user_agent = self.get_random_user_agent()
            self.current_user_agent = new_user_agent
            
            logger.info(f"Yeni User Agent: {new_user_agent[:60]}...")
            
            # Yeni tarayıcıyı başlat
            self.start()
            
            logger.success("Tarayıcı yeni user agent ile başlatıldı!")
            return True
            
        except Exception as e:
            logger.error(f"Tarayıcı yeniden başlatma hatası: {e}")
            return False
    
    def _configure_chrome_options(self):
        """Chrome seçeneklerini yapılandırır"""
        if self.use_undetected:
            # undetected-chromedriver için minimal options
            chrome_options = uc.ChromeOptions()
            
            # Headless mod ayarları
            if self.headless:
                chrome_options.add_argument('--headless=new')
                # Headless modda gerçek bir pencere boyutu ayarla
                chrome_options.add_argument('--window-size=1920,1080')
                # Headless tespitini zorlaştıran ayarlar
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
                logger.warning("Headless mod Cloudflare bypass'ı engelleyebilir")
            
            # Minimal argümanlar
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--log-level=3')
            
            # Bot tespitini zorlaştıran ek ayarlar
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-popup-blocking')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--lang=en-US,en')
            
            # NOT: User agent'ı burada değil, driver başladıktan sonra CDP ile ayarlıyoruz
            # chrome_options.add_argument ile user-agent ayarlamak UC'de sorun çıkarabiliyor
            
            # SSL sertifika hatalarını her zaman yoksay
            chrome_options.add_argument('--ignore-certificate-errors')
            chrome_options.add_argument('--ignore-ssl-errors')
            chrome_options.add_argument('--ignore-certificate-errors-spki-list')
            chrome_options.add_argument('--allow-insecure-localhost')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            
            # NOT: add_experimental_option UC ile uyumlu değil!
            # UC zaten kendi automation ayarlarını yönetiyor
            
            # Proxy kullanılıyorsa proxy ayarlarını ekle
            if self.proxy_config and self.proxy_config.is_configured():
                proxy_string = self.proxy_config.get_proxy_string()
                chrome_options.add_argument(f'--proxy-server={proxy_string}')
                
                logger.success(f"Proxy yapılandırıldı: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
                logger.success("SSL sertifika doğrulaması devre dışı (proxy için)")
            
        else:
            # Normal selenium için tam options
            chrome_options = Options()
            
            # Headless mod
            if self.headless:
                chrome_options.add_argument('--headless=new')
            
            # Temel ayarlar
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--start-maximized')
            
            # Bot tespitini zorlaştıran ayarlar
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
            chrome_options.add_argument('--lang=tr-TR')
            
            # User agent (custom veya varsayılan)
            user_agent = self.current_user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            chrome_options.add_argument(f'user-agent={user_agent}')
            if self.current_user_agent:
                logger.info(f"Custom User Agent: {user_agent[:50]}...")
            
            # Proxy ayarları - sadece normal Chrome için
            if self.proxy_config and self.proxy_config.is_configured():
                proxy_string = self.proxy_config.get_proxy_string()
                chrome_options.add_argument(f'--proxy-server={proxy_string}')
                
                # SSL sertifika hatalarını yoksay (proxy için gerekli)
                chrome_options.add_argument('--ignore-certificate-errors')
                chrome_options.add_argument('--ignore-ssl-errors')
                chrome_options.add_argument('--allow-insecure-localhost')
                
                # Proxy loopback bypass
                chrome_options.add_argument('--proxy-bypass-list=<-loopback>')
                
                logger.success(f"Proxy yapılandırıldı: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
                logger.success("SSL sertifika doğrulaması devre dışı (proxy için)")
            
            # Bildirimleri kapat
            prefs = {
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_setting_values.geolocation": 2,
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            }
            chrome_options.add_experimental_option("prefs", prefs)
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
        
        return chrome_options
    
    def start(self):
        """WebDriver'ı başlatır"""
        try:
            chrome_options = self._configure_chrome_options()
            
            # Her zaman selenium-wire kullan (proxy olsun olmasın)
            # Bu sayede her iki durumda da aynı davranış olur
            seleniumwire_options = {
                'verify_ssl': False,
                'suppress_connection_errors': True,
                'connection_timeout': 60,  # Proxy yavaşsa bağlantı kopmaması için artırıldı
                'connection_keep_alive': True # Bağlantıyı canlı tut
            }
            
            # Proxy varsa proxy ayarlarını ekle
            if self.proxy_config and self.proxy_config.is_configured():
                proxy_url = f"http://{self.proxy_config.proxy_user}:{self.proxy_config.proxy_pass}@{self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}"
                seleniumwire_options['proxy'] = {
                    'http': proxy_url,
                    'https': proxy_url,
                    'no_proxy': 'localhost,127.0.0.1'
                }
                logger.info("selenium-wire proxy yapılandırıldı:")
                logger.info(f"  - Host: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
                logger.info(f"  - User: {self.proxy_config.proxy_user}")
                logger.info("  - SSL doğrulama: Devre dışı")
            else:
                logger.info("Proxy kullanılmıyor (selenium-wire aktif)")
            # Sistemdeki Chrome versiyonunu tespit etmeye çalış
            import subprocess
            import re
            import sys
            import os
            
            client_version = None
            try:
                output = ""
                if sys.platform == "win32":
                    paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                    ]
                    for path in paths:
                        if os.path.exists(path):
                            cmd = f'(Get-Item "{path}").VersionInfo.ProductVersion'
                            result = subprocess.run(["powershell", "-command", cmd], capture_output=True, text=True)
                            output = result.stdout.strip()
                            if output:
                                break
                elif sys.platform.startswith("linux"):
                    for cmd_name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
                        try:
                            result = subprocess.run([cmd_name, "--version"], capture_output=True, text=True)
                            if result.stdout:
                                output = result.stdout.strip()
                                break
                        except Exception:
                            continue
                elif sys.platform == "darwin":
                    path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                    if os.path.exists(path):
                        result = subprocess.run([path, "--version"], capture_output=True, text=True)
                        output = result.stdout.strip()
                            
                if output:
                    match = re.search(r'(\d+)\.', output)
                    if match:
                        client_version = int(match.group(1))
                        logger.info(f"Oto-tespit edilen Chrome sürümü ({sys.platform}): {client_version}")
            except Exception as e:
                logger.debug(f"Chrome sürümü tespit edilemedi: {e}")
                
            if self.use_undetected:
                # undetected-chromedriver kullan (Cloudflare bypass)
                logger.info(f"undetected-chromedriver kullanılıyor (Cloudflare bypass, v{client_version or 'auto'})")
                
                # selenium-wire + undetected-chromedriver kombinasyonu
                try:
                    kwargs = {
                        "options": chrome_options,
                        "seleniumwire_options": seleniumwire_options
                    }
                    if client_version:
                        kwargs["version_main"] = client_version
                        
                    self.driver = WireChrome(**kwargs)
                    logger.success("selenium-wire + undetected-chromedriver aktif")
                except Exception as e:
                    logger.warning(f"WireChrome hatası, normal uc.Chrome deneniyor: {e}")
                    # Fallback: normal uc.Chrome with seleniumwire_options
                    # Options objesi kullanılmış olabilir, yeniden oluşturalım:
                    fallback_options = self._configure_chrome_options()
                    
                    fallback_kwargs = {
                        "options": fallback_options,
                        "seleniumwire_options": seleniumwire_options
                    }
                    if client_version:
                        fallback_kwargs["version_main"] = client_version
                        
                    self.driver = uc.Chrome(**fallback_kwargs)
                    logger.success("uc.Chrome + seleniumwire aktif")
                
            else:
                # Normal Selenium + selenium-wire kullan
                logger.info("Normal Chrome WebDriver + selenium-wire kullanılıyor")
                self.driver = wire_webdriver.Chrome(
                    options=chrome_options,
                    seleniumwire_options=seleniumwire_options
                )
                logger.success("selenium-wire aktif")
            
            self.driver.implicitly_wait(10)
            
            # Pencere boyutu
            self.driver.set_window_size(1920, 1080)
            
            # User Agent'ı CDP ile ayarla (daha güvenilir)
            if self.current_user_agent:
                try:
                    self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                        "userAgent": self.current_user_agent
                    })
                    logger.info(f"User Agent (CDP): {self.current_user_agent[:60]}...")
                except Exception as e:
                    logger.warning(f"CDP User Agent ayarlanamadı: {e}")
            
            # Bot tespitini zorlaştıran JavaScript injection
            if self.headless:
                self._apply_stealth_scripts()
            
            logger.success("Chrome WebDriver başarıyla başlatıldı")
            return self.driver
            
        except WebDriverException as e:
            logger.failed("WebDriver başlatma hatası", e)
            raise
    
    def _apply_stealth_scripts(self):
        """
        Headless modda bot tespitini zorlaştıran JavaScript kodlarını uygula
        """
        try:
            # navigator.webdriver özelliğini gizle
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    // webdriver özelliğini gizle
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // plugins dizisini doldur
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // languages dizisini ayarla
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    // Chrome özelliğini ekle
                    window.chrome = {
                        runtime: {}
                    };
                    
                    // Permissions API'yi düzelt
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                '''
            })
            logger.info("Stealth scripts uygulandı (headless mod)")
        except Exception as e:
            logger.warning(f"Stealth scripts uygulanamadı: {e}")
    
    def close(self):
        """WebDriver'ı kapatır"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                logger.success("WebDriver kapatıldı")
            except Exception as e:
                # Kapanma sırasında oluşan hataları görmezden gel
                logger.info("WebDriver kapatılırken küçük bir hata oluştu (görmezden gelindi)")
                self.driver = None
    
    def restart(self):
        """
        WebDriver'ı kapatıp yeniden başlat
        
        Returns:
            WebDriver instance veya None
        """
        try:
            logger.section("TARAYICI YENİDEN BAŞLATILIYOR")
            
            # Mevcut driver'ı kapat
            self.close()
            
            # Kısa bekleme
            import time
            time.sleep(2)
            
            # Yeni driver başlat
            result = self.start()
            
            if result:
                logger.success("Tarayıcı başarıyla yeniden başlatıldı!")
            else:
                logger.error("Tarayıcı yeniden başlatılamadı!")
            
            return result
            
        except Exception as e:
            logger.error(f"Tarayıcı yeniden başlatma hatası: {e}")
            return None
    
    def take_screenshot(self, name: str = "screenshot") -> str:
        """
        Ekran görüntüsü al
        
        Args:
            name: Screenshot dosya adı öneki
            
        Returns:
            str: Kaydedilen dosya yolu veya boş string
        """
        if not self.driver:
            logger.warning("Screenshot alınamadı: Driver aktif değil")
            return ""
            
        try:
            # Screenshots klasörünü oluştur
            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            
            # Dosya adını oluştur (tarih-saat ile)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            # Screenshot al
            self.driver.save_screenshot(str(filepath))
            logger.info(f"📸 Screenshot kaydedildi: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            logger.warning(f"Screenshot alma hatası: {e}")
            return ""
