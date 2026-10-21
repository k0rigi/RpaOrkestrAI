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
alınmaz. Riskli işleri onaylama yetkisi sunucuda firmanın seçilmiş onaylayıcısının,
departman ofislerine ayrılmış firmada ise kullanıcının ofis yetkilisinin kalıcı hesap
kimliğine bağlanır; kullanıcı adı kodda sabitlenmez.

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

## Departman ofisleri (0.9.34)

Firma ajan ekibini departmanlara ayırabilir. Her departmanın bir **ofisi** ve bir
**ofis yetkilisi** olur. Örneğin «Claim & İade Departmanı» ile «Lojistik Planlama ve
Süreç Geliştirme Departmanı» iki ayrı ofistir; her birinin yetkilisi kendi ajanlarını
kurar.

- **Yetkili ne yapar:** kendi ofisinde ajan kurar ve düzenler, otomasyon tanımlar,
  insan çalışanlara görev verir, riskli işlemleri onaylar. Onaysız çalıştırma ve
  onaysız gönderme izinlerini de yalnız o verir. Ofisin üyesi kendisine verilen
  görevleri ve kendi onay isteklerini görür.
- **Ofisin içi:** tek ekipli düzenle aynıdır: bir yönetici ajan, ona bağlı departman
  ajanları (ofisin bölümleri) ve ofisin çalışanları. Her ofiste en fazla bir yönetici
  ajan bulunur.
- **Ofisler birbirini görmez:** görevler, onaylar, çalışan listesi, Ofis görünümü,
  performans ve Studio'daki ajan, çalışma, görev ve otomasyon kayıtları ofise göre
  ayrılır. Başka ofisteki birine görev verilemez; başka ofisin onayı görülemez veya
  verilemez.
- **Görünüm:** ofis adı Ajanlar sayfasının başlığında, Ekip sekmesindeki çalışan
  listesinde ve Ofis görünümünün başlığında yazar.
- **Kim kurar:** 0.9.36'dan itibaren ofisi kullanıcı kendisi kurar (bkz.
  [Kendi ofisinizi kurmak](#kendi-ofisinizi-kurmak-0936)). orkestrai.net yönetimi
  yalnız RPA ve Ajanlar lisansını verir. Yetkili birden fazla ofisi yönetebilir
  (0.9.37); yetkili olmayan çalışan tek ofiste bulunur.
- **Erişim:** bir ofise bağlı olmayan hesap önce kendi ofisini kurar veya bir ofis
  yetkilisinin onu eklemesini bekler; o zamana kadar ajan çalıştırmaz ve ofislerin
  kayıtlarını görmez. Yetkilisinin hesabı pasifleşen veya kapatılan ofis kapanır;
  diğer ofisler çalışmaya devam eder.
- **Bilgisayar:** ajanlar ve yerel kayıtları Studio'nun çalıştığı bilgisayarda
  saklanır. Her yetkili Studio'yu kendi bilgisayarında, kendi hesabıyla kullanır ve
  model bağlantısını (API anahtarı) orada tanımlar ya da ortak modeli seçer. Aynı
  bilgisayarı kullanan iki yetkili birbirinin ajanlarını görmez; akışlar ve Studio
  bağlantıları ise bilgisayara aittir ve paylaşılır.
- **Geçiş:** ofislerden önce kurulmuş ajanlar, görevler ve otomasyonlar onları kuran
  kişinin ofisine geçer. Firmanın tek onaycılı düzeni ofise dönüştürülürken sunucudaki
  görev ve onay geçmişi de aynı ofise taşınır.
- **Taşınma:** kullanıcı başka ofise taşınırsa açık ajan çalışması durur ve eski
  ofisteki bekleyen onay geçersizleşir.
- **Uyumluluk:** ofisli kayıtlar (ajan, çalışma, görev, otomasyon) 0.9.34'ten eski
  Studio sürümlerinde açılmaz. Ofislere ayrılmamış firmalarda dosyalar değişmez.

### Kendi ofisinizi kurmak (0.9.36)

RPA ve Ajanlar lisansı olan, henüz bir ofiste bulunmayan her hesap Ajanlar sayfasını
ilk açtığında **Ofisinizi kurun** ekranını görür. Bu kural firma hesaplarında da
bireysel hesaplarda da aynıdır.

1. **Ofis adı** yazın (2–120 karakter, firmanızda başka bir ofisin adı olmamalı;
   ör. «Lojistik Planlama Departmanı») ve **Ofisi kur**'a basın.
2. Ofisi kuran kişi ofisin **yetkilisi** olur: ajan kurma, otomasyon, görev verme ve
   onay yetkileri hemen gelir. Yetkili, 0.9.37'den itibaren başka ofisler de
   kurabilir (bkz. [Birden fazla ofisi yönetmek](#birden-fazla-ofisi-yönetmek-0937)).
   Bir firmada en fazla 50 ofis açılabilir.
3. Başka birinin ofisine katılacaksanız bu ekranda bekleyin. Ofis yetkilisi sizi
   eklediğinde ekran en geç bir dakika içinde o ofise geçer.

Ajanlar sayfasındaki **Ofisim** sekmesi ofisin bilgilerini gösterir:

- **Yetkili:** ofisin adını değiştirir; firmada ofisi olmayan, RPA ve Ajanlar
  lisanslı çalışanları listeden seçip ofise ekler; bir üyeyi **Ofisten çıkar** ile
  çıkarır. Çıkarılan kişinin ofisteki görev ve onay geçmişi ofiste kalır.
- **Üye:** **Ofisten ayrıl** ile ayrılabilir; sonra kendi ofisini kurabilir. Üye
  ofisindeyken yeni ofis kuramaz.
- Yeni lisans vermek orkestrai.net yönetimindedir; kendi ofisini kurmuş bir çalışan
  başka bir ofise eklenmez.
- Değişiklik açık Studio'lara en geç 10 dakika içinde yansır. Ofisi kurmak ve
  ofisten ayrılmak o bilgisayarda hemen geçerli olur.
- Ofislerden önce kurulmuş ajan ve otomasyonlar, onları kuran kişi kendi ofisini
  kurduğunda o ofise geçer. Ofisi olmayan hesap başkalarının eski kayıtlarını görmez.

### Birden fazla ofisi yönetmek (0.9.37)

Bir yetkili birden fazla departmanı yönetebilir; her departmanın kendi ofisi olur.

- **Yeni ofis:** **Ofisim** sekmesindeki **Yeni ofisin adı** alanına ad yazıp
  **Yeni ofis kur**'a basın. Yeni ofis hemen ekrana gelir; yetkilisi sizsiniz. Bir
  kullanıcının kurabileceği ofis sayısı sınırsızdır; firmadaki toplam sınır 50'dir.
- **Ofis değiştirme:** birden fazla ofisiniz varsa Ajanlar başlığındaki **Ofis**
  listesinden ofis seçin. Ajanlar, çalışmalar, görevler, onaylar, otomasyonlar,
  Organizasyon, Performans ve 3D Ofis seçili ofise göre gösterilir. Seçim bu
  bilgisayarda hatırlanır.
- **Diğer ofisler çalışmaya devam eder:** ofis değiştirmek yalnız ekranı değiştirir.
  Diğer ofislerin ajan çalışmaları, zamanlanmış otomasyonları ve onay beklemeleri
  kendi ofislerinde sürer; onaylar ve görevler her zaman ait oldukları ofise yazılır.
- **Ofislerim:** **Ofisim** sekmesinin başında her ofisin ajan, kişi, açık görev ve
  bekleyen onay sayısı görünür; **Bu ofise geç** ile o ofise geçilir.
- **Kişiler:** yetkili, kurduğu her ofisin kişisidir. Yetkili olmayan çalışan tek
  ofiste bulunur; bir ofise eklenen kişi başka ofise eklenemez.
- **Güvenlik:** Studio her istekte hangi ofis adına çalıştığını bildirir;
  orkestrai.net bunu her istekte doğrular. Erişiminiz kalmayan bir ofis adına
  istek yapılmaz; o ofisin açık çalışması durur.
- **Uyumluluk:** birden fazla ofis 0.9.37 gerektirir. 0.9.36 ve önceki sürümler
  yalnız ilk ofisi gösterir.

### Ofisler arası iletişim (0.9.38)

Birden fazla ofisi yöneten yetkilinin ofisleri birbirine iş gönderebilir. Gönderim yalnız yöneticiler
aracılığıyla yapılır.

- Yönetici ajan, **list_offices** ile yönettiğiniz diğer ofisleri ve yöneticilerini görür. **contact_office** ile
  o ofisin yönetici ajanına görev verir veya soru sorar.
- Karşı ofisin yöneticisi işi kendi departmanlarına dağıtabilir. Belirsizlikte isteyen yöneticiye geri soru
  sorar. Sonucu bitirdiğinde istek yapan yönetici sonucu alır ve kendi işini tamamlar.
- Departman ajanları başka ofisle doğrudan konuşmaz. İşi alan yönetici de onu üçüncü bir ofise aktaramaz.
- Gönderilen iş karşı ofiste o ofisin kaydı olarak çalışır. Görevler, riskli işlem onayları ve süre sınırları
  o ofise aittir. Bütçe (tur ve görev sınırları) isteyen yöneticinin işinden düşer.
- Yalnız aynı yetkilinin yönettiği ofisler arasında çalışır. Üyeler ve başka yetkililerin ofisleri bu araçları
  görmez. Hedef ofiste yönetici ajan yoksa iş gönderilmez ve neden yazılır.
- 3D ofiste gönderen yöneticide "Diğer ofise", alan yöneticide "Diğer ofisten" balonu görünür. Son iletişimler
  listesi yalnız ofisin adını ve mesajın türünü yazar; işin içeriği ofis görünümüne taşınmaz.

### Telegram'dan soru ve onay (0.9.38)

Bilgisayar başında değilken ajanlar size Telegram'dan ulaşabilir. Kurulum için:

1. @BotFather'dan bir bot oluşturun.
2. Bot anahtarını Studio **Ayarlar → Bağlantılar**'da bir Telegram (bot) bağlantısına kaydedin.
3. Kendi Telegram hesabınızla bota `/start` yazın ve sohbet kimliğinizi bağlantıya ekleyin.
4. **Ajanlar → Bağlantılar → Telegram'dan soru ve onay** bölümünde bağlantıyı ve sohbet kimliğinizi seçip
   **Kaydet ve aç**'a basın. **Deneme mesajı gönder** ile kontrol edebilirsiniz.

Nasıl çalışır:

- **Sorular:** bir ajan size soru sorduğunda soru Telegram'a gelir. Seçenekler düğmedir; yazılı yanıt için
  mesajı **Yanıtla** ile seçip yazın. Tek soru açıkken düz mesaj da o soruya yanıt sayılır.
- **Onaylar:** onay yetkiliyseniz riskli işlem istekleri; akış, neden ve girdileriyle birlikte **Onayla /
  Reddet** düğmeleriyle gelir. Karar, Studio'daki kararla aynı denetimlerden geçer (oturum, ofis, merkezi
  onay). Girdileri düzenlemek için Studio'daki onay kartı kullanılır.
- **Güvenlik:**
  - Yalnız kayıtlı **özel sohbetinizden** gelen yanıt ve düğme kabul edilir; grup ve kanal kabul edilmez.
  - Soru Studio'da yanıtlanırsa veya süresi dolarsa Telegram mesajı "Kapandı" olarak güncellenir; geç yanıt
    reddedilir.
  - Mesajlarda kayıtlı gizli değerler maskelenir. Soru ve onay metinleri (iş bilgisi) Telegram'a gider.
- **Gereksinim:** Studio açık ve internete bağlı olmalıdır. Studio yanıtları kendisi çeker (getUpdates);
  dışarıdan erişilebilir bir adres gerekmez. Botta webhook tanımlıysa yanıtlar okunamaz; bu iş için ayrı bir
  bot kullanın.
- **Ücret:** Telegram ücretsizdir. Telefonla arama bu sürümde yoktur; ücretli bir sağlayıcı gerektirir ve
  ancak onayınızla kurulur.
- Ayar kişiseldir: aynı bilgisayardaki başka hesap kendi ayarını yapar. Diğer ofislerinizdeki soru ve onaylar da
  gelir ve kendi ofislerinde yanıtlanır.

### Telegram'dan görev ve soru (0.9.41)

Telegram ayarlıysa bota yazarak ajanlarınıza görev verebilir ve soru sorabilirsiniz:

| Bota yazın | Ne olur? |
| --- | --- |
| `/gorev bugünkü bekleyen işleri özetle` | Ofisinizin yönetici ajanına görev verilir; yönetici gerekirse departmanlara dağıtır. |
| `/gorev Rapor ajanı: haftalık tabloyu hazırla` | Görev adı yazılan ajana gider. |
| `/sor kaç görev bekliyor?` | Yönetici iş başlatmadan, bildiklerinden yanıt verir (Soru sor ile aynı). |
| Komutsuz mesaj | Yanıt bekleyen bir soru yoksa yöneticiye soru sayılır. |
| `/ajanlar` | Ofisleriniz ve ajanlarınız listelenir. |
| `/yardim` | Komutları gösterir. |

- **Birden fazla ofis:** mesajı ofis adıyla başlatın: `/gorev Lojistik: yarının sevkiyatlarını planla` veya
  `/gorev Lojistik: Rota ajanı: rota çıkar`. Ofis yazılmazsa iş gönderilmez ve ofisleriniz listelenir. Aynı adlı ajan
  birden fazla ofiste varsa ofis adı istenir; iş tahminle bir ajana verilmez.
- **Sonuç:** görev başlayınca "Görev … ajanına verildi" mesajı gelir; bitince sonuç özeti, başarısız olursa nedeni
  Telegram'a yazılır. Aradaki sorular ve onaylar her zamanki gibi gelir.
- **Kayıtlar:** Telegram'dan verilen görev Studio'da verilmiş görev gibi **Görevler** ve **Çalışmalar**'da tüm
  ayrıntısıyla durur; listede ve zaman çizelgesinde "Telegram'dan" yazar. Telegram'dan sorulan soru ajanın soru
  geçmişine "Telegram'dan" işaretiyle kaydedilir. Telegram'dan verilen yanıtlar ("Yanıtınız Telegram'dan iletildi")
  ve onay kararları ("İşlem onaylandı · Telegram'dan") da çalışma kaydında böyle görünür. Kayıtlar yalnız bu
  bilgisayardadır.
- **Yetki:** görev ve soru, Studio'daki gibi oturum, lisans, ofis, ajanın izinli akışları ve riskli işlem onayından
  geçer. Yalnız kayıtlı özel sohbetinizden gelen komutlar kabul edilir.
- **Studio kapalıyken** gönderilen `/gorev` ve `/sor` (10 dakikadan eski) çalıştırılmaz; "Studio kapalıyken
  gönderildi" yanıtı gelir, gerekiyorsa yeniden gönderin. Studio açıkken Telegram ayarlıysa bot sürekli dinlenir.
- Telegram'dan verilen görevin kaydı 0.9.41 öncesi sürümlerde okunmaz; Studio'da verilen görevlerin kayıtları
  değişmez.

## Bireysel hesapta ajanlar (0.9.35)

Bireysel hesapta (bkz. [lisans](lisans.md#bireysel-hesaplar-0935)) Ajanlar ek modüldür ve ekip tek kişidir.
0.9.36'dan itibaren bireysel hesap da Ajanlar'ı ilk açtığında kendi ofisini kurar
(bkz. [Kendi ofisinizi kurmak](#kendi-ofisinizi-kurmak-0936)); ofiste tek kişidir.

- Kişi kendi ajanlarının yöneticisi ve onaycısıdır: riskli işlemleri o onaylar, onaysız çalıştırma izinlerini de o verir.
- İnsan görevleri (**Görevler** sekmesi) ve **Organizasyon** sekmesindeki çalışan listesi gösterilmez.
- Yönetici ve departman ajanları, bilgi kaynakları, süreç kartları, otomasyonlar ve doğrudan yetenekler firma hesaplarındakiyle aynı çalışır.

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

**Model sağlayıcısının kendi araması (0.9.32+).** Gemini (Google Search ile destekleme), OpenAI (web
arama aracı) ve Claude (web arama aracı) internette kendileri arayabilir. Bu seçenek seçilince ek anahtar
gerekmez; her ajan kendi model bağlantısıyla arar.
- Arama, ajanın konuşmasından ayrı bir istekle yapılır. Aranacak metin önce uygulamanın denetiminden geçer:
  kayıtlı şifre denetimi, izinli siteler ve görev başına 20 istek sınırı.
- Dönen kaynaklar izinli sitelere göre süzülür; Gemini'nin yönlendirme bağlantıları gerçek adrese çevrilir.
  Sağlayıcının kısa özeti de ajana verilir. Kaynaklar ve özet güvenilmeyen veridir.
- Kullanılan tokenlar ajanın token sınırına sayılır. Sağlayıcının arama ücreti ve tokenlar model
  faturanıza eklenir; Gemini'de aylık ücretsiz bir kota vardır.
- Ollama, yerel OpenAI uyumlu sunucu ve kurum sunucusu bağlantılarının kendi araması yoktur. Bu ajanlar
  arama yapmaya çalışırsa ne yapılacağını söyleyen bir uyarı alır; onlar için Tavily, Vikipedi veya
  SearXNG seçin.
- **Aramayı test et**, ilk uygun ajanın bağlantısıyla gerçek bir deneme araması yapar.
- Ajan formu iki durumda uyarı gösterir: internet erişimi açık ama arama hizmeti seçilmemişse ya da
  ajanın bağlantısı model aramasını desteklemiyorsa.

### Doğrudan yetenekler: akışsız okuma ve gönderme (0.9.33)

Ajan bir yapay zekâ modelidir: metni anlamak, sınıflandırmak, özetlemek, hesaplamak ve yanıt yazmak için akışa
ihtiyaç duymaz, bunları kendisi yapar. Akışlar masaüstü, ERP ve sistem işleri içindir. Ajan formundaki
**Doğrudan yetenekler** bölümünde ajanın akış gerekmeden neyi okuyabileceği ve nereye gönderebileceği seçilir:

| Yetenek | Ne yapar | Sınır |
| --- | --- | --- |
| Okuyabileceği klasörler | Klasörlerdeki PDF, Word, Excel, metin, CSV ve HTML belgelerini listeler ve okur (ör. e-posta ekleri) | Yalnız seçilen klasörler; Studio klasörleri seçilemez; görevde en fazla 30 belge |
| Okuyabileceği gelen kutusu | Gelen e-posta (IMAP) bağlantısındaki iletileri okur | Okundu yapmaz; görevde en fazla 5 okuma |
| E-posta gönderebileceği hesap | E-posta yazar, gönderir veya yanıtlar (aynı yazışmanın altında) | Kimlere: yalnız göreve gelen adreslere (ör. yazan müşteri), yalnız izinli alan adlarına veya herkese; görevde en fazla 10 gönderim; ek dosya eklenmez |
| Mesaj gönderebileceği kanal | WhatsApp, Telegram, Teams, Slack… bağlantısına mesaj gönderir | Yalnız bağlantıdaki kanala veya varsayılan alıcıya |

- **Onay:** Her e-posta ve mesaj, akışlardaki gibi onayınıza gelir. Onay ekranında **Düzenleyerek onayla**
  ile konu ve metin düzeltilebilir; gönderilen, onaylanan hâldir.
- **Onaysız gönderim:** **Onay beklemeden gönderebilir** iznini yalnız onay yetkilisi verir ve kayda
  geçer.
- **Süreç kartları:** Kart kuralları gönderimde de geçerlidir. Kartı olan ajan uyan kartı seçmeden
  göndermez; «İnsana bırak» kartında hiç göndermez; «Her değişikliği onaya sun» kartında izin olsa bile
  onay ister.
- **Kayıt:** Okunan belgeler ve gönderilen e-postalar zaman çizelgesine yazılır.
- **Uyumluluk:** Yetenek tanımlanmamış ajanların dosyası değişmez. Yetenek tanımlanmış ajan 0.9.32 ve
  önceki sürümlerde okunamaz.

### Ajana soru sorma (0.9.33)

Ajan kartındaki **Soru sor** ile ajanla konuşulur. Örnek sorular: «Bugün neler yaptın?», «Şu an bekleyen
işler neler?», «Son hatalar neydi?», «Bu hafta kaç görev tamamladın?».
- **Neye bakar:** Ajan bu bilgisayardaki görev kayıtlarına, otomasyon sıralarına, onaylı notlarına ve
  bilgi kaynaklarına bakarak yanıtlar. İnterneti veya okuma yetenekleri açıksa onları da kullanır.
  Yönetici ajan, bağlı departmanların durumunu da anlatır.
- **Sınır:** Sohbet yalnız bilgi verir; iş başlatmaz, akış çalıştırmaz, e-posta veya mesaj göndermez. İş
  yaptırmak için **Görev ver** kullanılır.
- **Gönderilen veri:** Sohbette görev kayıtlarının maskelenmiş özetleri ajanın model bağlantısına
  gönderilir; kullanılan token her yanıtın altında görünür.
- **Geçmiş:** Ajan başına son 40 mesaj saklanır; **Sohbeti temizle** ile silinir.

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

### Firmanın işleyişini öğretmek: bilgi kaynakları, süreç kartları ve taslak onayı (0.9.31)

Her firmanın dinamiği farklıdır; ajan bunu kendiliğinden bilmez. Ajan formundaki iki bölümle öğretilir.
Onay ekranındaki düzeltmelerle de gelişir.

**Bilgi kaynakları.** Fiyat listesi, iade politikası, sık sorulan sorular, ürün kataloğu gibi belgelerin
veya klasörlerin tam yolu yazılır (**Dosya ekle / Klasör ekle**).
- Okunan türler: metinli PDF, Word (.docx), Excel (.xlsx), metin, CSV, HTML. Klasörlerin alt klasörleri
  de okunur. Gizli, geçici ve `~$` kilit dosyaları atlanır.
- Ajan firmaya özgü bir konuda cevap yazmadan önce bu belgelerde arar. Cevabını bulduğu bölüme dayandırır
  ve kaynak adını belirtir. Bulamazsa uydurmaz.
- Arama bu bilgisayarda yapılır ve ücretsizdir. Modele yalnız bulunan kısa bölümler gider; belgelerin
  tamamı gönderilmez.
- Belge değişince ajan yeni hâlini kullanır.
- Taranmış (metni olmayan) PDF okunmaz; metin içeren bir kopyası eklenmelidir.
- Studio'nun veri ve program klasörleri kaynak olamaz.
- **Kaynakları kontrol et ve dene** kaydedilmiş kaynaklarda kaç dosyanın okunduğunu, okunamayanları
  gösterir. Modele bir şey göndermeden deneme araması yapar.
- Bir görevde en fazla 30 arama yapılır. Her arama zaman çizelgesine yazılır; ofiste ajan araştırma
  köşesine gider.

**Süreç kartları.** Her kart bir konuyu ve firmanın o konudaki işleyişini anlatır:

| Alan | Örnek |
| --- | --- |
| Konu | Bilgi talebi |
| Ne zaman | Müşteri ürün, stok veya teslim süresi sorarsa |
| Ne yapılır | Bilgi kaynaklarına bak, kısa ve kibar yanıt yaz, kaynakta yoksa insana bırak |
| Akışlar | Bu kartta kullanılacak akışlar (boşsa izinli tüm akışlar) |
| Kural | Akış izinlerine göre uygula / Her değişikliği onaya sun (taslak) / Değişiklik yapma, insana bırak |

Kartlar izin vermez, yalnız daraltır:
- Kartı olan ajan, değişiklik yapan bir akışı ancak işe uyan kartı seçtikten sonra çalıştırabilir.
- Uyan kart yoksa ajan değişiklik yapmaz. Durumu özetler ve işi **size bırakır**.
- «Taslak» kuralı, akışa «Onaysız çalışabilir» izni verilmiş olsa bile her değişikliği onaya sunar.
- «İnsana bırak» kuralı değişikliği tamamen engeller.
- Kartta akış seçildiyse ajan o konuda başka bir akışla değişiklik yapamaz.

Ajanın size bıraktığı işler üstteki **Sizi bekleyen işler** alanında 14 gün görünür. Çalışmada
**Ele alındı olarak işaretle** ile kapatılır.

**Taslak onayı ve öğrenme.** Onay ekranında **Düzenleyerek onayla** ile ajanın taslağı
(ör. e-posta metni) düzeltilir:
- Akış tam olarak onaylanan hâliyle çalışır.
- Ajan düzeltmeyi görür. Sonraki işler için genel bir kural çıkıyorsa bunu not olarak önerir; not yalnız
  yetkili onaylarsa kaydedilir.
- Yalnız mevcut alanların değeri değişir; alan eklenmez, türü değişmez. Gizli değer içeren alanlar
  düzenlenemez.
- Merkezi kurum onayı kullanılıyorsa düzeltilmiş hâl de merkezi kayda geçer. Düzenleme, görevin çalıştığı
  Studio'dan yapılır.

Ajan kartındaki **Süreç kartları** bölümü her kart için şunları sayar: kaç taslağın değiştirilmeden
onaylandığı, kaçının düzeltilerek onaylandığı, kaçının reddedildiği ve kaç işin insana bırakıldığı.
Bir konuda en az 20 karar verilmiş ve taslakların %90'ı değiştirilmeden onaylanmışsa bölüm bir öneri
gösterir: o konunun akışına «Onaysız çalışabilir» izni verilebilir. İzni yalnız onay yetkilisi verir.
Akış başka kartlarda da kullanılıyorsa onlar da etkilenir; konuya özel otomatik gönderim için her
konuya ayrı bir akış önerilir.

Bilgi kaynağı veya süreç kartı tanımlanmamış ajanların dosyası değişmez. Tanımlanmış ajan dosyası
0.9.30 ve önceki sürümlerde okunamaz.

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

Three.js 0.160.0, OrbitControls, GLTFLoader ve BufferGeometryUtils, MIT
lisanslarıyla uygulamaya dahildir. CDN, uzak model, doku veya yazı tipi yüklenmez. Açık/koyu temada kamera döndürülebilir,
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
kullandıklarını göstermez. Yönetici şirketindeki (ofislere ayrılmış firmada kendi
ofisindeki) görev durumlarını, diğer çalışanlar kendi görev durumlarını görebilir;
yetkisiz görevler için durum bilinmiyor olarak kalır. Ofislere ayrılmış firmada başlık
ofisin adını gösterir ve yalnız o ofisin ajanları ile çalışanları görünür.

Ofis durum cevabı görev metni, müşteri adı, tutar, girdi veya model yanıtı içermez.
Ajanın düşünmesi ve bir akış çalıştırması ayrı durum olarak aktarılır. Tamamlanan
çalışmanın yalnız kimlik/durum bilgisi teslim animasyonu için en fazla 60 saniye
bellekte kalır; performans sayacı tutulmaz. Ayrıntılar yalnız kişi seçildiğinde
yetkili kayıtlardan okunur. İnsan hizmetine ulaşılamazsa durum bilgisi yenilenmiş
gibi gösterilmez; yerel ajan görünümü çalışmaya devam eder.
### Kendi 3D ofis modeliniz (0.9.38: yerleşim sözleşmesi)

Hazır ofis yerine kendi binanızın veya ofisinizin 3D modelini kullanabilirsiniz. Model, **RPA ofis yerleşim
sözleşmesine** uymalıdır. Ajanların çalışacağı, bekleyeceği ve yürüyeceği yerler modelin içinde adlandırılmış
noktalarla açıkça tanımlanır. Kurallar, hata listesi, Blender adımları ve model hazırlatırken kullanılacak
yönerge: [Ofis modeli](ofis-modeli.md).

- **İçe aktarma:** Ofis görünümünde **Ofis modeli → Model seç (.glb)**. Sözleşmeye uymayan model reddedilir ve
  eksikler madde madde yazılır. **Örnek ofisi kullan** sözleşmeye uyan hazır bir ofis açar: sekiz masalı
  çalışma alanı, cam yönetici odası, bekleme alanı ve araştırma köşesi.
- **Yerleşim:** ajanlar ve ofisin çalışanları modelin çalışma noktalarına, sonra bekleme noktalarına kalıcı
  olarak yerleşir. Noktalar dolunca kişi yalnız listede görünür ve "Ofis kapasitesi dolu" yazar; karakterler üst
  üste binmez. Tabloda herkesin noktası görünür (ör. "Çalışma noktası 003").
- **Oturma ve yürüme:** oturma referansı olan masada karakter gerçek oturma pozuyla oturur. Yürüyüş (yöneticiye
  soru, sonuç teslimi, araştırma, görev devri) yalnız modelin yol ağında yapılır. Buluşma veya araştırma noktası
  tanımlı değilse karakter yerinde kalır ve balonu görünür.
- **Görünüm:** model ofisin kendi odası olur; hazır oda, masa veya etiket üretilmez. Yalnız modeldeki alan
  etiketleri gösterilir. **Tavan kesiti** verilen yüksekliğin üstünü gizler (0 = kapalı); 2D plan modelin
  noktalarından, yollarından ve etiketlerinden çizilir.
- **Nerede saklanır:** model, ayarı ve yerleşim eşlemesi yalnız bu bilgisayarda, çalışma alanındaki
  `data/office_models` klasöründe ve o ofis için saklanır. Sunucuya gönderilmez.
- **Önceki sürümler:** 0.9.36–0.9.37 ölçek ve konum ayarlarıyla dekor olarak yerleştirilen, sözleşmesiz modeller
  artık kullanılmaz; panel nedenlerini yazar. Yeni model içe aktarın, örnek ofisi kullanın veya eski modeli silin.
- **Performans:** binlerce parçalı modeller açılırken malzemeye göre birleştirilir. Model cihazda yavaş çizilirse
  ofis 2D plana geçer.

### 3D ofisten yönetmek (0.9.38)

Ofis görünümünde bir çalışana tıklayınca açılan panel, diğer Studio ekranlarıyla aynı yetkilerle işlem yapar.
Bir düğmeye basılmadıkça hiçbir şey yapılmaz.

- **Ajan:** **Görev ver** ajana yeni bir görev başlatır. Yöneticiye verilen görev departmanlara dağıtılabilir.
  **Soru sor**, ajanla kısa bir sohbet açar; ajan iş başlatmaz, bildiklerinden yanıtlar.
- **Bekleyen soru:** ajan sizden yanıt bekliyorsa soru ve seçenekleri panelde görünür; seçenekle veya yazarak
  yanıtlarsınız.
- **Bekleyen onay:** onay yetkiliyseniz akışın adı, neden ve girdiler görünür. **Onayla** veya **Reddet**
  ile karar verirsiniz. Girdileri düzenlemek için onay kartına gidilir.
- **İnsan çalışan:** ajan yönetme yetkiniz varsa **Görev ata** ile başlık, yapılacak iş ve öncelik yazıp görev
  atarsınız.
- **Yöneticiye yaz:** araç çubuğundaki düğme, yönetici ajanın panelini soru formuyla açar.

### Ajanları hareket halinde görmek (0.9.40)

Karakterler yalnız ajanlar birbiriyle çalışırken yürür:

| Ne olur? | 3D ofiste görünen |
| --- | --- |
| Yönetici bir departmana görev verir | Yönetici departmanın yanına yürür, "Görev" balonu |
| Departman ajanı internette araştırır | Ajan araştırma köşesine yürür, "Araştırıyor" balonu |
| Departman ajanı yöneticiye soru sorar | Ajan yöneticinin önüne yürür, "Soru" balonu; yönetici "Yanıt" ile döner |
| Departman işini bitirir | Ajan sonucu yöneticiye götürür, "Sonuç" balonu |
| Ajan izinli bir akış çalıştırır | Masasında çalışır, ekranı yeşil yanar |

- **Gösterimi oynat:** araç çubuğundaki düğme, ofisinizdeki yönetici ve bir departman ajanıyla bu zinciri
  yaklaşık bir dakikada canlandırır. Görev başlatılmaz, ajanlara veya sunucuya hiçbir şey gönderilmez; liste ve
  son iletişimler gerçek durumu göstermeye devam eder. **Gösterimi durdur** veya başka görünüme geçmek gösterimi
  bitirir. Gösterim için ofiste bir yönetici ajan ve en az bir departman ajanı olmalıdır.
- Büyük ofis modellerinde yürüyüş en fazla 6 saniye sürer; uzak noktalara daha hızlı yürünür.
- Bilgisayarda **Hareketi azalt** (macOS: Erişilebilirlik → Ekran; Windows: Erişilebilirlik → Görsel efektler →
  Animasyon efektleri kapalı) açıksa karakterler yürümez, yalnız balonlar görünür.
- **Gerçek bir görevle görmek için** yönetici ajana (karakterine tıklayıp **Görev ver** veya **Yöneticiye yaz**)
  şuna benzer bir talimat verin; köşeli parantezleri kendi departman ve konularınızla değiştirin:

  > [Departman A] ajanından [konu] hakkında internette kısa bir araştırma yapmasını, [Departman B] ajanından da
  > [iş] için bugünkü durumun özetini çıkarmasını iste. Belirsiz bir nokta olursa sana sorsunlar. Sonuçları topla
  > ve bana tek bir özet ver.

  Yönetici görevleri dağıtırken yürür. İnternet araştırması izni açık olan departman araştırma köşesine gider.
  Bitiren departman sonucu yöneticiye götürür. Ajanlar ofis 3 saniyede bir yenilendiğinde güncellenir; çok kısa
  süren işlerin ara adımları görünmeyebilir.

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
