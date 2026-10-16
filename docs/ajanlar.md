# Ajanlar ve dijital ekip

**0.9.23 yayın durumu:** Windows/macOS kurulumları yayımlandı. Ortak sunucu LLM
hizmeti canlı performans sınamasını henüz geçmediğinden etkin değildir. Ajan
kullanımı firmaya ve hesaba atanmış ayrı ajan lisansı gerektirir. [Doğrulama ve açık işler](ajanlar-gelistirme-durumu.md).

Ajanlar, kullanıcı hedefini izin verilen akışlarla yerine getirir. Model hangi akışı
hangi girdilerle çalıştıracağını önerir; izin, lisans, onay ve durdurma kararlarını
Studio'nun Python katmanı uygular. Modele doğrudan fare, klavye, dosya, ağ veya komut
aracı verilmez. Bir hedefin bulunamaması tahmini tıklama veya veri girişine dönüşmez.

Bu özellik aşamalar hâlinde geliştirilmektedir. Aşağıdaki çekirdek mevcut geliştirme
dalındadır; yayımlanan sürüm ve gerçek bilgisayar doğrulaması README'de belirtilir.

## Lisans ve kullanıcı

Mevcut `MOD_RPA` lisansı korunur. Ajanlar için hem firmada hem kullanıcı hesabında
ayrıca `MOD_AJAN` gerekir. Sunucunun imzaladığı ajan yetkisi bulunmazsa normal RPA
çalışabilir, ajan uçları kapalı kalır. 0.9.24'ten itibaren bu hesaplarda **Ajanlar**
menüsü, Ayarlar'daki yapay zekâ bağlantıları ve **Yapay zekâya sor** adımı da
gösterilmez. Lisans her doğrulamada (en geç 10 dakikada bir, ya da **Lisansı şimdi
doğrula** ile) yeniden okunur; yetki verildiğinde menü yeniden giriş gerekmeden
görünür, kaldırıldığında açık Ajanlar ekranı kapanır. Bu adımı önceden içeren akışlar
açılır, ancak lisans olmadan çalıştırılamaz. Kullanıcı ve firma kimliği istek gövdesinden
alınmaz. Riskli işleri onaylama yetkisi sunucuda firmanın seçilmiş onaylayıcısının
kalıcı hesap kimliğine bağlanır; kullanıcı adı kodda sabitlenmez.

Studio oturumu kapatıldığında, lisans geçersizleştiğinde veya Durdur seçildiğinde
ajan ve onun başlattığı akış durdurulur. Başka bir kullanıcının veya zamanlayıcının
başlattığı çalışma ajan iptalinden etkilenmez. Yeniden açılışta yarım çalışmalar
otomatik sürdürülmez; eski onaylar kullanılamaz.

## İzinli akışlar ve onay

Her ajan için izinli akışlar açıkça seçilir. Alt akışlar da ayrı ayrı izinli olmalıdır.
Dinamik alt akış kimliği, döngüsel başvuru ve desteklenmeyen adımlar reddedilir.
Yönetici ajan akış çalıştıramaz; bu yetki yalnız departman ajanlarına verilir.

Katalogdaki her adım risk tablosunda sınıflandırılır. Masaüstünden tablo okumak bile
tıklama ve seçim değiştiriyorsa onay gerektirir. Akışın riski tüm alt akışları kapsar.
Bilinmeyen bir adım okuma sayılmaz. API bağlantısı kullanan HTTP isteği, veritabanı
okuma/yazma, e-posta okuma, FTP ve mesaj adımları 0.9.30'dan itibaren ajan akışlarında
kullanılabilir ([kurallar](kurumsal-entegrasyon.md#ajanlar-ve-entegrasyon-adımları)).
Genel kabuk/komut/script, bağlantısız HTTP isteği ve genel
masaüstü girişleri ilk sürümün ajan araçlarına açılmaz; manuel akış davranışı korunur.
Pencere üzerinden çalışan adımlar aynı çalışmada bulunmuş, doğrulanmış pencereyi
kullanır. Dosya işlemleri yalnız kullanıcının akış izninde belirttiği köklerde yapılır;
Studio veri dizinine, program kaynaklarına ve kimlik bilgilerine erişilemez.

Geri alınamaz akış başlamadan onay beklenir. Onay akış ve alt akış içeriklerine,
girdilere, ajan izin revizyonuna ve kullanıcı oturumuna bağlıdır. Tek kullanımlıktır.
Reddetme veya sürenin dolması akışı başlatmaz. Değişen akış/girdi eski onayı
kullanamaz. Yeniden deneme gerekiyorsa tekrar onay alınır; hedef hatası veren akış
aynı girdilerle körlemesine çalıştırılmaz. Açıkça verilen «onaysız çalışabilir» izni
akışın o sürümüne bağlıdır ve denetim kaydı içerir.

Tek masaüstü çalışanı kuralı devam eder. Ajan akışları sırayla çalışır; masaüstü
meşgulse sınırlı süre bekler ve sonunda modele «meşgul» sonucu döner. Zamanlanmış
akışın geri sayımı da masaüstünü ayırır; araya başka ajan veya manuel akış giremez.

Web akışında tıklamanın başlattığı yeni sekme yavaş yanıt verirse adım sekmenin
açılmasını bekler. Süre aşımında önceki sayfada çalışmayı sürdürmez ve tıklamayı
tekrarlamaz. Bu davranış ajan üzerinden ve elle çalıştırılan akışlarda aynıdır.

## Girdiler, çıktılar ve gizli bilgiler

Akış dosyasına zorunlu girdi/çıktı alanı eklenmez. Beklenen girdiler, akışın okuyup
üretmediği değişkenlerden çıkarılır. Sistem ve şifre değişkenleri girdi olarak
geçilemez. En fazla 100 alan ve toplam 64 KiB JSON kabul edilir; derinlik, sonsuz
sayı, alan adı ve türler doğrulanır. Belirsiz çıkarımlar açıkça belirtilir.

Ajanın başlattığı akışın son değişkenleri sınırlandırılmış, maskelenmiş görüntü
olarak kaydedilir. `Run.trigger` değerleri değiştirilmez; ajan ile akış ilişkisinin
kaynağı ajan çalışma kaydındaki akış kimlikleridir. Böylece mevcut akış çalışma
dosyalarının tetikleyici biçimi eski sürümlerle uyumlu kalır.

Sistem şifre kasasından gelen değerler, bunlardan türetilmiş çıktı değişkenleri ve
bağlantı sırları model mesajlarına veya günlüklere verilmez. API anahtarları ayrı
kasa alanında tutulur; akışın `${sifre.ad}` kapsamına açılmaz. Sağlayıcı bağlantısı
kaydı anahtar içermez, arayüz yalnız «kayıtlı» durumunu görür. Anahtar değiştirme
alanı yazma amaçlıdır; eski değer geri okunmaz.

Kayıtlı bir sağlayıcı anahtarı bağlantı adı, model veya adres alanına yazılamaz;
bağlantı testindeki model kutusu da aynı denetime tabidir. Kasa kaydı bulunduğu
hâlde anahtar sistem kasasında yoksa dış çağrı yapılmaz; kayıt sorunu giderilmeden
yapay zekâ işlemi sürdürülmez. Çalışma sırasında yeni kaydedilen sırlar
soru yanıtı ve model isteği/yanıtı denetimlerinde mevcut maskeleme listesine
eklenir; anahtar değişse de aynı çalışmanın eski anahtarı maskelenmeye devam eder.

Akış çıktıları güvenilmeyen veri olarak işaretlenir. Bir e-posta, OCR sonucu veya
dosya içindeki talimat ajan yetkisini değiştiremez. Metin/CSV/JSON çıktı okumak
yalnız o ajan çalışmasının oluşturduğu dosyalarda ve boyut sınırıyla mümkündür;
keyfi disk yolu kabul edilmez. Modele gönderilen maskeli içerik çalışma zaman
çizelgesinde incelenebilir. Tur, süre, token, akış sayısı ve aynı çağrıyı tekrarlama
sınırları vardır.

## Sağlayıcılar

Ortak arayüz OpenAI, Gemini, Anthropic, Ollama ve OpenAI uyumlu yerel sunucuları
kapsar. Model adı serbest metindir; sağlayıcıda gerçekten bulunan ve araç çağırmayı
destekleyen bir model seçilmelidir. Formdaki model çipleri yalnız öneridir; seçtiğiniz ad
değiştirilmeden kullanılır, eski bir ad başka modele sessizce çevrilmez. Gemini Flash
modellerinde düşünme kapatılır; Pro modellere bu ayar gönderilmez. Başka ücretli sağlayıcıya otomatik geçiş yoktur.
Bulut bağlantısı kullanılırsa akış sonuçları o sağlayıcıya gönderilir; hassas veri
için yerel model tercih edilebilir. Bağlantı testi bile bulut sağlayıcıda kullanım
oluşturabilir; test yalnız kullanıcının düğmeye basmasıyla yapılır.

Yerel bağlantı yalnız loopback adresi kullanır. Ortak sunucu bağlantısı
ayrı kimlik doğrulamalı hizmet kullanır; Ollama portunu doğrudan internete açmak
desteklenen kurulum değildir. Sağlayıcı istekleri boyut ve süre sınırına tabidir,
yönlendirme izlenmez. Yeniden deneme yalnız ağ hatası, 429 ve 5xx durumlarında
yapılır. Testler gerçek sağlayıcıya istek göndermez.

Ollama bağlantısı, her istekten önce bulut kullanımının kapalı olduğunu ve seçilen
modelin yerelde bulunduğunu doğrular. `OLLAMA_NO_CLOUD=1` Ollama hizmetinde etkin
olmalıdır. Doğrulama yapılamazsa iş verisi gönderilmez. API'yi desteklemeyen eski
Ollama sürümü için güncelleme gerekir. Ortak sunucu seçeneği Studio oturumunu
kullanır; ayrıca API anahtarı girilmez. Diğer bulut sağlayıcılarına otomatik geçilmez.

## Studio'da kullanım

1. **Ajanlar → Bağlantılar** bölümünde sağlayıcıyı ve serbest model adını kaydedin.
   Kurum modeli seçildiğinde sunucuda kurulu ve izinli model adı gerekir.
2. **Ajanlar** bölümünde bir yönetici ve gerekli departman ajanlarını oluşturun.
   Departman adını ve bağlı yöneticiyi formdan değiştirin. Akış izinleri açıkça
   seçilir; başka departmanın akışı otomatik olarak eklenmez.
3. **Görev ver** ile hedefi yazın. Zaman çizelgesindeki soru kartına yanıt verin;
   riskli akışın adı, maskelenmiş girdileri ve gerekçesi onay kartında görünür.
4. **Onaylar** sekmesinden kurumun yetkili hesabı bekleyen işleri onaylar veya
   reddeder. Akışı başlatacak Studio onayı sunucuda tek kullanımlık olarak
   tüketmeden çalıştırmaz. Bağlantı hatası yerel onaya dönüşmez.
5. **Durdur** ajanı, alt görevlerini ve yalnız bunlara bağlı çalışan akışı durdurur.
   Alt akış iptal sinyalini önce görse de kaydı **İptal edildi** olur. Aynı kural
   lisansın kapanması ve oturum değişmesi için geçerlidir; süre veya yetki sınırını
   aşmak hata olarak kaydedilir. Daha önce tamamlanan dış işlemler geri alınmaz.

### Ekranda yardımcı olanlar (0.9.27)

- **Başlarken:** Bağlantı ve akış izni olan bir departman ajanı oluşana kadar
  Ajanlar sekmesinde adım adım kontrol listesi görünür. **Ajanlar nasıl çalışır?**
  bölümü süreci beş adımda özetler.
- **Sizi bekleyen işler:** Bir ajan sizden yanıt veya onay beklediğinde hangi
  sekmede olursanız olun üstte uyarı çıkar; düğme ilgili çalışmayı açar.
- **Sınır profili:** Ajan formundaki **Çalışma sınırları** bölümünde Temkinli,
  Dengeli (varsayılan) veya Geniş profil seçilebilir. Süreler dakika cinsinden
  girilir; her sınırın altında ne işe yaradığı yazar. Bir değeri değiştirince
  profil **Özel** olur.
- **Görev formu:** Görev yazarken ajanın yetki özeti açık gelir; ajanın yapamayacağı
  bir iş istenmeden önce görülür.
- **Çalışma ekranı:** Zaman çizelgesi sade cümlelerle gösterilir (hangi akış,
  hangi gerekçe, hangi soru ve yanıt). Model istekleri, okuma araçları ve JSON
  ayrıntıları **Teknik kayıtları göster** ile açılır. Karar adımı, akış, süre ve
  token kullanımı sınırla birlikte çubuk olarak görünür; yöneticinin çalışmasında
  bu, departmanlar dahil ekip bütçesidir. Alt görevlere ve yöneticinin görevine
  doğrudan geçilebilir. Ajan yöneticisinden yanıt beklerken bu belirtilir.
- **Organizasyon:** Yönetici ve bağlı departmanlar iletişim yönleriyle (görev,
  soru, yanıt, sonuç) gösterilir. Kurulum kontrolü; model bağlantısı olmayan,
  akış izni olmayan, ajanla çalıştırılamayan akışa izinli ajanları ve
  departmanı olmayan yöneticiyi listeler. Bağımsız ajanlar ayrı gösterilir.
- **Onaylar:** Onay kartında isteyen kişinin adı görünür.

Birden fazla ajan aynı çalışma alanındaki bağlantı kayıtlarını paylaşabilir.
İlk açılış ve eşzamanlı kayıt işlemleri sıraya alınır; yarım kalan dosya yazımı
önceki geçerli kaydı bozmaz.

## Organizasyon ve insan görevleri

Yönetici yalnız görev devreder; departman ajanının akış ve onay izinlerini
genişletemez. Hiyerarşi tek seviyelidir. Devirler kök görevin tur, token, süre,
akış ve görev bütçesini paylaşır. Aynı ajanın görevleri kuyruğa giriş sırasıyla
çalışır; önceki görevin bitiş anı veya bilgisayar saatinin değişmesi bu sırayı
bozmaz. Masaüstü akışları tek çalışan kuralını korur. Kuyruk durumu Studio'da görünür.

### Ajanlar arası iletişim (0.9.27)

Ajanlar yalnız yönetici üzerinden haberleşir:

- **Görev:** Yönetici, kendisine doğrudan bağlı departman ajanlarına görev verir.
- **Soru:** Yöneticinin verdiği görevde takılan departman ajanı önce yöneticisine
  sorar (`ask_manager`). Yönetici yanıtlar (`answer_department`). Bilmediği konuda
  yanıt uydurmaz; önce size sorar, yanıtınızı departmana iletir. Yanıt süre
  içinde gelmezse departman ajanı tahminle devam etmez; size sorar veya görevi
  açıklamayla bitirir. Bekleme süresi ajanın **Yanıt bekleme** sınırıdır.
- **Aktarım:** Yönetici bir departmanın bitmesini bekleyip (`wait_tasks`) sonucunu
  başka bir departmanın görevine girdi olarak ekleyebilir.
- **Sonuç:** Departman sonuçları yöneticiye döner; yönetici size tek özet sunar.

Departman ajanları birbirleriyle doğrudan konuşmaz; böylece bir departmanın
bilgisi veya izni başka bir departmana kendiliğinden geçmez. Sizin doğrudan
başlattığınız departman görevinde yönetici yoktur; ajan takılınca size sorar.
Soru ve yanıtlar iki tarafın çalışma kaydında da görünür.

### Otomasyonlar (0.9.29, 0.9.30)

**Ajanlar → Otomasyonlar** sekmesi işi kendiliğinden başlatır. Her otomasyonun bir
adı, bir **hedefi** ve bir **tetikleyicisi** vardır. Hedef iki türdür (0.9.30+):

- **Ajana görev ver:** karar gerektiren işler için. Görev metni ve isteğe bağlı girdi
  değişkenleri yazılır.
- **Akışı doğrudan çalıştır:** her seferinde aynı adımlarla yapılan işler için. Gelen
  iş akışa girdi değişkeni olarak verilir; yapay zekâ kullanılmaz, maliyet doğmaz.
  Akış elle başlatılan çalışmayla aynı kurallarla, masaüstü boşalınca (en çok 30 dakika
  beklenir) çalışır ve Çalışma geçmişi'nde görünür.

| Tetikleyici | Ayarlar | Ek olarak gelen girdiler |
| --- | --- | --- |
| Belirli zamanlarda | Bir kez, her gün, belirli günler veya her N dakikada bir (en az 5 dk); saat, günler, bitiş saati | `tetikleme_zamani` |
| Tabloya yeni kayıt geldiğinde (0.9.30+) | Google Sheets sayfası, veritabanı `SELECT` sorgusu veya Excel / CSV dosyası; kaydı ayıran sütun; isteğe bağlı süzgeç; denetim aralığı | `kayit`, `kayit_anahtari` |
| Yeni e-posta geldiğinde (0.9.30+) | Gelen e-posta (IMAP) bağlantısı, klasör, gönderen / konu süzgeci, eklerin kaydedileceği klasör, denetim aralığı | `eposta` |
| Klasöre yeni dosya geldiğinde | Klasörün tam yolu, dosya deseni (ör. `*.pdf`) | `dosya_adi`, `dosya_yolu` |
| Bir akış bittiğinde | Akış; bittiğinde, başarıyla bittiğinde veya hata verdiğinde | `tetikleyen_akis`, `akis_durumu`, `akis_hatasi`, `akis_calisma_id` |

Tablo ve e-posta tetikleyicilerinin ayrıntıları ve örnek kurgular:
[Kurumsal entegrasyon](kurumsal-entegrasyon.md#otomasyonlar-işi-kendiliğinden-başlatmak).

Kurallar:

- Otomasyonla başlayan görev, elle verilen görevle aynı izin, onay ve sınırlarla
  çalışır. Ajan takılırsa sorar; soru ve onaylar **Sizi bekleyen işler** uyarısında
  görünür. Görevin başlığı «Otomatik: ad» olur ve zaman çizelgesinde hangi otomasyonun
  başlattığı yazar.
- Otomasyonlar yalnız Studio açık, lisans ve oturum geçerliyken çalışır. Zamanı 60
  dakikadan fazla geçmiş bir çalışma (Studio kapalıydı) başlatılmaz, **Kaçırıldı**
  olarak yazılır. **Bir kez** otomasyonu çalıştıktan sonra kapanır.
- **Sıra (0.9.30+):** Gelen her iş (dosya, kayıt, e-posta, akış bitişi) sıraya girer
  ve önceki iş bitince sıradaki başlar; önceki iş sürerken gelen iş kaybolmaz. Sırada
  en fazla 200 iş bekler; kart sıradaki iş sayısını gösterir. Zamanlı otomasyonda
  önceki iş sürerken gelen zaman **Atlandı** olarak yazılır. Bir otomasyon bir saatte
  en fazla 30 ajan görevi veya 120 akış başlatır.
- Akış tetikleyicisi yalnız sizin veya akış zamanlayıcısının başlattığı çalışmaları
  sayar. Ajanların veya otomasyonların çalıştırdığı akışlar, önizleme ve adım testleri
  tetiklemez; bir akış kendi bitişiyle yeniden başlatılamaz. Böylece otomasyonlar
  döngüye giremez.
- Klasör tetikleyicisi yalnız klasöre doğrudan gelen ve iki denetim arasında boyutu
  değişmeyen (kopyalanması bitmiş) dosyaları sayar. Otomasyon kaydedildiğinde
  klasörde olan dosyalar işlenmez. Gizli, geçici (`.tmp`, `.part`, `.crdownload`)
  ve Office kilit (`~$`) dosyaları sayılmaz. Denetimde en fazla 5 dosya sıraya girer,
  kalanlar sonraki denetime kalır. Dosyayı okumak için ajanın veya akışın o klasöre
  erişimi olmalıdır.
- Otomasyonu yalnız ajanları yönetme yetkisi olan kişi oluşturur, düzenler, kapatır,
  siler veya **Şimdi çalıştır** ile dener. Diğer kullanıcılar listeyi görür. En fazla
  50 otomasyon tanımlanır. Kayıtlar `data/agent_automations.json` dosyasındadır.

### İnternet araştırması (0.9.30)

Ajan formundaki **İnternet erişimi** üç seçeneklidir: **Kapalı** (varsayılan),
**Yalnız izinli siteler** (her satıra bir site; `*.gib.gov.tr` alt alan adlarını da
kapsar) ve **Tüm web**. Erişim açık ajan iki araç kullanır: **web_search** (arama;
başlık, adres, kısa özet) ve **fetch_page** (açık bir sayfayı metin olarak okuma).
Yönetici ajan da araştırıp sonuca göre işi departmanlara yönlendirebilir.

- Yalnız okur: form gönderemez, oturum açamaz, dosya indiremez. PDF gibi metin
  olmayan içerik okunmaz.
- Yalnız açık internet: bu bilgisayara, iç ağa (10.x, 192.168.x …) ve bulut meta
  veri adreslerine istek gönderilmez; yönlendirmeler her adımda yeniden denetlenir.
  Bağlantı denetlenen adrese kurulur; sayfalar vekil sunucu (proxy) kullanılmadan okunur.
- Kayıtlı bir şifre veya anahtar içeren adres ya da arama metni reddedilir. Adresin
  `?` sonrası 300 karakterle sınırlıdır; ajan adresle iş verisi gönderemez.
- Bir görevde en fazla 20 web isteği yapılır. Her arama ve okunan sayfa zaman
  çizelgesine yazılır; ofiste ajan **Araştırma köşesi**'ne yürür.
- Sayfa içerikleri güvenilmeyen veridir. Bir sayfa ajanı yanıltmaya çalışsa bile
  izinler değişmez; riskli akışlar onay ister. Mümkünse **Yalnız izinli siteler**
  kullanın.

Arama hizmeti **Ajanlar → Bağlantılar → Web araması**'ndan seçilir: **Tavily** (ayda
1.000 ücretsiz arama, kart gerekmez; önerilen), **Vikipedi** (anahtarsız, ücretsiz,
yalnız ansiklopedik), **Brave Search** (aylık 5 $ kredi, sonrası ücretli; kredi için
sitede Brave atfı gerekir) veya kendi **SearXNG** sunucunuz. Anahtar sistem şifre
kasasında saklanır ve günlükte gizlenir. Arama kapalıyken interneti açık ajan yalnız
adresini bildiği sayfaları okuyabilir. Google Custom Search 1 Ocak 2027'de kapanacağı
için desteklenmez. İnternet erişimi kullanılmayan ajan dosyaları eski sürümlerle
uyumlu kalır; erişimi açılmış ajan 0.9.29 ve önceki sürümlerde okunamaz.

### Görevleri silme (0.9.29)

Ajanları yönetme yetkisi olan kişi bitmiş görevleri silebilir:

- **Ajan görevleri** (Görevler kartı veya Çalışmalar → **Çalışmayı sil**): görev ve
  çalışma kaydı bu bilgisayardan silinir. Bir yönetici görevi silinirse departmanlara
  verdiği alt görevler de silinir. Ajanın çalıştırdığı akışların kaydı **Çalışma
  geçmişi**'nde kalır. Çalışan veya sıradaki görev önce durdurulmalıdır.
- **İnsan görevleri**: tamamlanan, hata veren veya iptal edilen görev silinir; devam
  eden görev önce iptal edilir. Görev listelerden, ofisten ve performans hesabından
  çıkar; kayıt ve olayları denetim için kurum sunucusunda saklanır.

### Girdi değişkenleri

Girdi değişkenleri, göreve eklediğiniz adlandırılmış bilgilerdir (ör. `donem` =
`2026-09`). Görev formunda **Girdi değişkenleri** bölümünden **Girdi ekle** ile ad ve
değer satırları eklenir; JSON yazmak gerekmez. Ajan girdileri görür ve akış
çalıştırırken aynı adlı akış değişkenine verir; akışta `${donem}` olarak kullanılır.
Bölümün altında ajanın izinli akışlarının okuduğu girdi adları öneri olarak
listelenir (`*` akışın beklediği girdidir); öneriye tıklamak satırı ekler. Sayı gibi
yazılan değer sayı, `true`/`false` mantıksal değer, diğerleri metin olarak gönderilir.
Ad harfle başlamalı ve yalnız harf, rakam, alt çizgi içermelidir. Girdi gerekmiyorsa
boş bırakın; ajan eksik bilgiyi sorar.

### Hata mesajları

Model isteği başarısız olursa çalışma kaydında nedeni yazar: model bulunamadı (404,
model adı yanlış veya sağlayıcı kapatmış), API anahtarı geçersiz (401/403), kota veya
ödeme limiti doldu ya da istek sınırı aşıldı (429), sağlayıcıda geçici hata (5xx),
sağlayıcıya bağlanılamadı (internet veya Ollama kapalı), istek reddedildi (400).
Sağlayıcının kendi hata metni güvenlik nedeniyle gösterilmez. Ajan bir aracı eksik
veya tanınmayan alanla çağırırsa, hangi alanı düzeltmesi gerektiği ve beklenen alanlar
kendisine söylenir; gönderdiği değerler mesajda tekrarlanmaz. Ajan, akış gerektirmeyen
genel bilgi sorularını kendi bilgisiyle yanıtlayabilir ve bunun genel bilgi olduğunu
belirtir; şirkete özgü veriyi uydurmaz.

### Ajan notları: onaylı öğrenme (0.9.28)

Ajan, verdiğiniz yanıtları kendiliğinden kalıcı bilgiye dönüştürmez. Bir yanıt
varsayılan olarak yalnız o görevde kullanılır. Tek seferlik bir değerin ("Eylül"
gibi) sonraki aylarda tahmini girişe dönüşmemesi için kalıcı bilgi açıkça onaylanır:

- **Soruyu yanıtlarken:** Ajanları yönetme yetkisi olan kişi soru kartında
  **Bu bilgiyi ajanın kalıcı notu olarak da sakla** seçeneğini işaretleyip not
  metnini düzenleyebilir.
- **Ajanın önerisi:** Ajan görev sırasında kalıcı olabilecek bir bilgiyi
  (`suggest_note`) önerebilir. Öneri zaman çizelgesinde görünür; yetkili
  **Not olarak sakla** ile kaydeder. Bir görevde en fazla 5 öneri yapılabilir.
- **Bildikleri:** Ajan kartında notlar, ekleyen kişi ve tarihle listelenir.
  Yetkili not ekleyebilir, düzenleyebilir ve silebilir; diğer kullanıcılar yalnız
  görür.

Notlar ajanın talimatına "onaylanmış bilgi" olarak eklenir. İzin, onay veya
sınır değiştirmez; bunları yalnız ajan formu belirler ve sunucu uygular. Görev
bir notla çelişirse ajan kullanıcıya sorar. Her ajanın notu kendisine aittir;
yöneticinin veya başka bir departmanın notu paylaşılmaz. Çalışan bir göreve
eklenen not, o ajanın bir sonraki görevinden itibaren kullanılır ve çalışan
görevi durdurmaz.

Bir ajan en fazla 30 not, toplam 4.000 karakter tutar; tek not en fazla 500
karakterdir. Kayıtlı bir şifre veya anahtar içeren not reddedilir. Notlar
`data/agent_notes/` içinde ajan tanımından ayrı tutulur. Bu sayede not eklemek
ajanın izin revizyonunu değiştirmez ve eski sürümler ajan dosyalarını okumaya
devam eder. Ajan kaldırılınca notları da silinir.

### Yetki kartı

Her ajan kartında ve düzenleme formunda **Yapabilir · Onay ister · Yapamaz**
özeti bulunur. Özet elle yazılmaz, ajanın kayıtlı izinlerinden üretilir:

- Okuma/analiz akışları ve onaysız çalışma izni verilmiş akışlar **Yapabilir**
  altında görünür.
- Geri alınamaz işlem içeren akışlar **Onay ister** altında görünür.
- Ajanla çalıştırılamayan veya silinmiş akışlar ve sabit güvenlik sınırları
  **Yapamaz** altında görünür.

Düzenleme formundaki özet, siz izin ve sınırları değiştirdikçe anında
güncellenir. Kartın altında sınırlar sade dille yazılır (ör. «Her görevde en
fazla 10 akış çalıştırma, 20 karar adımı, 30 dk»). Yöneticinin sınırları,
departmanların harcadıkları dahil bütün ekip için ortaktır.

Her insan çalışan kendi Studio hesabıyla giriş yapar. Kurum yetkilisi **Görevler**
sekmesinden lisanslı çalışana görev atar. Atanan kişi başlatma, bekleme, bitirme
ve hata durumunu bildirir. Yetkili, başka çalışanın işini tamamlandı olarak
işaretleyemez; iptal edebilir veya başlamamış görevi başka çalışana aktarabilir.

İnsan görevlerinin başlığı, talimatı, durumu ve sonuç notu kurum sunucusunda tutulur.
Çalışan kendi görevlerini, yetkili kurum görevlerini görür. Görev listesi en yeni
100 kaydı gösterir; performans bu listeyle sınırlanmaz. Ajan tanımları, akışlar
ve ayrıntılı ajan zaman çizelgeleri çalıştıkları Studio bilgisayarında kalır.
Studio kapalıyken yerel ajan çalışmaz. Bu sürüm merkezi uzak masaüstü robotu
başlatma veya bilgisayarlar arasında ajan taşıma sağlamaz.

## Performans

**Performans** sekmesi bugün, bu hafta, bu ay veya en fazla 366 günlük özel
aralığı gösterir. Gün sınırları Studio bilgisayarının saat diliminde hesaplanır.
Dönem görevin **oluşturulma zamanına** göre seçilir; seçilen görevlerin tüm yaşam
süresi hesaba katılır. Başarı oranı tamamlanan / (tamamlanan + başarısız + iptal)
formülüdür. Açık görevler bu oranın paydasına girmez.

Ajan ve departman tablolarında durum sayıları, toplam/ortalama süre, akış sayısı,
onay sayısı ve bekleme süresi, token kullanımı bulunur. Üst görev alt görevin
tokenını tekrar saymaz. Süreler başlangıç ve bitiş arasındadır, beklemeleri içerir;
paralel görevlerin süreleri toplandığından toplam süre duvar saatiyle aynı değildir.
Eksik süre 0 kabul edilir ve eksik kayıt sayısı ayrıca gösterilir.

İnsan ölçümleri seçilen dönemin sunucu kayıtlarından hesaplanır. İnsan hesabında
departman alanı bulunmadığından insan departman dağılımı, akış veya token kullanımı
türetilmez. Ajan ve insan CSV'leri ayrı indirilebilir; görev içeriği içermezler ve
elektronik tablo formülü olarak yorumlanabilecek adlar etkisizleştirilir.

İsteğe bağlı **Model fiyatları** bölümüne bağlantı/model başına bir milyon girdi
ve çıktı token fiyatı girilebilir. Maliyet güncel girilen fiyatlarla tahmin edilir;
fatura değildir. Tarihsel görev kullanılan model ve bağlantı kimliğini korur.
Fiyatı bulunmayan görev ayrıca belirtilir; farklı para birimleri birleştirilmez.
Ücretsiz model için fiyat girmek gerekmez. Fiyatlar çalışma alanında firmaya özgü
`agent_metrics_<firma>.json` dosyasında tutulur, gizli anahtar içermez.

Saklama önerisi ayrıntılar için 90 gün, iş verisi çıkarılmış performans özetleri
için 365 gündür. Otomatik temizleme henüz etkin değildir; mevcut kayıtlar sessizce
silinmez. Temizleme eklendiğinde açık görev ve bekleyen onaylar korunmalıdır.

## Ofis

Three.js 0.160.0 ve OrbitControls, MIT lisanslarıyla uygulamaya dahildir. CDN,
uzak model, doku veya yazı tipi yüklenmez. Açık/koyu temada kamera döndürülebilir,
yakınlaştırılabilir; pencere gizlenince çizim durur. WebGL yoksa veya çizim yavaşsa
2D plana geçilir; aynı durum bilgileri liste görünümünde de bulunur.

Her ajan ve çalışan kodla üretilmiş bir karakterle temsil edilir. Ajan düşünürken
üç nokta, soru sorarken soru işareti, onay beklerken ünlem ve kaldırılmış el
görünür. Akış sırasında ekranı ve durum halkası canlanır; başarılı görev tesliminde
karakter yöneticiye dosya taşır, görev devrinde bir görev kartı departmana gider.
Başarısız veya iptal edilen iş teslim edilmiş gibi gösterilmez.
Yöneticiye soru soran departman ajanı yöneticinin odasının önüne yürür ve yanıt
gelene kadar orada «Soru» balonuyla bekler; yanıt gelince yöneticinin üzerinde
«Yanıt» balonu çıkar ve ajan masasına döner. Görev verilirken yöneticide «Görev»,
başarılı teslimde ajanda «Sonuç» balonu görünür. Balonlar yalnız mesajın türünü
gösterir; soru ve yanıt metni ofise taşınmaz. 2D planda soru soran ajan ile
yönetici arasında kesikli çizgi görünür. Ofisin altındaki **Son iletişimler**
listesi aynı bilgiyi saatle birlikte yazar (ör. «Yönetici → Muhasebe: görev verdi»);
mesaj içeriği bu listede de bulunmaz. İşletim sisteminin
hareket azaltma tercihi açıkken yürüyüş ve uçuşlar kaldırılır, durum simgeleri ve
balonlar korunur.

Ofis yalnız durum okur; işlem başlatmaz. Ajanlar kendi departmanlarında, insan
çalışanlar ortak çalışan alanında gösterilir. İnsan hesaplarının departman bilgisi
bulunmadığından ofis bu bilgiyi tahmin etmez. İnsanların durumları bildirdikleri
görev kayıtlarından gelir; bilgisayarlarının çevrimiçi olduğunu veya o anda klavye
kullandıklarını göstermez. Yönetici şirketindeki görev durumlarını, diğer çalışanlar
kendi görev durumlarını görebilir; yetkisiz görevler için durum bilinmiyor olarak kalır.

Ofis durum cevabı görev metni, müşteri adı, tutar, girdi veya model yanıtı içermez.
Ajanın düşünmesi ve bir akış çalıştırması ayrı durum olarak aktarılır. Tamamlanan
çalışmanın yalnız kimlik/durum bilgisi teslim animasyonu için en fazla 60 saniye
bellekte kalır; performans sayacı tutulmaz. Ayrıntılar yalnız kişi seçildiğinde
yetkili kayıtlardan okunur. İnsan hizmetine ulaşılamazsa durum bilgisi yenilenmiş
gibi gösterilmez; yerel ajan görünümü çalışmaya devam eder.
Yerel Chromium testleri geçse bile gerçek macOS WKWebView ve Windows WebView2
kontrolleri ayrıca yapılmalıdır. Paket derlemesi `--self-test-office` ile gerçek
pencere motorunu ve en az bir WebGL çizimini doğrular; yalnız 2D yedeğin çalışması
3D testinin geçtiği anlamına gelmez. Bu test yapay verili ayrı bir yerel sunucu
kullanır; normal Studio lisans kapısına istisna eklemez, kullanıcı çalışma alanını
ve şifre kasasını okumaz.

## Ortak model için kurulum koşulları

Başlangıç hedefi tek eşzamanlı çıkarım ve küçük, araç çağırmayı destekleyen yerel
modeldir. 4 vCPU ve 8 GB RAM asgari başlangıç önerisidir; web/lisans hizmetiyle
paylaşılan sunucuda 16 GB RAM tercih edilir. Model, bağlam ve sistem yüküne göre
gerçek bellek ve hız kurulumda ölçülür. GPU zorunlu değildir; CPU yanıt süresi
ölçülmeden performans garantisi verilmez. Model dosyası ve güncellemeler için
en az 15–20 GB kullanılabilir disk bırakılması önerilir.

Sanal sunucuda işlemci sayısına ek olarak işletim sisteminin gördüğü CPU
özellikleri de kontrol edilir. Fiziksel sunucunun desteklediği AVX2/FMA gibi
özellikler sanal CPU profiliyle gizlenmiş olabilir. Kurulum, gerçek araç çağrısı
sınamasını süre sınırı içinde geçmeden ortak modeli kullanıma açmaz.

Sunucudaki model işçisi web işçilerinden ayrıdır; özel yerel soket üzerinden tek
çıkarım ve sınırlı kuyruk yönetir. Prompt ve yanıt işçi belleğinde süreli tutulur;
iş kayıtları başka bir bulut sağlayıcısına gönderilmez. Ayrı ajan lisansı ve kurum
onaycısı sunucu yöneticisi tarafından tanımlanmadan bu uçlar etkinleşmez.

Aynı Studio oturumundaki ajanlar ve **Yapay zekâya sor** adımları ortak model
sırasını paylaşır. Sırada beklemek işlemin süre sınırına dahildir; iptal, oturum
değişmesi veya lisansın kapanması bekleyen isteği modele göndermeden durdurur.
Sıra bekleyen bir işlem önceki isteği kesmez. Yanıt token sınırında kesilmişse
tamamlanmış sonuç olarak kabul edilmez.

Geçici sunucu hatasında yeniden deneme beklemesi erken bitirilmez. Toplam süre
dolduğunda veya kullanıcı durdurduğunda yeni istek gönderilmez; aynı isteğin
tekrarı aynı istek kimliğini kullanır. Onay kararı ve onay tüketimi bu otomatik
yeniden denemeye dahil değildir.

Başlangıç bağlamı 8192, yanıt sınırı 1024 tokendır. Studio sunucunun bildirdiği
sınırları istekten önce uygular. İstek büyürse eski konuşmanın yalnız tamamlanmış
araç/yanıt grupları çıkarılır ve bu olay zaman çizelgesine kaydedilir. Sistem
talimatı, kullanıcı hedefi, araç tanımları veya son grup tek başına sığmıyorsa
çalışma açık hatayla durur; model sunucusunun sessizce metin kesmesine güvenilmez.

## Akış içinden yapay zekâya sor

**Veri ve metin → Yapay zekâya sor** adımı, kayıtlı sağlayıcı bağlantısını kullanır.
Talimatı ve girdi metnini/değişkenini belirtin; sonucu bir değişkene kaydedin.
İsteğe bağlı JSON şeması verilirse yanıt JSON olarak ayrıştırılır ve doğrulanır.
Örneğin `{"type":"object","properties":{"uygun":{"type":"boolean"}},
"required":["uygun"],"additionalProperties":false}` şemasıyla alınan
`${ai_result.uygun}` değeri **Koşul** adımında kullanılabilir.

Şema verilmezse sonuç metindir. Geçersiz JSON, şemaya uymayan değer, beklenmeyen
araç çağrısı, boş metin veya sınır aşımı adımı hatayla durdurur; tahmini sonuç
üretilmez. Modelin ERP veya masaüstüne doğrudan erişimi yoktur. Sonraki akış
adımları mevcut pencere ve hedef doğrulamalarını aynen uygular.

Şema Draft 2020-12 biçimindedir; uzak başvurular, dış kimlik ve düzenli ifade
kuralları desteklenmez. Yerel `$defs`/`$ref`, tür, zorunlu alan, enum ve uzunluk
sınırları kullanılabilir. Şema 16.000, girdi ve yanıt 32.000 bayt ile sınırlıdır;
iç içe düzey ve doğrulama işlemi sayısı da sınırlanır. Format denetimi seçilen
kurulumda desteklenmiyorsa açık hata verilir, denetim sessizce atlanmaz.

Bu adım için ayrı ajan lisansı gerekir. İlk sürümde yalnız elle başlatılan akışta
çalışır; ajan araç akışından veya zamanlayıcıdan iç içe model çağrısı yapılmaz.
Önizlemede dış istek gönderilmez ve sonuç bilinmeyen olarak taşınır. Kasa ve
sağlayıcı anahtarları istekten önce maskelenir; maskelenmiş istek çalışma çıktısında
incelenebilir. Bu adımı içeren akış yeni Studio sürümü gerektirir; kullanılmayan
akışlara yeni alan eklenmez.

## Geliştirme ve denetim

`agents/models.py` modelleri mevcut `Model` tabanını ve `extra="forbid"` kuralını
kullanır. Tanımlar `data/agents/`, çalışmalar `data/agent_runs/`, görevler
`data/agent_tasks/` içinde atomik yazılır. Sağlayıcı meta verisi
`data/agent_connections.json` içindedir. Ajan API uçlarının tamamı
`/api/agents` altındadır; lisans, Origin ve gövde sınırları geçerlidir.

Sahte sağlayıcı senaryoları ağsız test içindir; Studio'da gerçek bağlantı olarak
kaydedilemez. Testler izin ve alt akış denetimini, onayı, maskelemeyi, iptali,
lisansı, masaüstü sırasını, sağlayıcı protokollerini ve eski akış uyumunu kapsar.

Kullanım uçları, şirket sınırı, lisans ve Origin denetimi aynı kapıyı kullanır.
Yeni adım ve arayüz değişiklikleri yeni Studio sürümü gerektirir. Özelliği
kullanmayan akışların dosya biçimi değişmez. Sunucu kapasite yükseltmesi, canlı
lisans tanımı, gerçek model ve iki platformdaki paket kontrolleri tamamlanmadan
özellik yayımlanmış kabul edilmez.
