# Masaüstü uygulama ve güncelleme mimarisi

RpaOrkestrAI Studio, Windows'ta kurulum EXE'si, macOS'ta DMG içindeki `.app` ile
dağıtılır. Her paket kendi Python yorumlayıcısını ve gerekli Python bağımlılıklarını
taşır. Kullanıcının Python kurması, sanal ortam oluşturması veya terminali açık
tutması gerekmez. Kaynak koddan geliştirme için standart 64 bit Python 3.11–3.14
desteklenir; dağıtım paketinin Python sürümü kullanıcının sistem Python'undan
bağımsızdır.

## İlk kurulum ve sonraki sürümler

Güncelleme altyapısının başlangıç sürümü **0.2.0**'dır. Daha eski paketlerde bu
altyapı bulunmadığından 0.2.0'ın ilk kurulumu indirme sayfasından yapılır. Windows'ta
EXE kurulur; Mac'te `.app`, DMG'den Uygulamalar klasörüne taşınır ve oradan açılır.

Kurulu uygulama açılışta daha önce indirilmiş, doğrulanmış bir güncelleme olup
olmadığına bakar. Yeni sürüm denetimi ve indirme arka planda gerçekleşir. İndirilen
paket bir sonraki açılışta tekrar doğrulanıp kurulur; böylece devam eden bir ERP
işleminin ortasında uygulama değiştirilmez. Kurulumdan sonra uygulama yeniden açılır.
Mac'te DMG içinden çalışan veya mevcut kullanıcının değiştiremediği konuma kurulmuş
bir kopya için elle kurulum gerekebilir.

İnternet bağlantısı yoksa, sunucuya ulaşılamıyorsa, bildirim geçersizse veya indirme
yarım kalırsa mevcut sürüm çalışmaya devam eder. Doğrulanmamış paket çalıştırılmaz.
Uygulamayı kaynak koddan çalıştırmak otomatik olarak kaynak kodu veya Python ortamını
değiştirmez; otomatik kurulum paketlenmiş masaüstü uygulaması içindir.

## Kullanıcı verileri

Program dosyaları ile çalışma alanı farklı konumlarda tutulur:

| Platform | Kullanıcının çalışma alanı |
| --- | --- |
| Windows | `%LOCALAPPDATA%\RpaOrkestrAI\workspace` |
| macOS | `~/Library/Application Support/RpaOrkestrAI/workspace` |

Akışlar, favoriler ve bağlantı ayarları bu çalışma alanında kalır. Güncelleme,
çalışma alanını silmez veya yeni bir paketin içine kopyalamaz. Sunucuda yalnızca
program paketleri ve yayın bilgisi bulunur; ERP verileri veya Google Sheets bağlantı
anahtarları yayımlanmaz.

Bir kullanıcının akışına adım eklemesi veya bir adımın ayarını değiştirmesi o
bilgisayardaki akışı değiştirir. Kodla yeni bir adım türü geliştirilmesi ise uygulama
sürümü artırılarak, test edilerek ve yeni paketler yayımlanarak tüm kurulumlara
ulaştırılır. Bu iki işlem birbirinden bağımsızdır.

## Sunucudaki dosyalar

Hedef indirme adresi `https://orkestrai.net/rpa/`, güncelleme bildirimi ise
`https://orkestrai.net/rpa/stable.manifest` adresidir. Bu bölüm statik dosya sunumu
için tasarlanmıştır; ayrıca bir Python sunucusu veya veritabanı gerekmez.

```text
rpa/
  index.html
  stable.manifest
  releases/
    0.2.0/
      RpaOrkestrAI-Setup-0.2.0-Windows-x64.exe
      RpaOrkestrAI-0.2.0-macOS-arm64.dmg
```

Intel Mac paketi üretildiğinde aynı sürüm klasörüne ayrı bir `macos-x64` DMG'si
eklenebilir. `stable.manifest` JSON içeriği taşır; uzantısı, mevcut sitenin `.json`
ve `.zip` erişim kurallarıyla çakışmaması için `.manifest` olarak seçilmiştir.
Sunucu bu dosyayı UTF-8 olarak, dönüştürmeden sunmalıdır. Bildirim için önbelleğin
devre dışı bırakılması veya her istekte yeniden doğrulanması uygundur; sürümlü
EXE/DMG dosyaları değişmez dosyalar olarak uzun süre önbelleğe alınabilir.

Bu belge hedef dizin ve yayın protokolünü açıklar. Yayın hazırlama komutu tek başına
sunucuya bağlanmaz, dosya yüklemez veya bir sunucu iş akışını etkinleştirmez.

## Yayın güveni

Bildirim; sürümü, kanalı, yayın/geçerlilik tarihlerini ve her platform için indirme
adresi, boyut, dosya türü ve SHA-256 özetini içerir. Tam UTF-8 bildirim baytları
Ed25519 özel anahtarıyla imzalanır; zarf `payload` ve `signature` alanlarında
Base64 değerleri taşır. Uygulama yalnız kendi içine gömülü açık anahtarla doğrulanan
bildirimleri kabul eder. İndirme tamamlandığında ve kurulumdan hemen önce dosya
boyutu, özet ve imza yeniden doğrulanır.

İndirmeler HTTPS ile ve yapılandırılmış sunucu/dizin sınırında yapılır. Sürüm geriye
alınmaz; aynı sürüm yeniden kurulmaz. Varsayılan bildirim geçerliliği 90 gündür.
Süre dolmadan bildirim aynı dosya özetleriyle yeniden imzalanıp yayımlanmalıdır.
Süresi dolmuş bildirim güncellemeyi durdurur; kurulu programın çalışmasını durdurmaz.

Özel anahtar `credentials/update-signing-ed25519.pem` gibi Git tarafından yok
sayılan bir konumda saklanır. Anahtar uygulama paketine, yayın klasörüne, sunucuya
veya Git'e eklenmez. Anahtarı şifreli, erişimi sınırlı bir yedekte koruyun: mevcut
uygulamalar gömülü açık anahtara güvendiği için özel anahtarın kaybı, bu kurulumlara
aynı güven zinciriyle güncelleme yayımlamayı engeller. Bir anahtarı değiştirirken
kurulu uygulamaların yeni anahtara nasıl geçeceği ayrıca planlanmalıdır.

Bu imza **Apple Developer ID/noter onayı veya Windows Authenticode sertifikası
değildir**. Güncelleme yayınının doğrulanmasını sağlar. İşletim sistemi tarafından
tanınan yayıncı imzası ayrı yapılandırılır; henüz yoksa ilk kurulumda sistem veya
kurum politikalarının gerektirdiği onaylar çıkabilir.

## Bir sürümü hazırlama

Önce uygulama sürümünü artırın ve iki işletim sisteminde paket üretimi ile testleri
tamamlayın. Sonra proje kökünde, proje bağımlılıklarının kurulu olduğu bir Python
ortamıyla çalıştırın:

```sh
python scripts/prepare_update_release.py \
  --version 0.2.0 \
  --windows dist/RpaOrkestrAI-Setup-0.2.0-Windows-x64.exe \
  --macos-arm64 dist/RpaOrkestrAI-0.2.0-macOS-arm64.dmg \
  --signing-key credentials/update-signing-ed25519.pem \
  --output dist/update-site \
  --archive dist/publish-bundle.tar.gz
```

Girdi yollarını derleme çıktılarınızın gerçek konumlarına göre değiştirin. Çıktı
klasörü yeni veya boş olmalıdır; mevcut yayın sessizce üzerine yazılmaz. İsteğe
bağlı `--macos-x64` Intel paketini ekler. `--expires-in-days` bildirim geçerliliğini
1–365 gün aralığında ayarlar. `--archive` yalnızca bilinen yayın dosyalarını içeren
bir taşıma arşivi üretir; çalışma dizini veya kimlik bilgileri arşivlenmez.

Komut, özel anahtarın uygulamadaki açık anahtarla eşleşmesini kontrol eder;
hazırladığı bildirimi ve kopyalanan paketleri uygulamanın gerçek güncelleme istemcisiyle
doğrular. Bu kontrol EXE/DMG içindeki programın uçtan uca testinin yerine geçmez;
paket açılış kontrolleri yayın hazırlanmadan önce yapılmalıdır.

Sunucuya önce `releases/<sürüm>/` altındaki paketler, ardından indirme sayfası
aktarılır. Paketler sunucudan indirilebildikten ve özetleri doğrulandıktan sonra
**`stable.manifest` en son, geçici dosyadan atomik yeniden adlandırmayla** yayımlanır.
Böylece istemciler henüz aktarımı bitmemiş bir sürüme yönlendirilmez. Önceki sürümün
paketleri tutulur; aynı sürüm numarasındaki dosyaların içeriği değiştirilmez.

## Mevcut hosting deposuyla yayına alma

`k0rigi/orkestrai` hosting deposundaki **Publish RpaOrkestrAI desktop downloads**
iş akışı yalnız `/home/orkestrai.net/public_html/rpa` dizinini yönetir. Yapılandırma
`.github/workflows/publish-rpa.yml`, betik `.github/scripts/publish-rpa.py`
konumundadır. Bu projedeki kaynakları sırasıyla
`packaging/hosting/publish-rpa.yml` ve `scripts/deploy_update_bundle.py` dosyalarıdır.
Bu iki dosya hosting deposuna eklenirken veya güncellenirken commit mesajına
**`[skip ci]`** eklenir; mevcut, tüm web sitesini dağıtan ayrı iş akışının bu araç
değişikliği nedeniyle tetiklenmesi önlenir. RPA yayını ayrıca elle başlatılır.

İş akışı mevcut `HOST`, `USERNAME` ve `PASSWORD` GitHub Secrets değerlerini
kullanır. Bunlar masaüstü uygulamasına, indirme sayfasına veya güncelleme paketine
girmez. SSH sunucusunun bilinen açık anahtarı sabitlenmiştir; bilinmeyen sunucu
anahtarı otomatik kabul edilmez.

1. İmzalı yayın klasörüyle birlikte `publish-bundle.tar.gz` üretin ve arşivin
   SHA-256 özetini alın. Arşiv, özel GitHub deposunda geçici aktarım dosyası olarak
   tutulabilir; sunucunun GitHub erişim anahtarına ihtiyacı yoktur.
2. Hosting deposunda **Actions → Publish RpaOrkestrAI desktop downloads → Run
   workflow** yoluyla `action: inspect` çalıştırın. Bu işlem yalnız hedef dizinin
   erişimini ve mevcut yayın sürümünü okur; dizin oluşturmaz veya dosya değiştirmez.
3. Yayın için `action: publish`, `version`, `bundle_sha256` ve `bundle_url`
   alanlarını doldurun. `bundle_url`, GitHub'ın verdiği kısa ömürlü
   `https://release-assets.githubusercontent.com/…` indirme adresidir; normal
   Release sayfası bağlantısı değildir. Adresi belgeye veya commit'e yazmayın.
   İş akışı bunu doğrudan olay dosyasından okur; komut satırına veya günlüğe basmaz.
4. İş akışı arşivi indirip boyut/özet kontrolü yapar, bildirimin Ed25519 imzasını ve
   paketleri uygulamadaki yayıncı açık anahtarıyla doğrular. Ardından sunucuya özel
   geçici dosya olarak aktarır. Sunucu yeniden arşiv ve paket özetlerini denetler;
   yalnız izin verilen normal dosyaları çıkarır, farklı içerikle aynı sürümün
   üzerine yazmayı reddeder ve bildirimi en son yayımlar.
5. Başarılı işten sonra indirme sayfasını, bildirimi ve iki platformun paketlerini
   HTTPS üzerinden kontrol edin. Süresi dolan aktarım URL'siyle yeniden denemek
   gerekirse yeni bir kısa ömürlü URL alın; arşiv değişmediyse özeti değişmez.

Bu yayın adımı her sürüm için bilinçli olarak elle başlatılır. Kurulu masaüstü
uygulamalarının yeni yayını bulması, indirmesi ve sonraki açılışta kurması otomatik
gerçekleşir. İş akışı mevcut web uygulamasını, veritabanını veya servisleri yeniden
başlatmaz.
