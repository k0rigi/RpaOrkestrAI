# Kullanıcı girişi ve lisans

0.5.0 sürümünden itibaren RpaOrkestrAI, orkestrai.net hesabıyla açılır. Uygulama orkestrai.net'in bir modülü olarak lisanslanır. Kural web modülleriyle aynıdır: kullanıcının RpaOrkestrAI'yi kullanabilmesi için hem firmasında hem kendi hesabında **MOD_RPA** modülünün açık olması gerekir.

## Kullanıcı için

1. Uygulamayı açın. Giriş ekranında orkestrai.net **kullanıcı adınızı** ve **şifrenizi** yazın. Kullanıcı adı, e-posta adresinizin `@` işaretinden önceki kısmıdır; e-postanın tamamını da yazabilirsiniz.
2. Giriş başarılıysa Studio açılır. Sol alttaki kartta adınız, firmanız ve lisans bitiş tarihi görünür. Son 30 günde kalan gün sayısı gösterilir.
3. Sonraki açılışlarda şifre sorulmaz. Uygulama lisansı arka planda saatlik olarak yeniler.

Şifre bu bilgisayara kaydedilmez. Bilgisayarda yalnız orkestrai.net'in imzaladığı lisans ile bu bilgisayara bağlı bir yenileme oturumu tutulur. Oturum, açılış ve yenilemelerle 30 gün boyunca kendini tazeler. Orkestrai.net'te şifreniz değişirse oturum kapanır ve yeniden giriş istenir.

**Bağlantılar ve ayarlar → RpaOrkestrAI lisansı** bölümünde lisans durumunu görebilir, **Lisansı şimdi doğrula** ile hemen yenileyebilir veya **Oturumu kapat** ile başka bir kullanıcıya geçebilirsiniz. Oturumu kapatmak akışları ve bağlantı ayarlarını silmez.

### İnternet olmadığında

Uygulama, orkestrai.net ile son başarılı doğrulamadan sonra **en fazla 7 gün** internetsiz kullanılabilir. Bu süre firmanın lisans bitiş tarihini hiçbir zaman aşmaz. 7 gün dolduğunda Studio kilitlenir; internete bağlanıp **Yeniden doğrula** düğmesine basın.

Bilgisayarın saatini geri almak lisansı uzatmaz. Saat geri alınmışsa internet bağlantısıyla yeniden doğrulama istenir. Lisans, uygulamanın bu bilgisayar için ürettiği cihaz kimliğine bağlıdır. Çalışma alanı başka bir bilgisayara kopyalanırsa orada yeniden giriş gerekir.

### Süre dolduğunda veya yetki yoksa

- **Kullanım süreniz dolmuştur:** Firmanın MOD_RPA bitiş tarihi geçmiştir. Uygulama uyarıyı gösterir ve 15 saniye sonra kapanır. **Şimdi kapat**, **Yeniden kontrol et** veya **Farklı kullanıcıyla giriş yap** seçilebilir. Yönetici süreyi uzattıktan sonra **Yeniden kontrol et** ile uygulama şifre sorulmadan açılır.
- **Lisans tanımlı değil:** Kullanıcıya veya firmaya MOD_RPA atanmamıştır. Uygulama aynı şekilde uyarıp kapanır.

Tarayıcıdan (`rpa-studio`) kullanımda pencere kapatılamaz. Studio yine kilitlenir ve sekmeyi kapatmanız istenir. Lisans çalışma sırasında dolarsa yeni işlem başlatılamaz. O an devam eden bir çalışma varsa kesilmez; bitmesi beklenir.

## Yönetici için: yetki verme

Lisanslar orkestrai.net veritabanındaki mevcut modül tablolarıyla yönetilir.

| Tablo | Kayıt |
| --- | --- |
| `SYS_Moduller` | `ModulKodu = 'MOD_RPA'` (API ilk açılışta kendisi oluşturur) |
| `SYS_FirmaModulleri` | Firmanın MOD_RPA satırı; `BitisTarihi` lisansın son günüdür, boş ise süresizdir |
| `SYS_KullaniciModulleri` | Uygulamayı kullanacak her kullanıcı için MOD_RPA satırı |

Modül kaydı ilk oluşturulduğunda ilk müşteri firmaya bir yıllık lisans verildi ve belirlenen kullanıcıya modül atandı. Başka bir firmaya veya kullanıcıya yetki vermek için ilgili satırları ekleyin. Süreyi uzatmak için firmanın `BitisTarihi` değerini güncelleyin. `Admin` rolündeki orkestrai.net hesapları, web modüllerinde olduğu gibi tüm modüllere erişir.

Yetki değişikliği uygulamaya en geç bir sonraki yenilemede, yani uygulama açıkken en fazla 1 saat içinde yansır. Uygulama internetsizse değişiklik 7 günlük çevrimdışı süre içinde yansımayabilir.

## Teknik ayrıntılar

| Uç | Görev |
| --- | --- |
| `POST https://orkestrai.net/api/rpa/lisans/giris` | Kullanıcı adı/e-posta, şifre ve cihaz kimliğiyle lisans alır. Web girişiyle aynı hatalı deneme sınırı (15 dakikada hesap başına 10) uygulanır. |
| `POST https://orkestrai.net/api/rpa/lisans/yenile` | Cihaza bağlı 30 günlük oturumla lisansı yeniler. Yetki ve süre her seferinde veritabanından okunur. |
| `GET https://orkestrai.net/api/rpa/lisans/anahtar` | Lisans imzasının açık anahtarı. Uygulamaya gömülüdür (`licensing.LICENSE_PUBLIC_KEY`). |

Lisans, orkestrai.net sunucusunda Ed25519 ile imzalanır. Özel anahtar `/home/orkestrai.net/.orkestrai_rpa_lisans_ed25519` dosyasında, web klasörünün dışında durur ve dağıtımlarla değişmez. Bu dosya silinirse sunucu yeni anahtar üretir. Bu durumda kurulu uygulamalar, yeni açık anahtarı içeren bir sürüm yayımlanana kadar lisans yenileyemez; güncelleme mekanizması lisanstan bağımsız çalışmaya devam eder. Bu nedenle dosyayı sunucu yedeğine dahil edin.

Yerel Studio API'sinde `/api/health`, `/api/instance` ve `/api/license*` dışındaki tüm uçlar geçerli lisans ister. Lisans yoksa bu uçlar `403` ve lisans durumunu döndürür. Studio ekranı bu yanıtla giriş veya uyarı ekranına geçer.
