# Mimari ve genişletme

RpaOrkestrAI, akış tasarımı ve yürütmeyi aynı yerel uygulamada toplar. Uygulama sahibi Studio'da akışı tanımlar; Python motoru tanımı doğrular, değişkenleri çözer ve ilgili adaptörleri çağırır. Çıktılar indirilebilir yerel dosyalardır.

## Katmanlar

| Katman | Sorumluluk |
| --- | --- |
| Studio arayüzü | Akış yönetimi, adım düzenleme, bağlantı ayarları, çalışma günlüğü ve rapor indirme |
| FastAPI | Yerel HTTP API, girdi doğrulama ve arayüz dosyalarını sunma |
| Akış modeli | Adım kimlikleri, parametreler, `children` / `otherwise` dalları ve yapı sınırları |
| Yürütme motoru | Değişken çözümleme, kontrol adımları, adaptör çağrıları, önizleme ve iptal |
| Adaptörler | SQLAlchemy/pandas, PyAutoGUI/OpenCV/OCR, gspread ve Playwright |
| Yerel depo | Akış, çalışma ve ayar JSON dosyaları ile CSV çıktıları |

Arayüz HTML, CSS ve JavaScript ile sunulur; geliştirmek için ayrı bir Node derleme zinciri gerekmez. pywebview aynı yerel arayüzün isteğe bağlı penceresidir. Tarayıcı görünümü ile masaüstü robotu farklı katmanlardır: Studio'yu tarayıcıda açmak, PyAutoGUI işlemlerini headless yapmaz.

## Veri yerleşimi

Varsayılan olarak çalışma klasöründe:

```text
data/
├── settings.json          # Yerel bağlantı ayarları
├── workflows/            # Kaydedilen akış JSON dosyaları
├── runs/                 # Çalışma durumları ve günlükler
└── artifacts/            # İndirilebilir çalışma çıktıları
```

`RPA_DATA_DIR` ile başka bir klasör seçilebilir. Bu klasör Git'te tutulmaz. Yedekleme gerekiyorsa uygulama kapalıyken kopyalayın; içinde bağlantı bilgileri ve iş verileri bulunabileceğini hesaba katın. Atomik dosya değiştirme yarım JSON yazımlarını azaltır; bu depolama çok süreçli veritabanı veya merkezi denetim kaydı yerine geçmez.

`WorkspaceLock`, işletim sistemi dosya kilidiyle aynı veri klasörünü iki Studio/demo sürecinin eşzamanlı açmasını engeller. Kilit alınmadan yarım kalmış çalışma kayıtları kurtarılmaz. Böylece ikinci süreç birincinin canlı çalışmasını kesilmiş sayamaz. Süreç kapandığında işletim sistemi kilidi bırakır; `.studio.lock` dosyasının diskte kalması tek başına etkin kilit olduğu anlamına gelmez.

Bu kilit veri klasörü bazındadır. Farklı klasörlerin ayrı uygulama süreçlerinde açılması mümkün olsa da aynı bilgisayarın fare ve klavyesi ortaktır. Gerçek masaüstü otomasyonları için tek robot oturumu kullanın. Açık Studio yanında bağlantısız demo denemesi `rpa-studio demo --data-dir ./data/demo-check` ile ayrı tutulabilir.

## Akış modeli

Her `Step`, `action` ve `params` alanlarını taşır. `control.for_each` ve `control.if` alt adımları `children` alanında saklar. Koşulun olumsuz dalı `otherwise` alanındadır. Bu ağaç yapısı sıralı çalışır; keyfi Python betiği ya da kabuk komutu çalıştırma adımı sunulmaz.

İşlem çıktıları çalışma kapsamındaki değişkenlere yazılır. `${orders}` referansı türünü korur; `${item.amount}` iç içe verilere erişir. Akış tanımı yalnız adımları ve sabit parametreleri taşır; adaptör bağlantıları yerel ayarlardan alınır. Bu ayrım, aynı akışın iki bilgisayarda farklı bağlantı hesaplarıyla kullanılmasını sağlar.

## Dış sistemlerle sınırlar

Veritabanı adaptörü serbest SQL kabul etmez ve sunucudaki salt okunur kullanıcıya dayanır. PostgreSQL işlemleri ayrıca salt okunur başlatılır. SQL Server'da hesap izinleri asıl sınırlamadır. [Veritabanı yetki rehberi](veritabani.md).

Masaüstü adaptörü kullanıcının açık oturumunu kontrol eder. Ekran koordinatları, Retina/DPI ölçeği, OCR dili, ERP teması ve odak gerçek makinede kalibre edilir. PyAutoGUI'nin acil durdurma mekanizması korunur. Tarayıcı adaptörü kendi Chromium oturumunu açar; mevcut kişisel tarayıcı oturumuna kendiliğinden bağlanmaz.

Tek uygulama süreci aynı anda bir akış çalıştırır; yeni çalıştırma isteği öncekinin bitmesini beklemeyi gerektirir. Bu düzen ortak fare ve klavyenin farklı akışlar tarafından eşzamanlı kullanılmasını önler. İptal, adaptör çağrıları ve adımlar arasında işlenir. Bu sürüm dış sistemlerde atomik işlem, otomatik geri alma veya tam bir kez yürütme garantisi sunmaz. Başarısız bir akışı yeniden çalıştırmak dış sistemde aynı işlemi tekrarlayabilir; iş akışına kayıt kimliği ve sonuç kontrolü gibi iş kurallarını ekleyin.

## Yerel erişim modeli

API loopback üzerinde çalışır. Kullanıcı hesabı, departman yetkileri veya uzak robot bağlantısı bulunmaz. Departman alanı düzenleme ve çıktı sınıflandırması içindir. İnternete veya ortak ağa yayınlama, kimlik doğrulama ve yetkilendirme eklenecek ayrı bir geliştirme aşamasıdır.

API şeması çalışan uygulamada `/api/openapi.json` adresindedir. Swagger arayüzü kapalıdır; Studio dış CDN betiğine ihtiyaç duymaz ve betikleri yalnız kendi kaynağından yükler. Yabancı tarayıcı kaynaklarından gelen istekler engellenir; JSON istek gövdeleri 2 MB ile sınırlıdır.

Bağlantı sırları `.env` veya yerel `settings.json` dosyasında bulunur; akış dışa aktarımına dahil edilmez. Dosya tabanlı ayarlar bir şifre kasası değildir. Çalışma günlükleri ve raporlar iş verisi içerebilir. Herhangi bir dış aktarım kullanıcının açıkça başlattığı akış adımlarından veya dosya indirmesinden kaynaklanır.

## Yeni işlem ekleme

1. Parametreleri ve sonuç veri türünü tanımlayın. Girdi doğrulaması, zaman aşımı, iptal ve tekrar çalıştırma davranışını kararlaştırın.
2. İşleme özgü dış bağlantıyı adaptör içinde uygulayın. Bağlantıları işlem sonunda kapatın; sırları günlük mesajlarına eklemeyin.
3. İşlemi motorun işlem kataloğuna ve yürütme yönlendirmesine ekleyin. Dış işlemse önizlemede atlanıp çıktısının bilinmeyen olarak taşındığını doğrulayın.
4. Studio'da alanları ve kullanıcıya dönük açıklamaları ekleyin.
5. Sahte adaptörlerle davranış testini ve gerekiyorsa hedef sistemde ayrı entegrasyon doğrulamasını yapın.

Çekirdek testler dış hesaplara ihtiyaç duymamalıdır. Örneğin bir OCR koşulu için gerçek ekran yerine sabit OCR sonucu; veritabanı sorguları için test bağlantısı kullanılabilir. Ancak bunlar gerçek ERP odağı, işletim sistemi izinleri veya sunucu kullanıcı yetkilerini doğrulamaz.
