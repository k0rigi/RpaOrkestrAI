# RpaOrkestrAI

**macOS ve Windows için Python tabanlı, yerelde çalışan görsel RPA uygulaması.** Uygulama sahipleri Studio üzerinden otomasyon adımları ekler, koşul ve döngüleri düzenler, akışları kaydeder ve çalıştırır. Çalışma çıktıları CSV olarak departmanlara verilebilir; akış tanımları JSON olarak başka kurulumlara taşınabilir.

Studio, FastAPI üzerinden sunulan bir web arayüzüdür. İsterseniz aynı arayüzü pywebview ile yerel uygulama penceresinde açabilirsiniz. Masaüstü işlemleri uygulamanın çalıştığı bilgisayarda gerçekleşir.

## Masaüstü uygulaması olarak kullanım

Hazır kurulum dosyaları için **[RpaOrkestrAI indirme sayfası](https://orkestrai.net/rpa/)** kullanılır. GitHub'daki alternatif dağıtım yeri [Releases](https://github.com/k0rigi/RpaOrkestrAI/releases) bölümüdür; özel depoya erişim için GitHub hesabınızla giriş yapın.

- **Windows:** `RpaOrkestrAI-Setup-0.9.15-Windows-x64.exe` dosyasını çalıştırın; ardından masaüstündeki **RpaOrkestrAI Studio** kısayolunu açın.
- **MacBook (Apple Silicon: M1 ve sonrası):** `RpaOrkestrAI-0.9.15-macOS-arm64.dmg` dosyasını açın, içindeki **RpaOrkestrAI.app** uygulamasını **Applications** kısayoluna sürükleyin; `/Applications/RpaOrkestrAI.app` üzerinden açın. Bu paket Intel Mac için değildir.

**0.9.6 ile her uygulama açılışında kullanıcı adı ve şifre yeniden istenir.** Girişte lisans süresi ve yetkiler orkestrai.net üzerinden kontrol edilir; oturum diske kaydedilmez. Kullanıcının firmasında ve kendi hesabında **MOD_RPA** modülünün açık, firma lisans süresinin dolmamış olması gerekir. Süresi dolmuş veya lisansı tanımlı olmayan kullanıcıya uygulama uyarı verip kapanır. **0.8.0 ile** uygulama her açılışta orkestrai.net'ten onay alır (internet gerekir), açıkken bağlantı kesilirse en fazla 60 dakika çalışır ve bir hesap aynı anda tek bilgisayarda kullanılır; 0.8.0'dan eski sürümlere lisans verilmez. [Kullanıcı girişi ve lisans](docs/lisans.md).

Bu paketler kendi Python 3.12 yorumlayıcısını içerir ve terminal açmadan çalışır; bilgisayara ayrıca Python 3.14 kurulması onları etkilemez. **Code → Download ZIP** kaynak kod indirmesidir. `start.command` ve `start.bat`, terminale bağlı geliştirme başlatıcılarıdır; terminal kapatılırsa bu şekilde açılan süreç de kapanabilir. Yeni derlemelerin paketleri **Actions → Build desktop apps → Artifacts** bölümünde bir gün durur; yayınlanan güncel sürüm orkestrai.net/rpa adresindedir. [Masaüstü dağıtım rehberi](docs/masaustu-dagitim.md).

**0.1.x kullananlar güncel sürümü bir kez elle kurmalıdır.** 0.2.0 ve sonraki kurulu uygulamalar açılışta yeni sürümü arka planda kontrol edip doğrulayarak indirir; hazır güncellemeyi sonraki açılışta kurar. Güncelleme indirilemezse mevcut sürüm kullanılmaya devam eder; akışlar ve bağlantı ayarları korunur. Studio'nun açılması için lisans doğrulaması nedeniyle internet bağlantısı gerekir. Kendi akışınıza eklediğiniz adımlar yerel kalır; kodla geliştirilen yeni adım türleri yeni uygulama sürümü yayımlandığında diğer kurulumlara ulaşır. [Güncelleme mimarisi](docs/guncelleme-mimarisi.md).

**0.9.6:** Metin okuma adımlarında **Bölge çiz** ile ekran görüntüsü üzerinde dikdörtgen seçebilirsiniz. Pencereye göre bölgeler pencere taşındığında da pencereye bağlı kalır. **Tabloya değer yaz** adımı uygulamanın düzenlenebilir tablo hücreleri sunmasını gerektirir; bu erişimi sunmayan tablolarda işlem anlaşılır bir hatayla durur.

**0.9.7:** Tabloya yazmada **Ekranda seç** ile referans görsel, konum veya alan kimliği kullanılabilir. Ana form satır, sütun ve değerden oluşur; ayrıntılı ayarlar **Diğer seçenekler** altındadır. 0.9.6 ile kaydedilmiş otomatik/adla tablo seçimi korunur. Adım açıklamaları firma ve uygulamadan bağımsız olacak şekilde genelleştirilmiştir.

**0.9.12:** Tablo önizlemesinde **Başlık yap** ile gerçek başlık satırını seçebilirsiniz; başlık yoksa **Başlık yok** seçin. Başlık ve öncesi veri sayılmaz, ilk kayıt **Veri 1 / Satır 1** olur. Başlıktan önce boş satır bulunan kopyalar desteklenir; okuma ve yazma aynı satır ayrımını kullanır. `sutun_7` gibi numaralı sütun adları çalışmaya devam eder.

**0.9.15:** Yeni **Metni bul, tıkla ve yaz** adımı: pencerede bir alan çizin; adım yazdığınız metni içeren yazıyı (bir parça yeterli, ör. `İad` → `İade`) her çalışmada OCR ile bulur; yazının ortasına veya **Sütun metni** (başlık) ile **Satır metni**nin kesişimine tıklar ve değeri yazar. Boş tablo hücreleri için de kullanılır. Metin bulunamazsa veya birden fazla yerde görünürse tıklamaz. Bu adımı kullanan akışlar 0.9.15 veya üzeri gerektirir. [Ayrıntılı kullanım](docs/pencere-tanitma.md#metni-bul-tıkla-ve-yaz-0915).

**0.9.14:** Boş hücreye yazmada **Tabloyu seç** noktası geniş tablolarda hedef sütundan uzak bir sütunda olsa da tablo doğru eşleştirilir; “Miktar / Onaylanan Miktar” gibi iç içe başlıklar artık sütun sırasını bozmaz. Hedef sütun başlığı okunamazsa hata, ekranda okunan başlıkları listeler. Uygulama simgesi Studio'daki siyah-sarı işaretle aynı oldu; pencere başlık çubuğu yan menüyle aynı koyu renktedir (Windows 11'de tam renk, Windows 10'da koyu başlık, macOS'ta koyu ve saydam başlık).

**0.9.13:** **Tabloya değer yaz** boş hücreye de yazar. Hücrenin yeri her çalışmada, ekrandaki sütun başlığı ile aynı satırda tabloda tek olan dolu bir hücrenin (ör. kayıt kodu) kesişiminden bulunur; ekran ölçeği veya sütun genişliği değişse de kayıtlı koordinat kullanılmaz. Boş görünmesi gereken yerde metin varsa yazılmaz. Akış dosyası değişmez. [Ayrıntılı kullanım](docs/pencere-tanitma.md#tabloya-değer-yaz-096).

**0.9.11:** **Tabloya değer yaz** sadeleştirildi: **Tabloyu seç**, ardından satır, sütun ve değer. “Diğer seçenekler” ve elle X/Y girişi kaldırıldı. Hücre düzenlemesi otomatik doğrulanır; değişkenin değeri bir kez yazılır ve tablonun tamamı yeniden okunarak kontrol edilir. Uzun değer ekranda kesilse de pano doğrulaması yapılır. Tablo seçiminde başlık ayarı, seçimden sonra ilk veri satırı görünür. [Ayrıntılı kullanım](docs/pencere-tanitma.md#tabloya-değer-yaz-096).

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
- uygulama ve sistem: uygulama/dosya/adres aç (çift tıklama gibi), komut / script çalıştır (terminal veya PowerShell gibi), uygulamayı kapat, pano
- veritabanı: SQL Server, PostgreSQL, MySQL, Oracle ve SQLite'ta salt okunur SQL sorgusu
- dosya ve Excel: .xlsx/CSV oku-yaz, dosya listele, kopyala/taşı/sil, indirmeyi bekle
- veri: hesapla, metin, tarih, liste
- akış: tekrarla, döngüden çık, hata olursa, başka akışı çalıştır, akışı bitir
- etkileşim ve web: mesaj ve girdi kutusu, HTTP/API

**0.7.1 ile akış iki görünümde düzenlenir.** **Liste** görünümü alt alta kartlardır. **Diyagram** görünümü aynı adımları n8n'deki gibi soldan sağa düğümler ve bağlantı çizgileriyle gösterir: koşul ve hata dalları ayrı satırlarda, döngüler "Sonraki tur" dönüş çizgisiyle çizilir. Çizgilerdeki **+** düğmesiyle araya adım eklenir, düğümler sürüklenerek taşınır. Bir kutunun sağındaki noktayı başka bir kutuya sürükleyince akış oradan devam eder (**Adıma git**). Gerideki bir adıma dönmek için adımları kopyalamak gerekmez. Çizgideki **×** bağlantıyı kaldırır ve o yol orada biter; biten dal diğer dalla birleşmez. Son çalışmada her adımın kaç kez çalıştığı ✓ ve hata verdiği ✗ olarak düğümün üzerinde görünür; çalışma ayrıntısındaki **Diyagramda göster** hatalı adımı seçili açar. Çalışma mantığı iki görünümde de aynıdır.

**Görünüm.** Arayüz teknik çizim görünümündedir: kareli kâğıt zemin, mürekkep çizgili kutular ve tek bir vurgu rengi. Sağ üstteki ay/güneş düğmesi **açık** (çizim kâğıdı) ve **koyu** (blueprint) tema arasında geçer; **Ayarlar → Görünüm** altında bilgisayarın ayarını izleyen **Sistem** seçeneği de vardır. Diyagramda kutuları sürükleyerek istediğiniz yere taşıyabilirsiniz; bir **+** üzerine bırakılan kutu akışta o noktaya geçer.

**Bağlantılar adımın içindedir.** Google Sheets ve veritabanı adımlarının ilk alanı **Bağlantı**'dır. Bağlantı orada oluşturulur, seçilir ve düzenlenir; aynı türde birden fazla adlandırılmış bağlantı olabilir (ör. "Satış tablosu", "İade tablosu"). Bağlantı seçilmeyen adım, o türün varsayılan bağlantısını kullanır. Editördeki **Bağlantılar** düğmesi tüm bağlantıları listeler. Şifre, anahtar ve dosya yolları yalnız o bilgisayarda saklanır; dışa aktarılan akışta yalnız bağlantının kimliği bulunur. 0.6'daki genel Sheets ve veritabanı ayarları ilk açılışta otomatik olarak varsayılan bağlantılara dönüştürülür.

**Adlar.** Bir adımın sonucuna verdiğiniz ad alanına yalnız ad yazılır (ör. `erp_window`); `${erp_window}` yazılırsa uygulama düzeltir. Pencere adımlarında pencere, önceki **Pencereyi tanı** adımlarında verilen adlardan oluşan listeden seçilir. Geçersiz bir ad, hangi adımda ve hangi alanda olduğu belirtilerek bildirilir.

**Hareketleri kaydet**, bir işi fare ve klavyeyle bir kez yapmanızı adımlara çevirir; kayıt F9 ile biter. Adımlar tutup sürüklenerek yer değiştirir ve döngü, koşul veya hata bloklarının içine bırakılabilir. **Bu adımı test et**, seçili adımı tek başına çalıştırır; pencereyi, sabit değerleri ve tablodaki ilk satırı önceki adımlardan kendisi alır, sizden değer istemez. Tıklama ve alan doldurma adımlarında **Yeri göster**, tıklamadan fareyi hedefe götürür. Her adımın ayarlarında kısa bir **Nasıl kullanılır?** kutusu ve her alanın altında açıklaması bulunur. **Çalıştır** adımları gerçekten uygular; **Önizleme (ekranı kullanmadan)** seçeneği ekran, dosya ve bağlantı adımlarını atlar. Tüm adımlar, AutoHotkey karşılıkları ve örnekler [adım rehberindedir](docs/adimlar.md). İlk denemeler için [examples/adim-turu.json](examples/adim-turu.json) ve [examples/metin-editoru.json](examples/metin-editoru.json) akışlarını içe aktarabilirsiniz.

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
| Akış tasarımı | Adım ekleme, sıralama, düzenleme; iç içe koşul ve döngüler; her adımda **Sonraki adıma geçmeden bekle** süresi |
| Notlar | Akışın bir bölümünü seçip başlıklı, renkli not ekleme; diyagramda çerçeve, listede bant olarak görünür |
| Zamanlayıcı | Akışı bir kez, her gün, haftanın belirli günlerinde veya belirli aralıklarla çalıştırma; başlamadan önce iptal edilebilir geri sayım; çakışan akışlar için öncelik, gecikme ve süre sınırı, çakışma uyarısı ve 24 saatlik plan |
| Akış yönetimi | Kaydetme, açma, JSON içe/dışa aktarma ve departman bilgisi |
| Çalıştırma | Arka planda çalışma, adım günlükleri, geçmiş ve iptal isteği |
| Raporlar | Akış verisinden CSV üretme ve indirme |
| Veritabanı | **Veritabanı sorgusu** ile SQL Server, PostgreSQL, MySQL / MariaDB, Oracle veya SQLite'ta tek bir `SELECT` sorgusu çalıştırma; `${değişken}` değerleri parametre olarak gönderilir, sonuç **Her satır için** döngüsüne verilir. Yalnız okuma yapılır; değiştiren sorgular reddedilir. Bağlantı sunucu, kullanıcı ve şifreyle formdan kurulur. [Adım rehberi](docs/adimlar.md#veritabanı) |
| Kayıtlı şifreler | ERP girişi gibi işler için şifreyi işletim sisteminin kasasında (Windows Kimlik Bilgisi Yöneticisi, macOS Anahtar Zinciri) tutma; adımda `${sifre.ad}` ile kullanma, günlükte gizleme |
| Script ve programlar | **Uygulama, dosya veya adres aç** programı, belgeyi veya klasörü çift tıklar gibi açar. Windows'ta programları başlatmak için masaüstü kısayolunu (`.lnk`) seçin; kısayolun parametreleri ve çalışma klasörü korunur. **Komut / script çalıştır** terminal (cmd / Terminal) veya PowerShell komutunu ya da seçilen `.py`, `.ps1`, `.bat`, `.vbs`, `.sh` script'ini çalıştırır, bitmesini bekler ve çıktısını akışta kullanır |
| Masaüstü | Geri sayımla fare konumu alma, alanı uygulama yapısındaki kimliğiyle bulma, fareyle görsel alanı seçme; hedefe tıklama, alan doldurma ve platforma uygun kısayollar |
| Ekrandaki metinle yazma | **Metni bul, tıkla ve yaz** ile çizilen alanda OCR ile metni bulup üzerine ya da sütun başlığı ile satır değerinin kesişimine (boş hücre dahil) tıklama ve değer yazma; koordinat kaydedilmez (0.9.15+) |
| Uygulama tabloları | **Tablodan değer oku** ile uygulama tablosundaki hücreyi sütun adıyla okuma ve satır sayma; **Tabloya değer yaz** ile erişilebilir tablo hücresini satır/sütun veya benzersiz kayıt değeriyle bulup yazma ve doğrulama (0.9.6+) |
| Görsel algılama | OpenCV şablon eşleştirme, OCR metni ve koşullu kararlar |
| Google Sheets | Adlandırılmış sütunlarla satır okuma, boş durumları koruma; hücre okuma/yazma ve servis katmanında satır ekleme |
| Web | **HTTP isteği gönder** ile web servisleri (API); eski akışlardaki tarayıcı (Playwright) adımları çalışmaya devam eder |

Bu sürüm her bilgisayarda orkestrai.net hesabıyla açılır; akışlar ve ayarlar o bilgisayarın çalışma alanında kalır. Departman alanı raporları ve akışları sınıflandırır; akış bazında erişim yetkisi oluşturmaz. Zamanlayıcı bu bilgisayarda, Studio açıkken çalışır; Studio isterseniz bilgisayar açılınca simge durumunda başlar ([zamanlayıcı rehberi](docs/zamanlayici.md)). Merkezi çok kullanıcılı sunucu ve uzak robot yönetimi bu sürümün kapsamı dışındadır.

## İlk gerçek otomasyon

Masaüstü ERP için [pencere tanıtma rehberiyle](docs/pencere-tanitma.md) başlayın. Daha kapsamlı işlemler için aşağıdaki sırayı izleyin. Tabloda ve rehberlerde anlatılan mevcut motor işlemleri, eski veya içe aktarılan akışlarda desteklenmeye devam eder.

1. [Kurulum rehberindeki](docs/kurulum.md) otomasyon paketlerini ve gerekli sistem araçlarını kurun.
2. Sheets adımını ekleyip **Bağlantı** alanından bağlantı oluşturun.
3. Yeni akışa ad ve departman girin. Adım kitaplığından veri okuma adımını ve ardından bir döngü ekleyin.
4. Çıktı değişkenlerini sonraki adımlara `${orders}` veya `${item.MATERIAL}` biçiminde bağlayın.
5. ERP tıklama, alan doldurma ve arama adımlarını döngünün içine yerleştirin. OCR sonucuna göre koşul ekleyin.
6. Önizleme ile adım yapısını inceleyin; ardından hedef uygulama hazırken gerçek çalıştırmayı başlatın.
7. CSV raporu ekleyip çalışma çıktısını ilgili departmanla paylaşın.

Masaüstü Studio, gerçek akış ve adım testleri başlamadan önce otomatik küçülerek ekranı hedef uygulamaya bırakır. Zamanlanmış akışlarda da aynı davranış geçerlidir; ilk adım küçülme tamamlandıktan sonra çalışır. Önizlemede Studio açık kalır. Sonucu görmek veya çalışmayı durdurmak için görev çubuğundan / Dock'tan Studio'yu açabilirsiniz; çalışma sonunda pencere kendiliğinden öne gelmez. Tarayıcı sürümünde pencereyi elle küçültün.

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

Adlandırılmış bağlantılar `data/connections.json`, uygulama ayarları `data/settings.json`, zamanlamalar `data/schedules.json` içindedir. `RPA_DATABASE_URL` ve `RPA_GOOGLE_CREDENTIALS_PATH` gibi `.env` değerleri yalnız ilk açılışta varsayılan bağlantıya dönüştürülür; sonrasında bağlantıyı adımın **Bağlantı** alanından veya **Bağlantılar** penceresinden düzenleyin. `data/` ile `.env` Git'e eklenmez. Yerel ayar dosyası bir şifre kasası değildir; bilgisayar hesabı ve dosya erişimleri bu bilgileri korur.

Akış dışa aktarımı bağlantı bilgilerini içermez; adımda yalnız bağlantının kimliği kalır. Akışı başka bir bilgisayara aktardığınızda adım "bağlantı bu bilgisayarda yok" uyarısı gösterir; orada bağlantıyı seçin veya oluşturun. Adımların kullandığı referans görseller dışa aktarılan dosyaya eklenir ve içe aktarırken şablon klasörüne yazılır; aynı adla farklı bir görsel varsa üzerine yazılmaz, yeni görsel ek bir numarayla kaydedilir. Akış dosyası en fazla 16 MB olabilir. Not veya **Sonraki adıma geçmeden bekle** süresi içeren akış dosyaları 0.8.6 ve önceki sürümlerde içe aktarılamaz. Ancak adımlara sizin yazdığınız sabit metinler, değişkenler ve iş verileri JSON içinde yer alabilir. Çalışma günlükleri ve CSV dosyaları da iş verisi içerebilir; paylaşılacak çıktıyı inceleyin.

## Geliştirme ve doğrulama

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

GitHub Actions her push'ta macOS ve Windows üzerinde paketlenen Python 3.12 için; **Actions → Python checks → Run workflow** ile elle başlatıldığında Python 3.11, 3.12, 3.13 ve 3.14 için tam `native`/`automation` bağımlılıklarını kurar, paket tutarlılığını ve yerel pencere motorunun yüklenmesini doğrular, testleri çalıştırır. Bu testler canlı ERP oturumu, veritabanı hesabı veya Google anahtarı gerektirmez. Gerçek masaüstü, OCR, sürücü ve ağ bağlantıları hedef bilgisayarda ayrıca doğrulanmalıdır; CI bunların yerini tutmaz.

Uygulama localhost üzerinde kullanılır; bu sürümü port yönlendirmeyle internete veya ortak ağa açmayın. Masaüstü robotu çalışırken hedef pencere odağı ve ekran düzeni korunmalıdır. İptal isteği bir sonraki denetim noktasında uygulanır; tamamlanmış dış işlemleri geri almaz.

## Rehberler

- [Adım rehberi: 65 adım, test etme, sürükle-bırak, AutoHotkey karşılıkları](docs/adimlar.md)
- [Google Sheets bağlantısı: Apps Script veya servis hesabı](docs/google-sheets.md)
- [Kullanıcı girişi, lisans, tek bilgisayar kuralı ve internet gereksinimi](docs/lisans.md)
- [Terminalsiz masaüstü uygulaması ve kurulum paketi](docs/masaustu-dagitim.md)
- [Otomatik güncelleme ve yeni sürüm yayımlama](docs/guncelleme-mimarisi.md)
- [Kurulum, macOS/Windows izinleri ve bağlantılar](docs/kurulum.md)
- [ERP penceresini tanıtma, alan kimliği ve Sheets hücresini kullanma](docs/pencere-tanitma.md)
- [Sheets satırları, boş/Bekliyor koşulu ve iç içe döngüler](docs/sheets-satir-dongusu.md)
- [Akış oluşturma, değişkenler ve raporlar](docs/akislar.md)
- [Zamanlayıcı: akışı belirli zamanlarda çalıştırma, bilgisayar açılınca başlatma](docs/zamanlayici.md)
- [Salt okunur veritabanı hesabı](docs/veritabani.md)
- [Mimari ve genişletme](docs/mimari.md)
- [GitHub remote ve push](docs/github.md)
