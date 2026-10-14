# Ajan geliştirmesi — 14 Ekim 2026

Windows ve macOS için **0.9.23 yayımlandı**. İmzalı bildirim, iki tam kurulum
dosyası ve indirme sayfası HTTPS üzerinden gerçek güncelleme istemcisiyle doğrulandı.
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

Doğrulanan kurulumların kaynak commit'i
`7a993f94906edb0fd7f198ac8694042d95a30f6d`.

- Studio tam ağsız test koşusu: **1.809 geçti, 39 atlandı**; `RPA_UI_TESTS=1`, 247,60 saniye. Ruff ve altı Studio JavaScript dosyasının sözdizimi kontrolleri temiz.
- [Push kontrolleri](https://github.com/k0rigi/RpaOrkestrAI/actions/runs/38484609998): Windows ve macOS başarılı. Gerçek tarayıcı testleri dahil Windows'ta 1.833, macOS'ta 1.811 test geçti.
- [Tam Python 3.11–3.14 matrisi](https://github.com/k0rigi/RpaOrkestrAI/actions/runs/38484635370): iki platformdaki **8 işin tamamı başarılı**.
- [Son masaüstü derlemesi](https://github.com/k0rigi/RpaOrkestrAI/actions/runs/38484654544): Windows ve macOS başarılı. Her pakette `ok=true`, `frozen=true`, sürüm `0.9.23` ve **16 paket kontrolü** doğrulandı.
- Paketlenmiş uygulamada gerçek **WebView2 ve WKWebView ofis sınamaları 9/9**: yerel Three.js, tema, SVG geri dönüşü, erişilebilir liste, güvenli metin, temizlik ve salt okunur davranış başarılı; hata listeleri boş.
- GitHub artefakt özetleri, çıkarılan EXE/DMG boyut ve SHA-256 değerleri eşleşti. macOS disk imajının `hdiutil verify` kontrolü başarılı.
- Sunucu ajan/ekip/LLM, kurulum ve lisans atama testleri: **344 geçti**; Ruff ve Python 3.6 uyumluluk kontrolü temiz. [Son API dağıtımı](https://github.com/k0rigi/orkestrai/actions/runs/38485098815) başarılı.
- Canlı lisans ön kontrolü onaylanan firma, hesap ve dönem için başarılı; canlı atama henüz yapılmadı. [Ön kontrol](https://github.com/k0rigi/orkestrai/actions/runs/38477834671).

Testler gerçek müşteri ERP verisi veya sağlayıcı anahtarı kullanmaz. Hedef
bilgisayardaki gerçek ERP akışları ayrıca sınanmalıdır. Başarılı Studio ve paket
testleri, ortak sunucu modelinin çalıştığının kanıtı değildir.

## Ortak modelin durumu

4B ve 1.7B modellerin canlı araç çağrıları 90 saniyelik sınırı aşmıştır.
Son ayrıntılı ölçümde 1.7B modelin ön yüklemesi 8,22 saniyede tamamlandı;
ilk araç isteği 90,16 saniyede durdu. Ayrı 90 saniyelik akış tanılamasında
hiç yanıt parçası alınmadı. Yaklaşık dört işlemci çekirdeği kullanıldı;
bellek taşması saptanmadı. [Ölçüm ve geri alma kaydı](https://github.com/k0rigi/orkestrai/actions/runs/38485429812).

Sanal makinede SSE2 görünürken SSSE3, SSE4.1, AVX, AVX2 ve FMA görünmüyor.
Bu, fiziksel işlemcinin bu özellikleri desteklemediğini kanıtlamaz; sanal CPU
profilinin sağlayıcı tarafından kontrol edilmesi gerekir. Bu gözlem gecikmenin
tek nedeninin kesin olarak bulunduğu anlamına gelmez. Değişiklikten sonra aynı
iki turlu araç çağrısı sınaması yeniden geçmelidir; süre veya izin denetimleri
gevşetilmez. Başarısız kurulumda hizmetler ve ayarlar geri alındı; ortak model
kullanıma açılmadı, mevcut RPA hizmeti korundu.

[Yayın günündeki son sınamada](https://github.com/k0rigi/orkestrai/actions/runs/38507979262)
CPU özellikleri değişmemişti; model 7,77 saniyede yüklendi, ilk araç çağrısı
90,18 saniyede zaman aşımına uğradı. Hizmet ve ayarlar yeniden geri alındı.

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

## Yayın sonucu ve açık işler

- [0.9.23 yayın işi](https://github.com/k0rigi/orkestrai/actions/runs/38508334057) başarılı. [İndirme sayfası](https://orkestrai.net/rpa/) ve [GitHub test sürümü](https://github.com/k0rigi/RpaOrkestrAI/releases/tag/v0.9.23-test.1) kullanılabilir. Canlı dosyaların boyutları ve SHA-256 özetleri doğrulanan yerel paketlerle aynı.
- Sunucu sağlayıcısı CPU özelliklerini kontrol etmeli; ortak model gerçek araç çağrısı sınamasını geçmeden etkinleştirilmez.
- Onaylanan ayrı ajan lisansı ve tek onaycı ataması henüz uygulanmadı. Hesap kimlikleri ve tarihler genel uygulama koduna veya açık depo belgelerine gömülmez.
- Yeni yayın doğrulanmadan önceki kurulumlar kaldırılmaz. En düşük kabul edilen Studio sürümü değiştirilmez.
- Kullanıcının yerel imzalama onayıyla yalnız mevcut yayın betiği özel anahtarı kullanır; anahtar Git'e, paketlere veya sunucuya gönderilmez.

Kullanım ayrıntıları: [Ajanlar ve dijital ekip](ajanlar.md).
