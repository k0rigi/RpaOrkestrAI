# Kurulum ve bağlantılar

RpaOrkestrAI Python 3.11 veya üstünü kullanır. Studio ve yerel demo, masaüstü otomasyon paketleri veya harici hesaplar olmadan açılabilir. Gerçek ERP, OCR, veritabanı, Sheets ve web işlemleri için `automation` ek bağımlılıklarını yükleyin.

## macOS

Terminalde proje klasörüne geçin:

```bash
cd "/projenizin/yolu/RpaOrkestrAI"
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
rpa-studio
```

Python sürümü 3.11'den eskiyse önce uygun bir Python kurup sanal ortamı o yorumlayıcıyla oluşturun. Uygulamayı her başlattığınızda aynı proje klasöründe `source .venv/bin/activate` çalıştırın; `.env` ve varsayılan `data/` dizini bu çalışma konumuna göre bulunur.

Masaüstü otomasyonu için Sistem Ayarları → Gizlilik ve Güvenlik altında uygulamayı başlatan Terminal/IDE veya paketlenmiş uygulamaya **Erişilebilirlik** ve **Ekran ve Sistem Sesi Kaydı** izinlerini verin. İzin değişikliğinden sonra ilgili uygulamanın yeniden açılması gerekebilir. [Apple erişilebilirlik izinleri](https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac), [Apple ekran kaydı izinleri](https://support.apple.com/guide/mac-help/control-access-screen-system-audio-recording-mchld6aa7d23/mac).

## Windows / PowerShell

```powershell
Set-Location "C:\projeler\RpaOrkestrAI"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
rpa-studio
```

Makinenizde 3.12 kuruluysa ilk komutta `py -3.12` kullanabilirsiniz. PowerShell aktivasyon betiğini engelliyorsa sistemin execution policy ayarını değiştirmeden sanal ortamın programlarını doğrudan çağırabilirsiniz:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\rpa-studio.exe
```

Masaüstü akışını ekranı açık ve kilidi kaldırılmış bir oturumda çalıştırın. ERP ve şablonların üretildiği ekran ölçeğini, pencere boyutunu ve yakınlaştırmayı eşleştirin. Farklı monitörlere taşınan pencereler için koordinatları ve şablonları yeniden doğrulayın. Yönetici yetkisiyle çalışan ERP ile normal kullanıcı oturumundaki robot arasında giriş kısıtlamaları olabilir; uygulamayı rutin olarak yönetici yapmadan önce ERP'nin normal yetkilerle çalışmasını tercih edin.

## Otomasyon bağımlılıkları

Aktif sanal ortamda, iki sistem için de:

```bash
python -m pip install -e ".[automation,dev]"
python -m playwright install chromium
rpa-studio doctor
```

Playwright'ın Python paketi ile tarayıcı ikilileri ayrı kurulur. Paket güncellendikten sonra Chromium kurulum komutunu yeniden çalıştırmak gerekebilir. [Playwright Python kurulumu](https://playwright.dev/python/docs/library), [tarayıcı kurulumu](https://playwright.dev/python/docs/browsers).

### OCR / Tesseract

`pytesseract`, sistemdeki Tesseract programını çağırır; yalnızca pip paketi OCR motorunu kurmaz.

macOS'ta Homebrew mevcutsa:

```bash
brew install tesseract tesseract-lang
tesseract --list-langs
```

Windows'ta Tesseract belgelerinde bağlantısı verilen dağıtımlardan birini kullanın. Projenin güncel Windows sürümleri için kendi resmi yükleyicisi bulunmadığından yükleyicinin sağlayıcısını kontrol edin. Örnek program yolu `C:\Program Files\Tesseract-OCR\tesseract.exe` olur; gerçek kurulum yolunu uygulama ayarında belirtin. [Tesseract kurulumu](https://tesseract-ocr.github.io/tessdoc/Installation.html), [Windows indirme seçenekleri](https://tesseract-ocr.github.io/tessdoc/Downloads.html), [Homebrew dil paketi](https://formulae.brew.sh/formula/tesseract-lang).

Türkçe ve İngilizce için `tur` ve `eng` dil modellerinin kurulu olduğunu `tesseract --list-langs` çıktısından doğrulayın. Dili `RPA_OCR_LANGUAGE=tur+eng`, program konumunu `RPA_TESSERACT_CMD` ile yapılandırın. Örneğin Windows `.env` dosyasında `RPA_TESSERACT_CMD='C:\Program Files\Tesseract-OCR\tesseract.exe'` kullanılabilir. Küçük yazılarda ekran bölgesini daraltmak ve ölçeklendirmeyi sabit tutmak tanımayı kolaylaştırır.

### SQL Server / ODBC

`pyodbc` ayrıca işletim sisteminde Microsoft ODBC Driver for SQL Server gerektirir. Python mimarisiyle sürücü mimarisini eşleştirin; özellikle Apple Silicon'da ARM ve Intel ortamlarını karıştırmayın.

macOS'ta Microsoft'un Homebrew kurulumunu izleyin. Windows'ta Microsoft'un mimarinize uygun ODBC Driver 18 yükleyicisini kurun. Kurumsal lisans kabulü ve işletim sistemi paket kurulumu uygulamanın pip kurulumundan ayrıdır. [Microsoft macOS ODBC kurulumu](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/install-microsoft-odbc-driver-sql-server-macos), [Microsoft Windows sürücü indirmeleri](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).

Kurulu sürücüleri aktif sanal ortamdan görebilirsiniz:

```bash
python -c "import pyodbc; print(pyodbc.drivers())"
```

Veritabanı hesabı ve bağlantı örnekleri [salt okunur veritabanı rehberindedir](veritabani.md).

### Google Sheets

1. Google Cloud projesinde Google Sheets API'yi etkinleştirin. gspread'in dosya keşfi gibi Drive işlemlerini kullanacaksanız Google Drive API'yi de etkinleştirin.
2. Bir servis hesabı oluşturup JSON anahtarını proje içindeki Git tarafından yok sayılan `credentials/` klasörüne veya proje dışındaki güvenli bir konuma kaydedin.
3. Hedef elektronik tabloyu JSON dosyasındaki `client_email` adresiyle paylaşın. Yazma işlemleri için düzenleyici yetkisi gerekir.
4. `.env` dosyasında `RPA_GOOGLE_CREDENTIALS_PATH=./credentials/service-account.json` değerini kendi JSON dosyanızın yoluyla doldurun. Akış adımında elektronik tablo kimliğini, çalışma sayfasını ve hücre/aralığı belirtin.

Elektronik tablo kimliği URL'deki `/spreadsheets/d/` ile sonraki `/` arasındadır. Servis hesabının tabloya erişimi yoksa dosya mevcut olsa bile `SpreadsheetNotFound` görülebilir. [gspread servis hesabı kurulumu](https://docs.gspread.org/en/master/oauth2.html).

Kimlik bilgilerini akış JSON'una yazmayın. Aynı akışı farklı bir bilgisayara aktarırken o bilgisayarın `.env` dosyasını ve erişimlerini ayrı yapılandırın.

## Yerel pencere seçeneği

Tarayıcı yerine yerel uygulama penceresi açmak için:

```bash
python -m pip install -e ".[native]"
rpa-studio --native
```

Bu seçenek aynı Studio arayüzünü pywebview penceresinde gösterir. İşletim sisteminin web görünümü bileşenleri gerekir; Windows WebView2 gibi ek gereksinimleri [pywebview kurulum belgesinden](https://pywebview.flowrl.com/guide/installation.html) kontrol edin. Bu depoda imzalı `.app` veya `.exe` dağıtım paketi üretilmez.

`native` bağımlılıklarını kurduktan sonra proje kökündeki **macOS `start.command`** veya **Windows `start.bat`** dosyasını çift tıklayabilirsiniz. Başlatıcı önce kendi klasörüne geçer ve `.venv` içindeki Python ile yerel pencereyi açar. Sanal ortam yoksa kurulum yönergesi gösterir; otomatik paket indirme veya kurulum yapmaz.

Başlatıcı `launch.py` ile doğrudan projenin `src/` klasörünü yükler. Böylece kurulu paketin eski kopyası veya macOS'ta gizli işaretlenmiş `.pth` dosyaları kaynak kodunun yüklenmesini engellemez. İlk açılışta bileşenler yüklenirken durum mesajları görünür. Proje iCloud ile eşitlenen Masaüstü/Belgeler içindeyse bulut simgeli dosyaların indirilmesi ek süre alabilir.

Aynı portta, aynı sürüm ve çalışma alanına ait Studio açıksa yeni masaüstü penceresi ona bağlanır. Farklı bir uygulama/çalışma alanı veya eski sürüm algılanırsa anlaşılır hata gösterilir; başka uygulamanın portu devralınmaz. Güncelleme sonrası eski Studio'yu kapatıp tekrar açın. Bir sunucuya bağlanan pencere o sunucuyu kapatmaz; kendisi sunucu başlatan pencere kapanırken onu durdurur. CSV indirme yerel pencerede de etkindir.

Komut satırından aynı başlatıcılar:

```bash
# macOS
./start.command
```

```powershell
# Windows
.\start.bat
```

Başlatıcıyla açmadan önce aynı veri klasörünü kullanan terminal Studio'sunu kapatın. İkinci uygulama farklı port seçse de aynı veri klasörünü eşzamanlı açamaz. Studio açıkken bağlantısız CLI demosunu denemek için ayrı klasör seçin:

```bash
rpa-studio demo --data-dir ./data/demo-check
```

Bu örnek yalnız yerel demo verisini işler. Farklı veri klasörleriyle çalışan gerçek masaüstü akışları ortak fare ve klavyeyi yine paylaşır; bunları aynı anda çalıştırmayın.

## Sık karşılaşılan durumlar

| Belirti | Kontrol |
| --- | --- |
| `rpa-studio` bulunamıyor | Sanal ortamı etkinleştirin veya `.venv` içindeki yürütülebilir dosyayı çağırın. |
| Masaüstü görüntüsü siyah / tıklama çalışmıyor | macOS izinleri, açık oturum ve hedef pencerenin odağını kontrol edin. |
| Şablon bulunamıyor | Ekran ölçeğini, ERP temasını, arama bölgesini ve güven eşiğini kontrol edin. |
| OCR dili yüklenemiyor | `tesseract --list-langs` ile dil modelini ve program yolunu kontrol edin. |
| SQL Server sürücüsü bulunamıyor | `pyodbc.drivers()` çıktısıyla bağlantıdaki sürücü adını karşılaştırın. |
| Chromium bulunamıyor | Aynı sanal ortamda `python -m playwright install chromium` çalıştırın. |
| Sheets erişim hatası | Servis hesabı e-postasının hedef tabloya erişimini kontrol edin. |
| Çalışma alanı başka Studio tarafından kullanılıyor | Aynı `RPA_DATA_DIR` ile çalışan diğer Studio/demo sürecini kapatın. Bağlantısız demoya ayrı `--data-dir` verilebilir. |
| İptal hemen tamamlanmıyor | Geçerli adaptör çağrısının veya zaman aşımının dönmesini bekleyin; iptal tamamlanmış dış işlemleri geri almaz. |
