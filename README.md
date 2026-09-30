# RpaOrkestrAI

**macOS ve Windows için Python tabanlı, yerelde çalışan görsel RPA uygulaması.** Uygulama sahipleri Studio üzerinden otomasyon adımları ekler, koşul ve döngüleri düzenler, akışları kaydeder ve çalıştırır. Çalışma çıktıları CSV olarak departmanlara verilebilir; akış tanımları JSON olarak başka kurulumlara taşınabilir.

Studio, FastAPI üzerinden sunulan bir web arayüzüdür. İsterseniz aynı arayüzü pywebview ile yerel uygulama penceresinde açabilirsiniz. Masaüstü işlemleri uygulamanın çalıştığı bilgisayarda gerçekleşir.

## Masaüstü uygulaması olarak kullanım

Hazır kurulum dosyaları için **[RpaOrkestrAI indirme sayfası](https://orkestrai.net/rpa/)** kullanılır. GitHub'daki alternatif dağıtım yeri [Releases](https://github.com/k0rigi/RpaOrkestrAI/releases) bölümüdür; özel depoya erişim için GitHub hesabınızla giriş yapın.

- **Windows:** `RpaOrkestrAI-Setup-0.6.1-Windows-x64.exe` dosyasını çalıştırın; ardından masaüstündeki **RpaOrkestrAI Studio** kısayolunu açın.
- **MacBook (Apple Silicon: M1 ve sonrası):** `RpaOrkestrAI-0.6.1-macOS-arm64.dmg` dosyasını açın, içindeki **RpaOrkestrAI.app** uygulamasını **Applications** kısayoluna sürükleyin; `/Applications/RpaOrkestrAI.app` üzerinden açın. Bu paket Intel Mac için değildir.

**0.5.0 ve sonrası orkestrai.net hesabıyla açılır.** Kullanıcının firmasında ve kendi hesabında **MOD_RPA** modülünün açık, firma lisans süresinin dolmamış olması gerekir. Süresi dolmuş veya lisansı tanımlı olmayan kullanıcıya uygulama uyarı verip kapanır. Son doğrulamadan sonra internetsiz en fazla 7 gün çalışır. [Kullanıcı girişi ve lisans](docs/lisans.md).

Bu paketler kendi Python 3.12 yorumlayıcısını içerir ve terminal açmadan çalışır; bilgisayara ayrıca Python 3.14 kurulması onları etkilemez. **Code → Download ZIP** kaynak kod indirmesidir. `start.command` ve `start.bat`, terminale bağlı geliştirme başlatıcılarıdır; terminal kapatılırsa bu şekilde açılan süreç de kapanabilir. Yeni derlemeler **Actions → Build desktop apps → Artifacts** bölümünde bulunur. [Masaüstü dağıtım rehberi](docs/masaustu-dagitim.md).

**0.1.x kullananlar güncel sürümü bir kez elle kurmalıdır.** 0.2.0 ve sonraki kurulu uygulamalar açılışta yeni sürümü arka planda kontrol edip doğrulayarak indirir; hazır güncellemeyi sonraki açılışta kurar. İnternet yoksa mevcut sürüm çalışır, akışlar ve bağlantı ayarları korunur. Kendi akışınıza eklediğiniz adımlar yerel kalır; kodla geliştirilen yeni adım türleri yeni uygulama sürümü yayımlandığında diğer kurulumlara ulaşır. [Güncelleme mimarisi](docs/guncelleme-mimarisi.md).

Bu test dağıtımı Apple noter onayı ve Windows yayıncı sertifikası olmadan hazırlanır; ilk kurulumda sistemin veya şirketinizin gerektirdiği onaylar çıkabilir.

Kaynak kodla Windows kurulumu yapanlar için `setup-windows.bat` masaüstüne terminal açmayan **RpaOrkestrAI Studio** kısayolu ekler.

## Başlangıç

Bu bölüm **kaynak koddan geliştirme** içindir; standart 64 bit Python **3.11, 3.12, 3.13 veya 3.14** gerekir. Free-threaded Python dağıtımları destek kapsamı dışındadır. Komutları proje klasöründe çalıştırın.

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
rpa-studio
```

Windows'ta GitHub'dan ilk kurulum:

1. ZIP dosyasını tamamen çıkarın. Örneğin `C:\RpaOrkestrAI` gibi yazabildiğiniz bir klasör kullanın.
2. **Python 3.11–3.14 (standart 64 bit)** kurulu olmalıdır. Kurulum betiği 3.14, 3.13, 3.12 ve 3.11 sırasıyla arar; varsa desteklenen mevcut `.venv` ortamını kullanır.
3. [setup-windows.bat](setup-windows.bat) dosyasını çift tıklayın. Sanal ortamı ve yerel pencere/otomasyon paketlerini kurar; internet gerekir.
4. Kurulum bitince masaüstündeki **RpaOrkestrAI Studio** kısayoluyla terminal açmadan başlatın. Hata ayıklamak için [start.bat](start.bat) kullanılabilir. Yerel pencere bileşeninde sorun varsa [start-browser.bat](start-browser.bat) aynı Studio'yu tarayıcıda açar.

GitHub indirmesi `.venv` içermez; Python ortamı her bilgisayarda yeniden kurulur. macOS ortamını Windows'a kopyalamayın. PowerShell komutları ve hata çözümleri [Windows kurulum rehberindedir](docs/kurulum.md#windows--powershell).

Arayüz varsayılan olarak **http://127.0.0.1:8765** adresinde açılır. Başka bir terminalden çalıştıracaksanız önce proje klasörüne geçip sanal ortamı etkinleştirin.

**0.6.0 ile adım kütüphanesi 63 adıma çıktı.** Kütüphane şu grupları kapsar:
- fare ve klavye: tıkla, sürükle, kaydır, yaz, kısayol, tuşu basılı tut
- pencere: öne getir, büyüt/küçült, taşı, kapat, kapanmasını bekle, alanın değerini oku
- ekran: görsel ara/tıkla, kurulum gerektirmeyen OCR ile metin oku/bekle, piksel rengi, ekran görüntüsü
- uygulama ve sistem: uygulama/dosya/adres aç, uygulamayı kapat, komut çalıştır, pano
- dosya ve Excel: .xlsx/CSV oku-yaz, dosya listele, kopyala/taşı/sil, indirmeyi bekle
- veri: hesapla, metin, tarih, liste
- akış: tekrarla, döngüden çık, hata olursa, başka akışı çalıştır, akışı bitir
- etkileşim ve web: mesaj ve girdi kutusu, HTTP/API

**Hareketleri kaydet**, bir işi fare ve klavyeyle bir kez yapmanızı adımlara çevirir; kayıt F9 ile biter. Adımlar tutup sürüklenerek yer değiştirir ve döngü, koşul veya hata bloklarının içine bırakılabilir. **Bu adımı test et**, seçili adımı örnek değerlerle tek başına çalıştırır. **Çalıştır** adımları gerçekten uygular; **Önizleme (ekranı kullanmadan)** seçeneği ekran, dosya ve bağlantı adımlarını atlar. Tüm adımlar, AutoHotkey karşılıkları ve örnekler [adım rehberindedir](docs/adimlar.md). İlk denemeler için [examples/adim-turu.json](examples/adim-turu.json) ve [examples/metin-editoru.json](examples/metin-editoru.json) akışlarını içe aktarabilirsiniz.

Sheets adımları, Google Cloud veya JSON dosyası gerektirmeyen **Apps Script** bağlantısıyla ya da Google servis hesabıyla çalışır; [Google Sheets bağlantı rehberi](docs/google-sheets.md). **Sheets satırlarını oku** ile B sütununa `form_id`, C sütununa `status` adı verin; döngüde `${row.form_id}` ve `${row.status}` kullanın. Durumu **boş veya Bekliyor** olanları koşulla seçebilir, her dalın içine işlem veya başka bir döngü ekleyebilirsiniz. **Koşul sürdükçe tekrarla**, tekrar ve süre sınırlarıyla çalışır. [Sheets satır ve koşul rehberi](docs/sheets-satir-dongusu.md).

**Alanı doldur → Ekranda seç**, 3/5/10 saniyelik geri sayım sonunda fare konumunu alır. Uygulama alana bir kimlik veriyorsa (Windows UI Automation, macOS Erişilebilirlik) **Alan kimliği** önerilir: alan, pencere boyutu veya ekran ölçeği değişse de kimliğiyle bulunur. Kimlik vermeyen uygulamalarda konum veya görsel yöntem kullanılır; görsel yöntemde ekranın alınmış görüntüsü üzerinde fareyle alan kırpıp hedef noktayı seçersiniz. Önizlemeyi kontrol ederek **Hedefi kaydet** ile onaylayın; **Esc** seçimden vazgeçirir. **Görüntü üzerinde seç** aynı seçimi Studio içindeki görüntüde yapar ve tarayıcıdan kullanımda da çalışır. Her iki yöntemde ERP penceresi **ana ekranda ve tamamen görünür** olmalıdır. macOS ekran kaydı ve erişilebilirlik izinleri, Windows pencere odağı ve yetkileri [pencere tanıtma rehberinde](docs/pencere-tanitma.md) açıklanır.

İlk açılışta örnek akış oluşturulmaz. Mevcut akışlar düzenlenebilir ve çalıştırılabilir; eski **Sheets sütununu oku** / `${row.value}` ve odaktaki alana yazma adımları korunur. Kütüphaneye eklenen adımları yıldızlayarak en üstteki **Sık kullanılanlar** bölümüne taşıyabilirsiniz; favoriler uygulama yeniden açıldığında korunur. Gerçek otomasyon bağlantıları olmadan terminal demosu da çalışır:

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
| Masaüstü | Geri sayımla fare konumu alma, alanı uygulama yapısındaki kimliğiyle bulma, fareyle görsel alanı seçme; hedefe tıklama, alan doldurma ve platforma uygun kısayollar |
| ERP listeleri | Bilinen değerler veya OCR ile toplanan dropdown seçenekleri üzerinde döngü |
| Görsel algılama | OpenCV şablon eşleştirme, OCR metni ve koşullu kararlar |
| Google Sheets | Adlandırılmış sütunlarla satır okuma, boş durumları koruma; hücre okuma/yazma ve servis katmanında satır ekleme |
| Web | Playwright ile headless Chromium işlemleri |

Bu sürüm her bilgisayarda orkestrai.net hesabıyla açılır; akışlar ve ayarlar o bilgisayarın çalışma alanında kalır. Departman alanı raporları ve akışları sınıflandırır; akış bazında erişim yetkisi oluşturmaz. Merkezi çok kullanıcılı sunucu, uzak robot yönetimi ve zamanlayıcı bu sürümün kapsamı dışındadır.

## İlk gerçek otomasyon

Masaüstü ERP için [pencere tanıtma rehberiyle](docs/pencere-tanitma.md) başlayın. Daha kapsamlı işlemler için aşağıdaki sırayı izleyin. Tabloda ve rehberlerde anlatılan mevcut motor işlemleri, eski veya içe aktarılan akışlarda desteklenmeye devam eder.

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

Bu kurulumdan sonra macOS'ta [start.command](start.command), Windows'ta [start.bat](start.bat) dosyasını çift tıklayarak yerel pencereyi açabilirsiniz. Başlatıcılar varsayılan olarak proje içindeki `.venv` sanal ortamını kullanır. Windows ilk kurulumunu `setup-windows.bat` yapar; `start.bat` ve `start-browser.bat` paket indirmez.

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

GitHub Actions her push'ta macOS ve Windows üzerinde paketlenen Python 3.12 için; **Actions → Python checks → Run workflow** ile elle başlatıldığında Python 3.11, 3.12, 3.13 ve 3.14 için tam `native`/`automation` bağımlılıklarını kurar, paket tutarlılığını ve yerel pencere motorunun yüklenmesini doğrular, testleri çalıştırır. Bu testler canlı ERP oturumu, veritabanı hesabı veya Google anahtarı gerektirmez. Gerçek masaüstü, OCR, sürücü ve ağ bağlantıları hedef bilgisayarda ayrıca doğrulanmalıdır; CI bunların yerini tutmaz.

Uygulama localhost üzerinde kullanılır; bu sürümü port yönlendirmeyle internete veya ortak ağa açmayın. Masaüstü robotu çalışırken hedef pencere odağı ve ekran düzeni korunmalıdır. İptal isteği bir sonraki denetim noktasında uygulanır; tamamlanmış dış işlemleri geri almaz.

## Rehberler

- [Adım rehberi: 63 adım, test etme, sürükle-bırak, AutoHotkey karşılıkları](docs/adimlar.md)
- [Google Sheets bağlantısı: Apps Script veya servis hesabı](docs/google-sheets.md)
- [Kullanıcı girişi, lisans ve çevrimdışı kullanım](docs/lisans.md)
- [Terminalsiz masaüstü uygulaması ve kurulum paketi](docs/masaustu-dagitim.md)
- [Otomatik güncelleme ve yeni sürüm yayımlama](docs/guncelleme-mimarisi.md)
- [Kurulum, macOS/Windows izinleri ve bağlantılar](docs/kurulum.md)
- [ERP penceresini tanıtma, alan kimliği ve Sheets hücresini kullanma](docs/pencere-tanitma.md)
- [Sheets satırları, boş/Bekliyor koşulu ve iç içe döngüler](docs/sheets-satir-dongusu.md)
- [Akış oluşturma, değişkenler ve raporlar](docs/akislar.md)
- [Salt okunur veritabanı hesabı](docs/veritabani.md)
- [Mimari ve genişletme](docs/mimari.md)
- [GitHub remote ve push](docs/github.md)
