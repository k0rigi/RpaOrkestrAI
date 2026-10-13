# Ajan geliştirmesi — 13 Ekim 2026

Bu rapor yerel geliştirme durumudur. Yeni kurulum paketi veya ajan sunucu hizmeti
henüz yayımlanmadı; Studio sürümü hâlâ 0.9.22. Kapasite tanılama iş akışı dışında
bu özellik için canlı sunucu işlemi yapılmadı.

## Aşamalar

| Aşama | Yerel sonuç | Başlıca dosyalar |
| --- | --- | --- |
| 1 — Çekirdek | İzin/risk denetimi, sahte sağlayıcı, onay/soru, sınırlar, iptal ve masaüstü sırası testli | `agents/models.py`, `risk.py`, `policy.py`, `runner.py`, `tools.py`, `storage.py`, `api.py`, `dispatch.py`, `engine.py`, `licensing.py` |
| 2 — Sağlayıcı ve Studio | Bulut/yerel/kurum bağlantısı, yazma amaçlı anahtar alanı, zaman çizelgesi, form ve soru/onay kartları hazır | `agents/provider_adapters.py`, `connections.py`, `shared_provider.py`, `central.py`, `studio_api.py`, `vault.py`, `static/agents.js`, `agents.css`, `app.py` |
| 3 — Organizasyon | Tek yönetici, departmanlara görev devri, ortak bütçe, kuyruk ve insan görevleri hazır | `agents/organization.py`, `runner.py`, `models.py`, `team_api.py`, `static/agent-team.js`; sunucuda `api/ajanlar/` |
| 4 — Performans | Görev kayıtlarından ajan/departman ve insan ölçümleri, tarih filtresi, fiyat tahmini, CSV hazır | `agents/metrics.py`, `metrics_api.py`, `static/agent-metrics.js`, `agent-metrics.css`; sunucuda `api/ajanlar/metrics.py` |
| 5 — Ofis | Yerel Three.js ve boş ofis, koyu/açık tema, 2D/listeli yedek hazır; yerleşim onayı bekleniyor | `agents/office.py`, `static/office.js`, `office.css`, `vendor/three/`, `package_check.py`, `scripts/build_desktop.py` |
| 6 — Akış içi AI | `ai.ask`, araçsız çağrı, şema doğrulaması, bilinmeyen önizleme sonucu ve form hazır | `actions/ai.py`, `agents/workflow_ai.py`, `schema.py`, `catalog.py`, `guide.py`, `engine.py`, `static/app.js` |
| 7 — Zamanlanmış ajan | Başlatılmadı; ilk sürüme dahil edilmesi soruldu | Henüz değişiklik yok |

Ofis karakterleri, insan çalışanların ofiste temsili ve durum animasyonları
yerleşim onayından sonra yapılacak. İnsan hesaplarında departman alanı olmadığı
için bu aşamada insan departman performansı türetilmiyor. Ajan ayrıntılı kayıtları
yerelde kalıyor; tüm bilgisayarların ajan verilerini web panelinde birleştiren
raporlama bu kapsamda yayımlanmış değildir.

## Doğrulama

- Studio tam ağsız test koşusu: **1.662 geçti, 39 atlandı**; `RPA_UI_TESTS=1`.
- Sunucu ajan/ekip/LLM testleri: **123 geçti**; Python 3.6 uyumluluğu statik olarak denetlendi.
- Ruff: temiz. `app.js`, `agents.js`, `agent-team.js`, `agent-metrics.js`, `office.js`: Node sözdizimi kontrolü temiz.
- Son ortak model tekrar deneme düzeltmesi ayrıca hedefli regresyonlarla kontrol edildi; onay kararı ve tüketimi tekrar edilmiyor.
- UI testleri Chromium'da sahte HTTP yanıtlarıyla çalıştı; gerçek sağlayıcı/ERP hesabı kullanılmadı.
- Gerçek Windows WebView2, macOS WKWebView ofis açılışı, paketlenmiş EXE/DMG öz testi ve iki platform CI sonuçları henüz tamamlanmadı.
- Gerçek MariaDB geçişi, Ollama çıkarımı ve sunucu hizmet kurulumu henüz yapılmadı.

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

- Sunucu yükseltmesinin tamamlandığının bildirilmesi. Başlangıç önerisi **4 vCPU, 16 GB RAM**; GPU zorunlu değil. 8 GB daha dar başlangıç seçeneğidir. Mevcut yaklaşık 27 GB boş disk ilk küçük model için yeterlidir; gerçek kullanım ölçülecek.
- Ofis yerleşimi onayı ve karakter/animasyon aşaması.
- Zamanlayıcı kapsamına yanıt.
- Canlı firmanın/kullanıcının `MOD_AJAN` kaydı ve bitiş tarihi için somut lisans planı; seçilen onaycının kalıcı hesap kimliğine bağlanması.
- GitHub Actions üzerinden kurulum/yayın öncesi inceleme, gerçek model ölçümü, iki platform CI ve paket öz testleri.
- Yeni sürüm numarası, imzalı dağıtım ve geri dönüş doğrulaması. `credentials/` dosyaları okunmadı veya paketlenmedi.

Kullanım ayrıntıları: [Ajanlar ve dijital ekip](ajanlar.md).
