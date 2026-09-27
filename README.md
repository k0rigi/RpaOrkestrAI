# RpaOrkestrAI

**macOS ve Windows için Python tabanlı, yerelde çalışan görsel RPA uygulaması.** Uygulama sahipleri Studio üzerinden otomasyon adımları ekler, koşul ve döngüleri düzenler, akışları kaydeder ve çalıştırır. Çalışma çıktıları CSV olarak departmanlara verilebilir; akış tanımları JSON olarak başka kurulumlara taşınabilir.

Studio, FastAPI üzerinden sunulan bir web arayüzüdür. İsterseniz aynı arayüzü pywebview ile yerel uygulama penceresinde açabilirsiniz. Masaüstü işlemleri uygulamanın çalıştığı bilgisayarda gerçekleşir.

## Başlangıç

Python **3.11+** gerekir. Komutları proje klasöründe çalıştırın.

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
rpa-studio
```

Windows / PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
rpa-studio
```

Arayüz varsayılan olarak **http://127.0.0.1:8765** adresinde açılır. Başka bir terminalden çalıştıracaksanız önce proje klasörüne geçip sanal ortamı etkinleştirin.

İlk denemede örnek akışı açın, adımlarını inceleyin ve çalıştırın. Örnek veriden üretilen CSV'yi çalışma sonucundan indirin. Gerçek otomasyon bağlantıları olmadan terminal demosu da çalışır:

```bash
rpa-studio demo
```

Studio zaten açıksa demo için ayrı bir veri klasörü kullanın:

```bash
rpa-studio demo --data-dir ./data/demo-check
```

Aynı veri klasörü eşzamanlı olarak yalnız bir Studio veya demo süreci tarafından açılabilir.

Tam kurulum, işletim sistemi izinleri ve bağlantılar için [kurulum rehberini](docs/kurulum.md) izleyin.

## Uygulamada neler yapılır?

| Alan | İşlev |
| --- | --- |
| Akış tasarımı | Adım ekleme, sıralama, düzenleme; iç içe koşul ve döngüler |
| Akış yönetimi | Kaydetme, açma, JSON içe/dışa aktarma ve departman bilgisi |
| Çalıştırma | Arka planda çalışma, adım günlükleri, geçmiş ve iptal isteği |
| Raporlar | Akış verisinden CSV üretme ve indirme |
| Veritabanı | PostgreSQL / SQL Server tablolarını izin listesi ve parametreli filtrelerle okuma |
| Masaüstü | Koordinata veya görsel şablona tıklama, metin yazma ve platforma uygun kısayollar |
| ERP listeleri | Bilinen değerler veya OCR ile toplanan dropdown seçenekleri üzerinde döngü |
| Görsel algılama | OpenCV şablon eşleştirme, OCR metni ve koşullu kararlar |
| Google Sheets | Hücre ve aralık okuma/yazma; servis katmanında satır ekleme |
| Web | Playwright ile headless Chromium işlemleri |

Bu sürüm tek bilgisayarda uygulama sahibi tarafından kullanılır. Departman alanı raporları ve akışları sınıflandırır; kullanıcı hesabı veya erişim yetkisi oluşturmaz. Merkezi çok kullanıcılı sunucu, uzak robot yönetimi ve zamanlayıcı bu sürümün kapsamı dışındadır.

## İlk gerçek otomasyon

1. [Kurulum rehberindeki](docs/kurulum.md) otomasyon paketlerini ve gerekli sistem araçlarını kurun.
2. Bağlantı bilgilerini `.env` veya uygulamanın bağlantı ayarlarında tanımlayın. Veritabanında ayrı salt okunur kullanıcı kullanın.
3. Yeni akışa ad ve departman girin. Adım kitaplığından veri okuma adımını ve ardından bir döngü ekleyin.
4. Çıktı değişkenlerini sonraki adımlara `${orders}` veya `${item.MATERIAL}` biçiminde bağlayın.
5. ERP tıklama, alan doldurma ve arama adımlarını döngünün içine yerleştirin. OCR sonucuna göre koşul ekleyin.
6. Önizleme ile adım yapısını inceleyin; ardından hedef uygulama hazırken gerçek çalıştırmayı başlatın.
7. CSV raporu ekleyip çalışma çıktısını ilgili departmanla paylaşın.

Akış geliştirme, değişkenler ve önizleme ayrıntıları [kullanım rehberindedir](docs/akislar.md).

**Önizleme gerçek bağlantıları doğrulamaz.** Veritabanı, ekran, web ve Sheets gibi dış adımlar atlanır ve günlükte belirtilir. Yerel veri ve kontrol adımları değerlendirilir. Atlanan dış adıma bağlı veri bilinmiyorsa ona bağlı döngü/koşul da değerlendirilmez; hayali ERP sonucu üretilmez.

## Otomasyon ve yerel pencere

Gerçek dış bağlantılar için:

```bash
python -m pip install -e ".[automation,dev]"
python -m playwright install chromium
rpa-studio doctor
```

Tesseract ve SQL Server ODBC sürücüsü işletim sistemine ayrıca kurulur. macOS ekran/erişilebilirlik izinleri de masaüstü işlemleri için gereklidir. [Platform kurulum adımları](docs/kurulum.md).

İsteğe bağlı yerel pencere:

```bash
python -m pip install -e ".[native]"
rpa-studio --native
```

Bu kurulumdan sonra macOS'ta [start.command](start.command), Windows'ta [start.bat](start.bat) dosyasını çift tıklayarak yerel pencereyi açabilirsiniz. Başlatıcılar varsayılan olarak proje içindeki `.venv` sanal ortamını kullanır; Python, paket ve sistem bağımlılıklarını kendileri kurmaz.

**macOS'ta Masaüstü/Belgeler iCloud ile eşitleniyorsa:** önce [setup-macos.command](setup-macos.command) dosyasını çalıştırın (`uv` veya proje içindeki `.bootstrap/bin/uv` gereklidir). Bu kurulum Python ve paketleri `~/Library/Application Support/RpaOrkestrAI/` içine yerleştirir. Ardından `start.command` bu yerel ortamı tercih eder ve güncel kaynak kodunu oraya eşitler; Python bileşenleri her açılışta buluttan beklenmez. Akışlar ve ayarlar projenin mevcut veri dizininde kalır.

Başlatıcı açılış durumunu Terminal'de gösterir. Aynı sürüm ve çalışma alanı zaten açıksa masaüstü penceresi o sunucuya bağlanır; ikinci sunucu başlatmaz. Sunucu kapalıysa kendisi başlatır. Önceden açık bir sunucuya bağlanan pencerenin kapanması o sunucuyu durdurmaz. Başlatıcı kendi sunucusunu açtıysa pencere kapatılırken onu da kapatır. Eski bir sürüm açıkken güncelleme yaptıysanız önce eski uygulamayı kapatın.

Başlatıcılar bu klasördeki güncel kaynak kodunu kullanır; her kod değişikliğinde paketi yeniden kurmanız gerekmez. Bağımlılıklar değişirse kurulum adımını tekrar çalıştırın. Açılış başarısız olursa Terminal hata mesajını gösterir ve Enter tuşuna basılana kadar açık kalır.

Tarayıcıyı otomatik açmadan çalıştırmak için `rpa-studio --no-browser` kullanın. CLI seçeneklerini `rpa-studio --help` ile görebilirsiniz.

## Yapılandırma ve saklama

| Ortam değişkeni | Varsayılan / amaç |
| --- | --- |
| `RPA_DATA_DIR` | `./data`; akışlar, çalışmalar, raporlar ve yerel ayarlar |
| `RPA_PORT` | `8765`; Studio portu |
| `RPA_DATABASE_URL` | Boş; SQLAlchemy veritabanı bağlantı adresi |
| `RPA_ALLOWED_TABLES` | `public.IASSALITEM,public.IASINVITEM`; virgülle ayrılan tam tablo adları |
| `RPA_MAX_ROWS` | `10000`; veritabanı satır üst sınırı |
| `RPA_GOOGLE_CREDENTIALS_PATH` | Boş; servis hesabı JSON dosyasının yolu |
| `RPA_TEMPLATE_DIR` | `./assets/templates`; eşleştirme şablonlarının kökü |
| `RPA_TESSERACT_CMD` | Boş; Tesseract PATH dışında ise program yolu |
| `RPA_OCR_LANGUAGE` | `tur+eng`; yüklü OCR dilleri |
| `RPA_ACTION_TIMEOUT` | `30`; adaptör beklemelerinde kullanılan saniye değeri |

Zaman aşımı tarayıcı, veritabanı, ekran bekleme ve OCR işlemlerine aktarılır. Sheets için istek başına üst sınır 120 saniyedir. Tek bir adım birden fazla istek, yeniden deneme veya dropdown sayfası içerebilir; bu değer tüm akışın toplam süre sınırı değildir.

Studio'da kaydedilmiş bağlantı ayarları `data/settings.json` içindedir ve aynı alanlar için `.env` varsayılanlarından önce gelir. `.env` değişikliğinin uygulanması için uygulamayı yeniden başlatın; daha önce Studio'da kaydedilmiş değeri de güncelleyin. `data/` ile `.env` Git'e eklenmez. Yerel ayar dosyası bir şifre kasası değildir; bilgisayar hesabı ve dosya erişimleri bu bilgileri korur.

Akış dışa aktarımı bağlantı ayarlarını içermez. Ancak adımlara sizin yazdığınız sabit metinler, değişkenler ve iş verileri JSON içinde yer alabilir. Çalışma günlükleri ve CSV dosyaları da iş verisi içerebilir; paylaşılacak çıktıyı inceleyin.

## Geliştirme ve doğrulama

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

GitHub Actions, macOS ve Windows üzerinde Python 3.11/3.12 için çekirdek testleri çalıştırır. Bu testler canlı ERP oturumu, veritabanı hesabı veya Google anahtarı gerektirmez. Gerçek masaüstü, OCR, sürücü ve ağ bağlantıları hedef bilgisayarda ayrıca doğrulanmalıdır; CI bunların yerini tutmaz.

Uygulama localhost üzerinde kullanılır; bu sürümü port yönlendirmeyle internete veya ortak ağa açmayın. Masaüstü robotu çalışırken hedef pencere odağı ve ekran düzeni korunmalıdır. İptal isteği bir sonraki denetim noktasında uygulanır; tamamlanmış dış işlemleri geri almaz.

## Rehberler

- [Kurulum, macOS/Windows izinleri ve bağlantılar](docs/kurulum.md)
- [Akış oluşturma, değişkenler ve raporlar](docs/akislar.md)
- [Salt okunur veritabanı hesabı](docs/veritabani.md)
- [Mimari ve genişletme](docs/mimari.md)
- [GitHub remote ve push](docs/github.md)
