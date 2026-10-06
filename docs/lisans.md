# Kullanıcı girişi ve lisans

0.5.0 sürümünden itibaren RpaOrkestrAI, orkestrai.net hesabıyla açılır. Uygulama orkestrai.net'in bir modülü olarak lisanslanır. Kural web modülleriyle aynıdır: kullanıcının RpaOrkestrAI'yi kullanabilmesi için hem firmasında hem kendi hesabında **MOD_RPA** modülünün açık olması gerekir.

0.8.0 ile lisans denetimi sıkılaştırıldı:

- Uygulama **her açılışta** orkestrai.net'ten onay alır; onay gelmeden Studio açılmaz. Açıkken onayı 10 dakikada bir yeniler.
- Bir hesap **aynı anda tek bilgisayarda** çalışır.
- Bilgisayarda Studio'yu açan hiçbir bilgi saklanmaz. Dosyaları değiştirmek, eski bir yedeği geri yüklemek veya bilgisayarın tarihini değiştirmek lisans vermez.
- 0.8.0'dan eski sürümlere lisans verilmez.

## Kullanıcı için

1. Uygulamayı açın. Giriş ekranında orkestrai.net **kullanıcı adınızı** ve **şifrenizi** yazın. Kullanıcı adı, e-posta adresinizin `@` işaretinden önceki kısmıdır; e-postanın tamamını da yazabilirsiniz.
2. Giriş başarılıysa Studio açılır. Sol alttaki kartta adınız, firmanız ve lisans bitiş tarihi görünür. Son 30 günde kalan gün sayısı gösterilir.
3. **0.9.6 ve sonrasında her açılışta kullanıcı adı ve şifre yeniden istenir.** Giriş sırasında lisans süresi ve yetkiler orkestrai.net üzerinden doğrulanır; internet bağlantısı gerekir. Güncellemeden sonraki ilk açılış da buna dahildir.

Kullanıcı adı, şifre ve yenileme oturumu diske kaydedilmez. Bilgisayarda yalnız kurulum kimliği tutulur. Önceki sürümlerin kaydettiği oturum ve kullanıcı adı açılışta silinir. Uygulama açık kaldığı sürece oturum bellekte tutulur ve lisans belirli aralıklarla denetlenir. Şifre değişikliği, pasif hesap veya başka bilgisayarda giriş oturumu kapatır.

Zamanlanmış akışlar için de uygulamayı açtıktan sonra giriş yapın. Giriş yapılmadan zamanlanmış işler çalışamaz; uygulama açık ve oturum geçerliyken olağan zamanlama sürer.

**Ayarlar → RpaOrkestrAI lisansı** bölümünde lisans durumunu görebilir, **Lisansı şimdi doğrula** ile hemen yenileyebilir veya **Oturumu kapat** ile başka bir kullanıcıya geçebilirsiniz. Oturumu kapatmak akışları ve bağlantı ayarlarını silmez.

### Tek bilgisayar kuralı

Bir hesap aynı anda yalnız bir bilgisayarda çalışır. Başka bir bilgisayarda giriş yaptığınızda önceki bilgisayardaki oturum kapanır: oradaki Studio en geç 10 dakika içinde giriş ekranına döner ve nedenini yazar; o sırada çalışan akış varsa bir sonraki adımda durdurulur.

- Bilgisayar değiştirmek için yeni bilgisayarda giriş yapmanız yeterlidir. Eski bilgisayarda **Oturumu kapat** demeniz gerekmez.
- Çalışma alanını (veri klasörünü) başka bir bilgisayara kopyalamak oturumu taşımaz; orada yeniden giriş gerekir.
- Aynı oturumun iki yerde birden kullanıldığı fark edilirse oturum kapatılır ve yeniden giriş istenir.
- Uygulamayı birden fazla kişi kullanacaksa her kişi için ayrı hesap ve MOD_RPA yetkisi tanımlanır.

### İnternet olmadığında

RpaOrkestrAI kullanılan bilgisayarın `https://orkestrai.net` adresine (443 numaralı port) erişebilmesi gerekir. Kurumsal güvenlik duvarı veya vekil sunucu (proxy) kullanılıyorsa bu adrese izin verin.

- **Açılışta:** Giriş ekranı gösterilir. Bağlantı yoksa giriş doğrulanamaz ve Studio açılmaz. Bağlantı geldikten sonra kullanıcı adı ve şifreyle yeniden giriş yapın.
- **Çalışırken:** Bağlantı kesilirse Studio en fazla **60 dakika** daha çalışır. Bu sürede bağlantı gelmezse Studio kilitlenir ve çalışan akış durdurulur. Bağlantı geldiğinde Studio kendiliğinden açılır; açık akıştaki kaydedilmemiş değişiklikler yerinde durur.
- Uygulamayı kapatıp açmak bu süreyi yenilemez: her açılış yeni bir onay ister.

60 dakikalık süre bilgisayarın saatine göre değil, uygulamanın çalışma süresine göre ölçülür. Bu yüzden bilgisayarın tarihini ya da saatini değiştirmek süreyi uzatmaz; saati yanlış olan bir bilgisayarda da uygulama gereksiz yere kilitlenmez.

### Süre dolduğunda veya yetki yoksa

- **Kullanım süreniz dolmuştur:** Firmanın MOD_RPA bitiş tarihi geçmiştir. Uygulama uyarıyı gösterir ve 15 saniye sonra kapanır. **Şimdi kapat**, **Yeniden kontrol et** veya **Farklı kullanıcıyla giriş yap** seçilebilir. Yönetici süreyi uzattıktan sonra açık oturumda **Yeniden kontrol et** kullanılabilir; uygulama kapatılmışsa tekrar giriş gerekir.
- **Lisans tanımlı değil:** Kullanıcıya veya firmaya MOD_RPA atanmamıştır. Uygulama aynı şekilde uyarıp kapanır.
- **Bu sürüm artık desteklenmiyor:** Kurulu sürüm, orkestrai.net'in kabul ettiği en düşük sürümden eskidir. Güncelleme arka planda indirilir ve uygulamayı kapatıp açtığınızda kurulur. Kurulmazsa güncel paketi `https://orkestrai.net/rpa` adresinden indirin. Akışlarınız ve ayarlarınız olduğu gibi kalır.

Tarayıcıdan (`rpa-studio`) kullanımda pencere kapatılamaz. Studio yine kilitlenir ve sekmeyi kapatmanız istenir.

Yetki kaldırılır, süre dolar veya oturum başka bilgisayara geçerse yeni işlem başlatılamaz ve **o an çalışan akış bir sonraki adımda durdurulur**. Çalışma kaydında durdurulma nedeni yazar. Yarım kalan ERP işlemini çalışma kaydındaki son adımdan kontrol edin.

## Yönetici için: yetki verme

Lisanslar orkestrai.net veritabanındaki mevcut modül tablolarıyla yönetilir.

| Tablo | Kayıt |
| --- | --- |
| `SYS_Moduller` | `ModulKodu = 'MOD_RPA'` (API ilk açılışta kendisi oluşturur) |
| `SYS_FirmaModulleri` | Firmanın MOD_RPA satırı; `BitisTarihi` lisansın son günüdür, boş ise süresizdir |
| `SYS_KullaniciModulleri` | Uygulamayı kullanacak her kullanıcı için MOD_RPA satırı |
| `SYS_RpaOturumlari` | Açık ve kapanmış uygulama oturumları (API kendisi oluşturur ve yazar; elle kayıt eklenmez) |

Modül kaydı ilk oluşturulduğunda ilk müşteri firmaya bir yıllık lisans verildi ve belirlenen kullanıcıya modül atandı. Başka bir firmaya veya kullanıcıya yetki vermek için ilgili satırları ekleyin. Süreyi uzatmak için firmanın `BitisTarihi` değerini güncelleyin. `Admin` rolündeki orkestrai.net hesapları, web modüllerinde olduğu gibi tüm modüllere erişir.

Yetki değişikliği açık uygulamalara **en geç 10 dakika içinde** yansır. Kapalı uygulama bir sonraki açılışında onay alamaz ve açılmaz. Yetkiyi geri verdiğinizde kullanıcı **Yeniden kontrol et** ile ya da en geç 10 dakika içinde şifre girmeden devam eder.

Bir kullanıcının kullanımını hemen kesmek için MOD_RPA satırını silin, hesabını `Pasif` yapın ya da şifresini değiştirin. Son iki durumda oturum da kapanır ve yeniden giriş gerekir.

`SYS_RpaOturumlari` tablosunda her oturumun kullanıcısı, cihaz kimliği, uygulama sürümü, IP adresi, açılış ve son görülme zamanı, durumu (`Aktif` / `Kapandi`) ve kapanma nedeni görülür:

| Kapanma nedeni | Anlamı |
| --- | --- |
| `BASKA_CIHAZ` | Hesap başka bir bilgisayarda açıldı |
| `YENI_GIRIS` | Aynı bilgisayarda yeniden giriş yapıldı |
| `CIKIS` | Kullanıcı **Oturumu kapat** dedi |
| `KOPYA` | Aynı oturum iki yerde birden kullanıldı |

Kapanmış oturumlar 90 gün sonra silinir.

## Teknik ayrıntılar

| Uç | Görev |
| --- | --- |
| `POST https://orkestrai.net/api/rpa/lisans/giris` | Kullanıcı adı/e-posta, şifre ve cihaz kimliğiyle oturum açar ve lisans verir; hesabın başka bilgisayardaki oturumu kapanır. Web girişiyle aynı hatalı deneme sınırı (15 dakikada hesap başına 10) uygulanır. |
| `POST https://orkestrai.net/api/rpa/lisans/yenile` | Cihaza bağlı oturumla taze lisans verir. Yetki, süre, oturum ve uygulama sürümü her seferinde veritabanından denetlenir. |
| `POST https://orkestrai.net/api/rpa/lisans/cikis` | Uygulamadaki **Oturumu kapat**: bu bilgisayarın oturumunu sunucuda da kapatır. |
| `GET https://orkestrai.net/api/rpa/lisans/anahtar` | Lisans imzasının açık anahtarı, protokol numarası ve lisans verilen en düşük uygulama sürümü (`asgari_surum`). Açık anahtar uygulamaya gömülüdür (`licensing.LICENSE_PUBLIC_KEY`). |

Doğrulama şöyle çalışır (protokol 2):

- Uygulama her istekte rastgele bir değer üretir. orkestrai.net bu değeri lisansın içine yazar ve lisansı Ed25519 ile imzalar. Uygulama imzayı gömülü açık anahtarla doğrular; cihaz kimliğinin ve rastgele değerin kendi isteğine ait olduğunu denetler. Böylece her yanıt yalnız bir isteğe aittir; daha önce alınmış bir yanıt yeniden kullanılamaz.
- Onay yalnız çalışan uygulamanın belleğinde tutulur. `data/license.json` dosyasında yalnız kurulum kimliği vardır; oturum belirteci, kullanıcı adı, lisans ve şifre yoktur.
- Oturum belirteci her doğrulamada yenilenir ve bir sıra numarası taşır. Sunucu her hesap için tek etkin oturum tutar. Yanıtı yolda kaybolan bir istek aynı uygulama tarafından yinelenebilir; aynı oturumun başka bir kopyası ise fark edilir.
- Yenileme aralığı (10 dakika) ve bağlantısız çalışma süresi (60 dakika) imzalı lisansın içinde gelir ve sunucuda (`api/app.py`: `RPA_YENILEME_ARALIGI`, `RPA_CALISMA_TOLERANSI`) ayarlanır. Uygulama bu değerleri 1–60 dakika ve 5 dakika–6 saat aralığına sınırlar.
- Sunucu, `RPA_ASGARI_SURUM` değerinden (şu an 0.8.0) eski uygulamalara lisans vermez; protokol 2 ve isteğe özel rastgele değer de zorunludur. Güvenlikle ilgili bir sürüm yayımlandıktan sonra bu değer yükseltilir.

Lisans, orkestrai.net sunucusunda Ed25519 ile imzalanır. Özel anahtar `/home/orkestrai.net/.orkestrai_rpa_lisans_ed25519` dosyasında, web klasörünün dışında durur ve dağıtımlarla değişmez. Bu dosya silinirse sunucu yeni anahtar üretir. Bu durumda kurulu uygulamalar, yeni açık anahtarı içeren bir sürüm yayımlanana kadar lisans doğrulayamaz; güncelleme mekanizması lisanstan bağımsız çalışmaya devam eder. Bu nedenle dosyayı sunucu yedeğine dahil edin.

Yerel Studio API'sinde `/api/health`, `/api/instance` ve `/api/license*` dışındaki tüm uçlar geçerli lisans ister. Lisans yoksa bu uçlar `403` ve lisans durumunu döndürür; Studio ekranı bu yanıtla giriş, doğrulama veya uyarı ekranına geçer. Akış başlatma ayrıca çalıştırma motorunda da denetlenir.

Yayınlanan kurulum paketlerinden yalnız güncel sürüm sunucuda tutulur; eski sürümlerin paketleri her yayından sonra kaldırılır.
