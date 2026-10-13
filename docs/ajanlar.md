# Ajanlar ve dijital ekip

Ajanlar, kullanıcı hedefini izin verilen akışlarla yerine getirir. Model hangi akışı
hangi girdilerle çalıştıracağını önerir; izin, lisans, onay ve durdurma kararlarını
Studio'nun Python katmanı uygular. Modele doğrudan fare, klavye, dosya, ağ veya komut
aracı verilmez. Bir hedefin bulunamaması tahmini tıklama veya veri girişine dönüşmez.

Bu özellik aşamalar hâlinde geliştirilmektedir. Aşağıdaki çekirdek mevcut geliştirme
dalındadır; yayımlanan sürüm ve gerçek bilgisayar doğrulaması README'de belirtilir.

## Lisans ve kullanıcı

Mevcut `MOD_RPA` lisansı korunur. Ajanlar için hem firmada hem kullanıcı hesabında
ayrıca `MOD_AJAN` gerekir. Sunucunun imzaladığı ajan yetkisi bulunmazsa normal RPA
çalışabilir, ajan uçları kapalı kalır. Kullanıcı ve firma kimliği istek gövdesinden
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
Bilinmeyen bir adım okuma sayılmaz. Genel kabuk/komut/script, sınırsız ağ ve genel
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

Akış çıktıları güvenilmeyen veri olarak işaretlenir. Bir e-posta, OCR sonucu veya
dosya içindeki talimat ajan yetkisini değiştiremez. Metin/CSV/JSON çıktı okumak
yalnız o ajan çalışmasının oluşturduğu dosyalarda ve boyut sınırıyla mümkündür;
keyfi disk yolu kabul edilmez. Modele gönderilen maskeli içerik çalışma zaman
çizelgesinde incelenebilir. Tur, süre, token, akış sayısı ve aynı çağrıyı tekrarlama
sınırları vardır.

## Sağlayıcılar

Ortak arayüz OpenAI, Gemini, Anthropic, Ollama ve OpenAI uyumlu yerel sunucuları
kapsar. Model adı serbest metindir; sağlayıcıda gerçekten bulunan ve araç çağırmayı
destekleyen bir model seçilmelidir. Başka ücretli sağlayıcıya otomatik geçiş yoktur.
Bulut bağlantısı kullanılırsa akış sonuçları o sağlayıcıya gönderilir; hassas veri
için yerel model tercih edilebilir. Bağlantı testi bile bulut sağlayıcıda kullanım
oluşturabilir; test yalnız kullanıcının düğmeye basmasıyla yapılır.

Yerel bağlantı varsayılan olarak loopback adresi kullanır. Ortak sunucu bağlantısı
ayrı kimlik doğrulamalı hizmet gerektirir; Ollama portunu doğrudan internete açmak
desteklenen kurulum değildir. Sağlayıcı istekleri boyut ve süre sınırına tabidir,
yönlendirme izlenmez. Yeniden deneme yalnız ağ hatası, 429 ve 5xx durumlarında
yapılır. Testler gerçek sağlayıcıya istek göndermez.

## Geliştirme ve denetim

`agents/models.py` modelleri mevcut `Model` tabanını ve `extra="forbid"` kuralını
kullanır. Tanımlar `data/agents/`, çalışmalar `data/agent_runs/`, görevler
`data/agent_tasks/` içinde atomik yazılır. Sağlayıcı meta verisi
`data/agent_connections.json` içindedir. Ajan API uçlarının tamamı
`/api/agents` altındadır; lisans, Origin ve gövde sınırları geçerlidir.

Sahte sağlayıcı senaryoları ağsız test içindir; Studio'da gerçek bağlantı olarak
kaydedilemez. Testler izin ve alt akış denetimini, onayı, maskelemeyi, iptali,
lisansı, masaüstü sırasını, sağlayıcı protokollerini ve eski akış uyumunu kapsar.

Organizasyon, insan görevleri, performans ve salt okunur ofis görünümü aynı kimlik
ve izin sınırını kullanacak şekilde ayrı aşamalarda tamamlanır. İş verileri ofis
durum uçlarına taşınmaz. Merkezi görev kaydı ve ortak model verisinin hangi
sunucuya gönderildiği arayüzde ayrıca gösterilir; uzak robot kontrolü açılmaz.
