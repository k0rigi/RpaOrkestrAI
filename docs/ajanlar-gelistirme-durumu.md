# Ajan geliştirmesi — 14 Ekim 2026

Bu rapor yayın hazırlığının durumudur. 0.9.23 kurulum paketi henüz yayımlanmadı.
Ajan ve ekip API kodu normal sunucu dağıtımıyla yayımlandı; mevcut API hizmetinin
yeniden başlatılması ve kimlik kapısı doğrulandı. Ortak model kurulumu ve açıkça
onaylanan lisans ataması ayrıca tamamlanacak.

## Aşamalar

| Aşama | Yerel sonuç | Başlıca dosyalar |
| --- | --- | --- |
| 1 — Çekirdek | İzin/risk denetimi, sahte sağlayıcı, onay/soru, sınırlar, iptal ve masaüstü sırası testli | `agents/models.py`, `risk.py`, `policy.py`, `runner.py`, `tools.py`, `storage.py`, `api.py`, `dispatch.py`, `engine.py`, `licensing.py` |
| 2 — Sağlayıcı ve Studio | Bulut/yerel/kurum bağlantısı, yazma amaçlı anahtar alanı, zaman çizelgesi, form ve soru/onay kartları hazır | `agents/provider_adapters.py`, `connections.py`, `shared_provider.py`, `central.py`, `studio_api.py`, `vault.py`, `static/agents.js`, `agents.css`, `app.py` |
| 3 — Organizasyon | Tek yönetici, departmanlara görev devri, ortak bütçe, kuyruk ve insan görevleri hazır | `agents/organization.py`, `runner.py`, `models.py`, `team_api.py`, `static/agent-team.js`; sunucuda `api/ajanlar/` |
| 4 — Performans | Görev kayıtlarından ajan/departman ve insan ölçümleri, tarih filtresi, fiyat tahmini, CSV hazır | `agents/metrics.py`, `metrics_api.py`, `static/agent-metrics.js`, `agent-metrics.css`; sunucuda `api/ajanlar/metrics.py` |
| 5 — Ofis | Yerleşim onaylandı; karakterler, durum animasyonları, insan görünümü, salt okunur ayrıntı paneli ve native paket kontrolü hazır | `agents/office.py`, `static/office.js`, `office.css`, `vendor/three/`, `native_office_check.py`, `scripts/check_native_office.py`, `package_check.py`, `scripts/build_desktop.py` |
| 6 — Akış içi AI | `ai.ask`, araçsız çağrı, şema doğrulaması, bilinmeyen önizleme sonucu ve form hazır | `actions/ai.py`, `agents/workflow_ai.py`, `schema.py`, `catalog.py`, `guide.py`, `engine.py`, `static/app.js` |
| 7 — Zamanlanmış ajan | İlk sürüm Studio'dan elle başlatma önerisini esas alıyor; zamanlanmış ajanlar ayrı aşamada | Henüz değişiklik yok |

Ofis karakterleri, insan çalışanların ofiste temsili ve durum animasyonları
yerleşim onayıyla tamamlandı. İnsan hesaplarında departman alanı olmadığı
için bu aşamada insan departman performansı türetilmiyor. Ajan ayrıntılı kayıtları
yerelde kalıyor; tüm bilgisayarların ajan verilerini web panelinde birleştiren
raporlama bu kapsamda yayımlanmış değildir.

## Doğrulama

- Studio tam ağsız test koşusu: **1.730 geçti, 39 atlandı**; `RPA_UI_TESTS=1`. Son insan durumu biçim denetimi ayrıca 15 ofis testiyle doğrulandı.
- Sunucu ajan/ekip/LLM, kurulum ve lisans atama testleri: **247 geçti**. Python 3.6 uyumluluğu statik olarak denetlendi.
- Ruff: temiz. `app.js`, `agents.js`, `agent-team.js`, `agent-metrics.js`, `office.js`, `native-office-check.js`: Node sözdizimi kontrolü temiz.
- Son ortak model tekrar deneme düzeltmesi ayrıca hedefli regresyonlarla kontrol edildi; onay kararı ve tüketimi tekrar edilmiyor.
- UI testleri Chromium'da sahte HTTP yanıtlarıyla çalıştı; gerçek sağlayıcı/ERP hesabı kullanılmadı.
- Gerçek macOS WKWebView kaynak çalışması: **9/9 kontrol geçti**, 633 WebGL çizim çağrısı, hata yok; sürüm 0.9.23, `frozen=false`. Paketlenmiş uygulama kanıtı değildir. Ofis Chromium testleri **10/10**, native kontrol regresyonları **56** test geçti.
- Gerçek Windows WebView2, paketlenmiş EXE/DMG öz testi ve iki platform CI sonuçları henüz tamamlanmadı.
- İlk Windows CI koşusu vendor dosyalarının CRLF dönüşümünü, iki testte UTF-8 belirtilmemesini ve eşzamanlı bağlantı kaydı/iptal yarışını ortaya çıkardı. Orijinal vendor baytları `.gitattributes` ile korunuyor; üretimde SHA denetimi gevşetilmedi. Bağlantılar ortak kilit ve benzersiz geçici dosya kullanıyor; iptal kontrol sinyali alt akışta da iptal sayılıyor. Ofis/native 50, bağlantı/kayıt/ajan 76, akış AI 52 hedefli test geçti; yeni tam koşu ve iki platform CI sonucu bekleniyor. Başarısız koşu yayın kanıtı sayılmaz.
- Sunucu API dağıtımı başarılı: [0033c5b dağıtım kaydı](https://github.com/k0rigi/orkestrai/actions/runs/38476658847). Gerçek MariaDB lisans ön kontrolü, Ollama çıkarımı ve model hizmet kurulumu henüz tamamlanmadı.

## Güvenlik kontrol listesi

1. Akış ve alt akış izinleri sunucuda zorlanıyor; dinamik alt akış kimliği ve izin dışı erişim reddediliyor.
2. Risk kararı modelden alınmıyor; onay akış/girdi/oturum bağlarıyla tek kullanımlık tüketiliyor. Hata yerel onaya dönüşmüyor.
3. Araç çıktısı güvenilmeyen veri olarak işaretleniyor; içerik izin veya onay kurallarını değiştiremiyor.
4. Varsayılan kasa sırları ve sağlayıcı anahtarları ilk istekten önce maskeleniyor; kasa doğrulanamazsa çağrı duruyor.
5. Bulut uçları sabit HTTPS; yerel bağlantılar loopback. Kurum modelinin yerel çalışması ve bulutun kapalı olması her çıkarım öncesinde kontrol ediliyor.
6. Hedef/pencere hatası tahmini tıklamaya dönüşmüyor; aynı başarısız hedef girdileri körlemesine tekrarlanmıyor.
7. Süre, tur, akış, token ve alt görev bütçeleri var. Ortak model bağlamı ve raporlanan token kullanımı doğrulanıyor.
8. Başlatan kimlik, araçlar, akışlar ve onay olayları kayıtlı. Yerel ajan ayrıntıları sunucu performans paneline taşınmıyor.
9. Yeni Studio uçları lisans/Origin/gövde sınırlarının arkasında. Model ve kullanıcı metni HTML olarak işlenmiyor.
10. Yönetici akış çalıştıramıyor; alt ajanın izinleri görev devriyle genişlemiyor. Toplam bütçe ve tek yönetici ilişkisi denetleniyor.
11. Ofis ve performans görev başlatmıyor. Three.js ve kaynakları yerelden, lisans ve bütünlük kontrolüyle paketleniyor.
12. Gizli bilgi, onay yarışları, iptal, lisans, bütçe, firma sınırı, CSV formülleri ve protokol hataları regresyon testleriyle kapsanıyor.

## Yayın için açık işler

- Sunucu yükseltmesi salt okunur Actions tanılamasıyla doğrulandı: **6 mantıksal işlemci, 7,5 GiB toplam / 6,8 GiB kullanılabilir RAM, 81,6 GiB boş disk**, AlmaLinux 8.10 x86_64. NVIDIA yönetim aracı bulunmaması GPU olmadığını kanıtlamaz; ilk model CPU ile, tek çıkarım sırasında ölçülecek. Donanım artışı tek başına model hızı veya araç çağrısı doğruluğunun doğrulandığı anlamına gelmez. [Tanılama kaydı](https://github.com/k0rigi/orkestrai/actions/runs/38472031645).
- Mevcut web hizmeti ve lisans metadata incelemesi tamamlandı; mevcut systemd web hizmeti korunacak. Ortak model henüz kurulu değil. [İnceleme kaydı](https://github.com/k0rigi/orkestrai/actions/runs/38472777304).
- Ofis karakterleri ve yerel pencere testi tamamlandı; paketler içindeki gerçek motor kontrolleri bekliyor.
- Seçilen firma/kullanıcı için `MOD_AJAN` bitişini mevcut RPA firma bitişiyle eşleme ve tek onaycı bağlama işlemi kullanıcı tarafından onaylandı; canlı atama henüz yapılmadı. Hesap kimlikleri ve lisans tarihleri genel uygulama koduna veya bu açık depo belgesine gömülmez.
- Sunucu seed'i yalnız modül kataloğunu oluşturuyor, lisans vermiyor. Bu depoda genel modül atama ekranı/yazma API'si bulunmadığından canlı atama ayrıca denetlenen yönetim işlemiyle yapılmalı; mevcut panelden atanabildiği doğrulanmadı.
- GitHub Actions üzerinden kurulum/yayın öncesi inceleme, gerçek model ölçümü, iki platform CI ve paket öz testleri.
- Kullanıcının seçtiği 0.9.23 sürüm numarası dört yayın dosyasına işlendi. İmzalı dağıtım ve geri dönüş doğrulaması bekliyor; `credentials/` dosyaları okunmadı veya paketlenmedi.

Kullanım ayrıntıları: [Ajanlar ve dijital ekip](ajanlar.md).
