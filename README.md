# RpaOrkestrAI

**macOS ve Windows için Python tabanlı, yerelde çalışan görsel RPA uygulaması.** Uygulama sahipleri Studio üzerinden otomasyon adımları ekler, koşul ve döngüleri düzenler, akışları kaydeder ve çalıştırır. Çalışma çıktıları CSV olarak departmanlara verilebilir; akış tanımları JSON olarak başka kurulumlara taşınabilir.

Studio, FastAPI üzerinden sunulan bir web arayüzüdür. İsterseniz aynı arayüzü pywebview ile yerel uygulama penceresinde açabilirsiniz. Masaüstü işlemleri uygulamanın çalıştığı bilgisayarda gerçekleşir.

## Masaüstü uygulaması olarak kullanım

Hazır kurulum dosyaları için **[RpaOrkestrAI indirme sayfası](https://orkestrai.net/rpa/)** kullanılır. GitHub'daki alternatif dağıtım yeri [Releases](https://github.com/k0rigi/RpaOrkestrAI/releases) bölümüdür; özel depoya erişim için GitHub hesabınızla giriş yapın.

- **Windows:** `RpaOrkestrAI-Setup-0.9.44-Windows-x64.exe` dosyasını çalıştırın; ardından masaüstündeki **RpaOrkestrAI Studio** kısayolunu açın.
- **MacBook (Apple Silicon: M1 ve sonrası):** `RpaOrkestrAI-0.9.44-macOS-arm64.dmg` dosyasını açın, içindeki **RpaOrkestrAI.app** uygulamasını **Applications** kısayoluna sürükleyin; `/Applications/RpaOrkestrAI.app` üzerinden açın. Bu paket Intel Mac için değildir.

**0.9.6 ile her uygulama açılışında kullanıcı adı ve şifre yeniden istenir.** Girişte lisans süresi ve yetkiler orkestrai.net üzerinden kontrol edilir; oturum diske kaydedilmez. Kullanıcının firmasında ve kendi hesabında **MOD_RPA** modülünün açık, firma lisans süresinin dolmamış olması gerekir. Süresi dolmuş veya lisansı tanımlı olmayan kullanıcıya uygulama uyarı verip kapanır. **0.8.0 ile** uygulama her açılışta orkestrai.net'ten onay alır (internet gerekir), açıkken bağlantı kesilirse en fazla 60 dakika çalışır ve bir hesap aynı anda tek bilgisayarda kullanılır; 0.8.0'dan eski sürümlere lisans verilmez. [Kullanıcı girişi ve lisans](docs/lisans.md).

Bu paketler kendi Python 3.12 yorumlayıcısını içerir ve terminal açmadan çalışır; bilgisayara ayrıca Python 3.14 kurulması onları etkilemez. **Code → Download ZIP** kaynak kod indirmesidir. `start.command` ve `start.bat`, terminale bağlı geliştirme başlatıcılarıdır; terminal kapatılırsa bu şekilde açılan süreç de kapanabilir. Yeni derlemelerin paketleri **Actions → Build desktop apps → Artifacts** bölümünde bir gün durur; yayınlanan güncel sürüm orkestrai.net/rpa adresindedir. [Masaüstü dağıtım rehberi](docs/masaustu-dagitim.md).

**0.1.x kullananlar güncel sürümü bir kez elle kurmalıdır.** 0.2.0 ve sonraki kurulu uygulamalar açılışta yeni sürümü arka planda kontrol edip doğrulayarak indirir; hazır güncellemeyi sonraki açılışta kurar. Güncelleme indirilemezse mevcut sürüm kullanılmaya devam eder; akışlar ve bağlantı ayarları korunur. Studio'nun açılması için lisans doğrulaması nedeniyle internet bağlantısı gerekir. Kendi akışınıza eklediğiniz adımlar yerel kalır; kodla geliştirilen yeni adım türleri yeni uygulama sürümü yayımlandığında diğer kurulumlara ulaşır. [Güncelleme mimarisi](docs/guncelleme-mimarisi.md).

**0.9.44:** **Telegram kurulumu:** bağlantı penceresindeki **Sohbetleri bul** anahtarın hangi bota ait olduğunu yazar ve sohbet bulunamazsa nedenini söyler (bota henüz yazılmamış, webhook tanımlı veya başka bir program okuyor). **Sohbet kimliği**ne botun adı yazılamaz; buraya mesajın gideceği kişinin numarası gelir. Telegram hataları Telegram'ın verdiği gerçek nedenle açıklanır. **Ajan akış izinleri:** ajana verilemeyen akışın altında hangi adımın neden engellediği yazar. [Telegram'dan soru ve onay](docs/ajanlar.md#telegramdan-soru-ve-onay-0938).

**0.9.43:** **Ofisi sil:** ofisin yetkilisi Ofisim sekmesinde ofisin adını aynen yazarak boş bir ofisi siler. Ofiste başka çalışan, açık insan görevi, bekleyen onay veya bu bilgisayarda o ofise ait ajan varsa silinmez ve eksik olan yazılır; biten görevler ve denetim kayıtları korunur, ofisin bu bilgisayardaki 3D modeli silinir. orkestrai.net tarafı bu sürümle birlikte güncellendi. [Kendi ofisinizi kurmak](docs/ajanlar.md#kendi-ofisinizi-kurmak-0936).

**0.9.42:** **Yenilikler:** güncellemeden sonraki ilk açılışta son sürümde nelerin değiştiği gösterilir; üst çubuktaki sürüm numarasından veya Ayarlar → Uygulama güncellemeleri → **Sürüm notları**'ndan her zaman açılır. **Güncelleme görünür:** Studio kapatılıp açıldığında güncelleme kurulurken "RpaOrkestrAI x sürümüne güncelleniyor" penceresi görünür; bitince Studio kendiliğinden açılır. **Akış adı:** düzenleyicide akışın adına tıklayarak veya Akışlar sayfasındaki **Adını değiştir** ile değiştirilir; listeden yapılan değişiklik hemen kaydedilir. **3D ofis:** ajana soru sorarken Enter soruyu gönderir (Shift + Enter yeni satır). [Güncelleme mimarisi](docs/guncelleme-mimarisi.md).

**0.9.41:** **Telegram'dan görev ve soru:** bota `/gorev metin` yazarak ofisinizin yöneticisine (veya `Ajan adı:` ile belirli bir ajana) görev verir, `/sor` ya da komutsuz mesajla iş başlatmadan soru sorarsınız; `/ajanlar` ofis ve ajanları listeler. Birden fazla ofiste mesaj ofis adıyla başlar; iş tahminle bir ajana verilmez. Görev bitince sonucu Telegram'a yazılır. Telegram'dan verilen görevler, sorular, yanıtlar ve onay kararları Studio kayıtlarında "Telegram'dan" olarak görünür. Studio kapalıyken gönderilen komutlar çalıştırılmaz. [Telegram'dan görev ve soru](docs/ajanlar.md#telegramdan-görev-ve-soru-0941).

**0.9.40:** **Düğme olarak işaretlenmemiş web düğmeleri:** Visual WebGui gibi düğmeleri düz öğelerle çizen sitelerde **Düğme veya bağlantı adı** artık tam bu yazıyı taşıyan tek tıklanabilir öğeyi bulur; birden fazla varsa tıklamaz. **Dosya uzantısı kontrolü:** yeni **Dosya bilgisi ve uzantı kontrolü** adımı dosyanın uzantısını, boyutunu ve içerik türünü verir; izin verilen uzantıları ve içeriğin uzantıyla uyuşmasını denetler (ör. `.xlsx` adıyla inen web sayfası). Yeni **Kullanıcıya dosya seçtir** adımı yalnız izin verilen türleri gösteren Aç penceresini açar. **Web'den dosya indir** adımına **İzin verilen uzantılar** eklendi. **Ajanları hareket halinde görmek:** Ofis'teki **Gösterimi oynat**, ofisinizdeki yönetici ve departman ajanlarıyla görev, araştırma, soru, yanıt ve sonuç teslimini gerçek iş başlatmadan canlandırır; büyük ofislerde yürüyüşler en fazla 6 saniye sürer. Yeni adımları veya indirmede uzantı alanını kullanan akışlar 0.9.40 öncesi sürümlerde açılmaz. [Adımlar](docs/adimlar.md), [Web otomasyonu](docs/web-otomasyonu.md), [Ajanları hareket halinde görmek](docs/ajanlar.md#ajanları-hareket-halinde-görmek-0940).

**0.9.39:** **Web öğesine tıkla** adımına **Tıklama türü** eklendi: tek tık, çift tık, sağ tık, orta tık veya tıklamadan yalnız üzerine gelme (fareyle açılan menüler için). Varsayılan tek tıktır ve akış dosyasına yazılmaz; başka bir tıklama türü seçilen akışlar 0.9.39 öncesi sürümlerde açılmaz. [Web otomasyonu](docs/web-otomasyonu.md).

**0.9.38:** **Telegram'dan soru ve onay:** bilgisayar başında değilken ajanların soruları Telegram'a gelir; yanıtı düğmeyle veya mesajı yanıtlayarak verirsiniz, onay yetkiliyseniz riskli işlemleri **Onayla / Reddet** düğmeleriyle kararlaştırırsınız. Yalnız kayıtlı özel sohbetiniz kabul edilir. **Ofis modeli yerleşim sözleşmesi:** kendi GLB ofisiniz artık sürümlü bir sözleşmeye uymalıdır. Model; çalışma, bekleme, oturma ve buluşma noktalarını ve yürünebilir yol ağını adlandırılmış görünmez noktalarla tanımlar. Ajanlar bu noktalara kalıcı olarak yerleşir, oturma yerinde gerçekten oturur, yalnız yol ağında yürür. Yer kalmayınca "Ofis kapasitesi dolu" yazar. Sözleşmeye uymayan model nedenleriyle reddedilir; 0.9.36–0.9.37'de sözleşmesiz içe aktarılan model de artık kullanılmaz ve panel nedenlerini yazar. **Örnek ofisi kullan** hazır bir ofis açar. **3D ofisten yönetim:** bir çalışana tıklayıp görev verir, ajana soru sorar, bekleyen soruyu yanıtlar, onay verir veya insan çalışana görev atarsınız. **Ofisler arası iletişim:** yönettiğiniz ofislerin yöneticileri birbirine görev ve soru gönderir; karşı yönetici işi kendi departmanlarına dağıtır ve sonuç geri döner. [Ajan rehberi](docs/ajanlar.md#telegramdan-soru-ve-onay-0938), [Ofis modeli](docs/ofis-modeli.md).

**0.9.37:** **Birden fazla ofisi yönetmek:** bir yetkili birden fazla departmanı yönetebilir. **Ofisim** sekmesindeki **Yeni ofis kur** ile istediği kadar ofis açar; Ajanlar başlığındaki **Ofis** listesinden ofisler arasında geçer. Ofis değiştirmek yalnız ekranı değiştirir: diğer ofislerin ajan çalışmaları, otomasyonları ve onay beklemeleri kendi ofislerinde sürer. **Ofisim** sekmesinin başında her ofisin ajan, kişi, açık görev ve bekleyen onay sayısı görünür. Yetkili olmayan çalışan tek ofiste kalır. Birden fazla ofis 0.9.37 gerektirir; önceki sürümler ilk ofisi gösterir. [Ajan rehberi](docs/ajanlar.md#birden-fazla-ofisi-yönetmek-0937).

**0.9.36:** **Ofisinizi kendiniz kurun:** RpaOrkestrAI ve Ajanlar lisansı olan, henüz bir ofiste bulunmayan her hesap (bireysel hesaplar dahil) Ajanlar'ı ilk açtığında **Ofisinizi kurun** ekranında ofisine ad verir ve ofisin yetkilisi olur; her hesap tek ofiste bulunur. Yeni **Ofisim** sekmesinde yetkili ofisin adını değiştirir, firmada ofisi olmayan lisanslı çalışma arkadaşlarını ofise ekler veya çıkarır; üye ofisten ayrılıp kendi ofisini kurabilir. **Kendi 3D ofis modeliniz:** Ofis görünümündeki **Ofis modeli** ile bilgisayarınızdaki `.glb` dosyasını (en fazla 100 MB) içe aktarın. Model yalnız o bilgisayarda ve o ofis için saklanır; ölçek, yön, konum, yükseklik ve tavan kesitiyle yerleştirilir, hazır zemin gizlenebilir, **Varsayılan ofise dön** modeli siler. **Şifre kodu:** giriş ekranındaki **Şifre kodum var** kullanıcı adıyla da çalışır; yeni açılan hesabın ilk şifresi de bu kodla belirlenir. [Ofis kurma](docs/ajanlar.md#kendi-ofisinizi-kurmak-0936), [3D ofis modeli](docs/ajanlar.md#kendi-3d-ofis-modeliniz-0938-yerleşim-sözleşmesi).

**0.9.35:** **Bireysel kullanım:** RpaOrkestrAI artık kişilere de satılır. Kişi orkestrai.net/rpa sayfasındaki formdan başvurur ve şifresini kendisi belirler. Ödeme onaylanınca platform yöneticisi orkestrai.net'teki **RpaOrkestrAI bireysel hesaplar** sayfasından hesabı açar: tek kullanıcılı firma ve lisans birlikte açılır, Ajanlar ek modüldür. Yeni başvurular yöneticinin bildirim ziline düşer. Bireysel hesapta Ajanlar tek kişilik ekip olarak çalışır; insan görevleri ve çalışan listesi gizlenir. Lisans panelinde hesap türü ve **Lisansı uzat** bağlantısı görünür. **Şifre:** her hesap Ayarlar'daki lisans panelinden **Şifreyi değiştir** ile şifresini değiştirebilir. Bireysel hesapta unutulan şifre, yöneticinin verdiği tek kullanımlık kodla giriş ekranındaki **Şifre yenileme kodum var** üzerinden yenilenir. Ödemesi beklenen başvuruyla giriş yapılırsa Studio bunu söyler. [Lisans](docs/lisans.md#bireysel-hesaplar-0935).

**0.9.34:** **Departman ofisleri:** firma ajan ekibini departmanlara ayırabilir. Her departmanın kendi ofisi ve ofis yetkilisi olur (ör. «Claim & İade Departmanı», «Lojistik Planlama ve Süreç Geliştirme Departmanı»). Yetkili kendi ofisinde ajan kurar, otomasyon tanımlar, görev verir ve riskli işlemleri onaylar; ofisler birbirinin ajanlarını, görevlerini, onaylarını ve çalışanlarını görmez. Her ofiste ayrı bir yönetici ajan bulunabilir. Ofis adı Ajanlar başlığında, Ekip sekmesinde ve Ofis görünümünde yazar. Ofisler ve yetkilileri orkestrai.net yönetiminde MOD_AJAN atamasıyla tanımlanır; mevcut ajanlar onları kuran kişinin ofisine geçer. Ofisli ajan kayıtları 0.9.33 ve önceki sürümlerde açılmaz. [Ajan rehberi](docs/ajanlar.md#departman-ofisleri-0934).

**0.9.33:** **Ajanlar akışa bağlı kalmadan çalışır:** ajan formundaki **Doğrudan yetenekler** ile ajan seçilen klasörlerdeki belgeleri (PDF, Word, Excel) ve gelen kutusunu okur; e-postayı kendisi yazıp gönderir veya yanıtlar (yalnız göreve gelen adreslere, izinli alan adlarına veya herkese), WhatsApp/Telegram/Teams kanalına mesaj gönderir. Gönderimler onaya gelir ve düzeltilerek onaylanabilir; onaysız gönderimi yalnız onay yetkilisi açar; süreç kartı kuralları geçerlidir. **Ajana soru sorma:** ajan kartındaki **Soru sor** ile «bugün neler yaptın, ne bekliyor, son hatalar» gibi sorular sorulur; ajan görev kayıtlarına, otomasyon sıralarına ve bildiklerine bakarak yanıtlar, iş başlatmaz. **WhatsApp ve Telegram:** Mesaj gönder adımı ve mesajlaşma bağlantısı WhatsApp (Meta WhatsApp Business Cloud API; serbest metin veya onaylı şablon) ve Telegram (bot; Sohbetleri bul) destekler. **Yapay zekâya sor düzeltmeleri:** Gemini 3 modellerinde düşünme ayarı düzeltildi (modelin desteklediği en düşük düzey istenir); yanıt sınırı düşünme sırasında dolarsa adım bir kez daha geniş sınırla sorar; varsayılan yanıt sınırı 4.096 token; hata nedeni (model bulunamadı, kota, sınır, güvenlik filtresi) gösterilir; adım artık zamanlayıcı ve otomasyonla başlayan akışlarda da çalışır. Yeni yetenekleri kullanan ajanlar ve Alıcı/Şablon alanlarını kullanan akışlar 0.9.32 ve önceki sürümlerde açılmaz. [Ajan rehberi](docs/ajanlar.md) · [Kurumsal entegrasyon](docs/kurumsal-entegrasyon.md).

**0.9.32:** **Model sağlayıcısının kendi web araması:** Ajanlar → Bağlantılar → Web araması'na beşinci seçenek eklendi. Gemini, OpenAI veya Claude bağlantısı kullanan ajanlar ek anahtar olmadan, kendi modelinin arama aracıyla internette arar. Arama metni önce uygulamanın denetiminden geçer (kayıtlı şifre, izinli siteler, görev başına 20 istek); sonuçlar izinli sitelere göre süzülür, kullanılan tokenlar ajanın sınırına sayılır. Sağlayıcının arama ücreti model faturanıza eklenir; Gemini'de aylık ücretsiz kota vardır. Ollama ve kurum sunucusu bağlantılarında çalışmaz. Ajan formu, internet açık ama arama hizmeti seçilmemişse uyarır. [Ajan rehberi](docs/ajanlar.md).

**0.9.31:** **Ajana firmanın işleyişini öğretmek:** ajan formunda **Bilgi kaynakları** (fiyat listesi, iade politikası, sık sorulan sorular gibi PDF, Word, Excel, metin belgeleri veya klasörleri) ve **Süreç kartları** (konu, ne zaman, ne yapılır, kullanılacak akışlar ve kural: uygula / her değişikliği onaya sun / insana bırak) tanımlanır. Ajan cevap yazmadan önce belgelerde arar ve kaynağını belirtir; arama bu bilgisayarda, ücretsiz yapılır ve modele yalnız bulunan kısa bölümler gider. Kartı olan ajan uyan kart yoksa değişiklik yapmaz, işi **Sizi bekleyen işler**'e bırakır. **Taslak onayı:** onay ekranında **Düzenleyerek onayla** ile ajanın taslağı (ör. e-posta metni) düzeltilir; tam olarak düzeltilmiş hâl çalışır, ajan düzeltmeden not önerir. Kart başına değişmeden / düzeltilerek onaylanan, reddedilen ve insana bırakılan iş sayısı görünür. **E-posta gönder** adımının yeni **Yanıtlanan e-posta** alanıyla yanıt, alıcının e-posta programında aynı yazışmanın altında görünür. Bilgi kaynağı veya süreç kartı tanımlanmış ajanlar ile yeni alanı kullanan akışlar 0.9.30 ve önceki sürümlerde açılmaz. [Ajan rehberi](docs/ajanlar.md#firmanın-işleyişini-öğretmek-bilgi-kaynakları-süreç-kartları-ve-taslak-onayı-0931) · [Örnek: e-postaları yanıtlayan ajan](docs/kurumsal-entegrasyon.md#örnek-gelen-e-postaları-yanıtlayan-ajan-0931).

**0.9.30:** **Kurumsal entegrasyon:** API'si olan uygulamalarda ekran yerine doğrudan servis veya veritabanı kullanılabilir. Yeni bağlantı türleri: **Web servisi (API)** (Bearer, kullanıcı/şifre, API anahtarı, OAuth 2.0; kimlik bilgileri yalnız o sunucuya gider), **Gelen e-posta (IMAP)**, **FTP / FTPS** ve **Mesajlaşma** (Teams, Slack, Google Chat, Discord). Yeni adımlar: **Veritabanında değişiklik yap** (yalnız bağlantıda izin verilen tablo ve yordamlarda tek komut; WHERE'siz UPDATE/DELETE çalışmaz, değişen satır sınırı aşılırsa geri alınır), **E-postaları oku** (ekleriyle), **FTP dosya aktarımı** ve **Mesaj gönder**; **HTTP isteği gönder** API bağlantısıyla yalnız yol yazılarak kullanılır. **Otomasyonlar:** «Tabloya yeni kayıt geldiğinde» (Google Sheets, veritabanı sorgusu, Excel / CSV) ve «Yeni e-posta geldiğinde» tetikleyicileri; hedef bir ajan veya doğrudan bir akış olabilir (yapay zekâ maliyeti olmadan). Gelen işler sıraya girer, önceki iş sürerken gelen iş kaybolmaz. **Ajanlar internette araştırabilir:** ajan başına Kapalı / Yalnız izinli siteler / Tüm web; arama hizmeti Tavily, Vikipedi, Brave veya SearXNG. Ajan yalnız açık internetteki sayfaları okur, iç ağa ve bu bilgisayara erişemez, görevde en fazla 20 istek yapar. Ajanlar API ve veritabanı adımı içeren izinli akışları da çalıştırabilir. **Canlı ofis:** yönetici görevi departmana yürüyerek götürür, araştıran ajan araştırma köşesine gider. Yeni adımları veya bağlantı alanını kullanan akışlar 0.9.29 ve önceki sürümlerde açılmaz. [Kurumsal entegrasyon rehberi](docs/kurumsal-entegrasyon.md) · [Ajan rehberi](docs/ajanlar.md).

**0.9.29:** **Ajan otomasyonları:** Ajanlar → **Otomasyonlar** sekmesinden ajana belirli zamanlarda (bir kez, her gün, belirli günler, her N dakikada bir), bir akış bittiğinde (başarılı, hatalı veya her sonuçta) ya da bir klasöre yeni dosya geldiğinde kendiliğinden görev verilir. Görev elle verilen görevle aynı izin, onay ve sınırlarla çalışır; önceki görev sürerken yenisi başlamaz, ajanın kendi çalıştırdığı akışlar tetiklemez. **Görev silme:** bitmiş ajan görevleri (alt görevleriyle) ve insan görevleri yetkili tarafından silinebilir; akış kayıtları ve sunucudaki denetim kaydı korunur. **Girdi değişkenleri** artık JSON yerine ad–değer satırlarıyla girilir; ajanın akışlarının beklediği girdiler öneri olarak gösterilir. Model hataları nedeniyle birlikte yazılır (ör. model bulunamadı, API anahtarı geçersiz, kota doldu); ajan bir aracı yanlış alanla çağırırsa hangi alanı düzelteceği kendisine söylenir. Ajan, akış gerektirmeyen genel bilgi sorularını kendi bilgisiyle yanıtlayabilir. [Ajan rehberi](docs/ajanlar.md).

**0.9.28:** **Ajanlar onaylı notlarla öğrenir:** bir soruyu yanıtlarken «Bu bilgiyi ajanın kalıcı notu olarak da sakla» seçilebilir; ajan da görev sırasında kalıcı bilgi önerebilir. Not yalnız ajanları yönetme yetkisi olan kişi onaylarsa kaydedilir ve o ajan sonraki görevlerde kullanır. Ajan kartındaki **Bildikleri** bölümünde notlar görülür, düzenlenir ve silinir. Notlar izin, onay veya sınır değiştirmez; her ajanın notu kendisine aittir. Kayıtlı şifre içeren not reddedilir. Araç tanımları küçültüldü; küçük bağlamlı modellerde konuşmaya daha fazla yer kalır. [Ajan rehberi](docs/ajanlar.md).

**0.9.27:** **Ajanlar yönetici üzerinden haberleşir:** yöneticinin verdiği görevde takılan departman ajanı önce yöneticisine sorar; yönetici yanıtlar ya da bilmiyorsa size sorup yanıtı iletir. Yönetici bir departmanın sonucunu bekleyip başka bir departmana girdi olarak aktarabilir. Departman ajanları birbirleriyle doğrudan konuşmaz. **Canlı ofis:** soru soran ajan yöneticinin odasına yürür; başlarında «Görev», «Soru», «Yanıt», «Sonuç» balonları çıkar (yalnız mesajın türü görünür, içerik görünmez). **Sade yetki kartı:** her ajan kartı ve düzenleme formu, ajanın kayıtlı izinlerinden üretilen **Yapabilir · Onay ister · Yapamaz** özetini ve sınırları dakika cinsinden gösterir. **Daha kolay yönetim:** Başlarken kontrol listesi; her sekmede **Sizi bekleyen işler** uyarısı; Temkinli / Dengeli / Geniş sınır profilleri ve dakika cinsinden süreler; sade cümlelerle zaman çizelgesi, sınır kullanım çubukları ve alt görev bağlantıları; organizasyon şeması ve kurulum kontrolü; ofiste **Son iletişimler** listesi; onay kartında isteyen kişinin adı. Model önerileri güncellendi; Gemini'de seçtiğiniz model adı artık değiştirilmeden kullanılır. Ekran tablosuna yazarken yeni açılmış uygulamanın ilk kopyalama yanıtı için daha uzun beklenir. [Ajan rehberi](docs/ajanlar.md).

**0.9.26:** **Görevler ekranında hem ajana hem insana görev atama:** Görevler sekmesinde «Ajana görev ver» butonuyla yapay zekâ ajanları doğrudan çalıştırılabilir; «İnsan çalışana görev ata» butonu lisanslı kurum personeline görev verir. **Ajan yetenekleri ve sınırları:** Ajanlar sekmesindeki her ajan kartında izinli araçlar (tools), izinli akışlar ve güvenlik sınırları (serbest web araması kısıtı, bilgisayarda rastgele kod çalıştırmama, kurum onayı gereksinimi) açılır detay panelinde gösterilir. Kurum onayları ve görev listesinde oturum süresi dolduğunda bilgilendirme ve donmayı önleme eklendi.

**0.9.6:** Metin okuma adımlarında **Bölge çiz** ile ekran görüntüsü üzerinde dikdörtgen seçebilirsiniz. Pencereye göre bölgeler pencere taşındığında da pencereye bağlı kalır. **Tabloya değer yaz** adımı uygulamanın düzenlenebilir tablo hücreleri sunmasını gerektirir; bu erişimi sunmayan tablolarda işlem anlaşılır bir hatayla durur.

**0.9.7:** Tabloya yazmada **Ekranda seç** ile referans görsel, konum veya alan kimliği kullanılabilir. Ana form satır, sütun ve değerden oluşur; ayrıntılı ayarlar **Diğer seçenekler** altındadır. 0.9.6 ile kaydedilmiş otomatik/adla tablo seçimi korunur. Adım açıklamaları firma ve uygulamadan bağımsız olacak şekilde genelleştirilmiştir.

**0.9.12:** Tablo önizlemesinde **Başlık yap** ile gerçek başlık satırını seçebilirsiniz; başlık yoksa **Başlık yok** seçin. Başlık ve öncesi veri sayılmaz, ilk kayıt **Veri 1 / Satır 1** olur. Başlıktan önce boş satır bulunan kopyalar desteklenir; okuma ve yazma aynı satır ayrımını kullanır. `sutun_7` gibi numaralı sütun adları çalışmaya devam eder.

**0.9.22:** Windows'ta görev çubuğuna sabitleme ve Başlat aramasında uygulama artık **RpaOrkestrAI Studio** adı ve simgesiyle görünür (önceden yalnız `RpaOrkestrAI.exe`). Uygulama ile masaüstü/Başlat kısayolları aynı uygulama kimliğini taşır; EXE'ye ad, sürüm ve yayıncı bilgisi eklendi. Daha önce sabitlenmiş eski öğeyi bir kez kaldırıp uygulama açıkken yeniden sabitleyin.

**0.9.23:** Ajanlar, tek yönetici ve departman ajanları, izinli akış araçları, ayrı ajan lisansı, merkezi kullanıcı onayları, insan görevleri ve performans paneli. **Yapay zekâya sor** adımı şema ile doğrulanmış sonuçları akışa taşır. Aynı oturumdaki ortak model istekleri sıraya girer; onay ve akış izinleri model yanıtıyla değişmez. [Ajan rehberi](docs/ajanlar.md) ve [doğrulama durumu](docs/ajanlar-gelistirme-durumu.md).

**0.9.25:** **Adım numaraları kütüphanede sabittir:** her adım türünün numarası kütüphane listesinde görünür ve akıştaki kutuda, ayar panelinde, Adıma git listesinde ve çalışma günlüğünde aynı numara kullanılır; adım eklemek veya taşımak numarayı değiştirmez.

**0.9.24:** **Tıkla ve tuşa bas** adımı hedefe tıklayıp aynı pencereye tuş gönderir. **Excel hücresine yaz** seçilen sütuna belirli satıra, son dolu satıra veya son dolu satırın altına değer, sayı ya da formül yazar; son satırı hangi sütunun belirleyeceği seçilir. **Excel / CSV'ye yaz → Sonuna ekle** artık başlıktaki sütun yerlerini korur ve biçimlendirilmiş boş satırları saymaz. **Ajanlar** bölümü ve **Yapay zekâya sor** adımı yalnız ayrı ajan lisansı (`MOD_AJAN`) tanımlı hesaplarda görünür; diğer hesaplarda menüden kalkar. Yeni adımları kullanan akışlar 0.9.23 ve öncesinde açılmaz.

**Ortak sunucu LLM hizmeti henüz etkin değildir.** Kurulum dosyalarının yayımlanması ortak modelin çalıştığı anlamına gelmez. Sunucunun CPU özellikleri ve gerçek araç çağrısı süresi doğrulanmalıdır. Ajan kullanımı için firmaya ve hesaba ayrı ajan lisansı atanması gerekir.

Web tıklamasıyla açılan yeni sekmenin ilk yanıtı gecikse de sonraki adım yeni sekmeyi bekler. Süre dolarsa işlem durur; tıklama tekrarlanmaz.

Kayıtlı API anahtarının bağlantı adı veya model alanına yapıştırılması reddedilir. Ajan ve yapay zekâ adımı, çalışma sırasında kaydedilen yeni sırları da dış çağrı ve sonuç denetimlerinde maskeler; kasa doğrulanamazsa işlem durur.

Aynı çalışma alanında paralel ajanlar bağlantı kayıtlarını güvenle paylaşır. **Durdur**, lisans kaybı veya oturum değişikliğinde bağlı akışın kaydı da **İptal edildi** olur; süre ve yetki sınırı ihlalleri hata olarak kalır. Ofisin yerel Three.js dosyaları iki platformda aynı bütünlük denetiminden geçer.

Aynı ajana verilen görevler kuyruğa giriş sırasıyla çalışır; önceki görevin bitiş anı veya bilgisayar saatinin değişmesi sırayı bozmaz. Ortak model yeniden denemeleri bekleme ve toplam süre sınırına uyar. Windows arayüz ve paket sınamaları Türkçe metinleri UTF-8 ile işler.

**0.9.21:** **Adım numaraları** (1, 2, 3.1 …) liste, diyagram, ayar paneli, Adıma git ve çalışma günlüğünde. **Web otomasyonu** genişledi: **Tarayıcıda seç** (öğeye tıklayarak hedef belirleme), çerçeve (iframe) desteği, yeni sekmeye kendiliğinden geçiş ve yeni adımlar — Web'de bekle, tuşa bas, geri/ileri/yenile, sekmeye geç, Web tablosunu oku, Web'den dosya indir, Web'e dosya yükle, sayfa görüntüsü ve **Web'de JavaScript çalıştır**. [Web otomasyonu rehberi](docs/web-otomasyonu.md).

**0.9.20:** Yeni adımlar: **Onay kutusu**, **PDF'ten oku**, **Zip aç / oluştur**, **E-posta gönder**, **Web sayfası aç / Web öğesine tıkla / Web alanını doldur / Web'den metin oku / Web listesinden seç**. **Hata olursa** bloğuna hata anında ekran görüntüsü seçeneği eklendi. Bu adımları veya seçeneği kullanan akışlar 0.9.20 öncesi sürümlerde açılmaz. [Adımlar](docs/adimlar.md).

**0.9.19:** Akış düzenleyicideki ana **Çalıştır** düğmesinin `body.pause_at: Input should be a valid string` hatası verip akışı başlatmaması düzeltildi (0.9.16–0.9.18).

**0.9.18:** **Buraya kadar çalıştır** duraklamasında Studio'nun donup yanıt vermemesi düzeltildi: Windows'ta pencereyi öne alma/üstte tutma işlemi pencerenin kendi iş parçacığında yapılır; duraklama sayfası değişmeyen durumu yeniden çizmez ve uzun değerleri (ör. tüm Sheets satırları) kısaltarak gösterir.

**0.9.17:** Akıştaki adım ve iç içe koşul/döngü sınırı kaldırıldı: bir akış 10.000 adıma ve 50 seviye iç içe bloğa kadar içerebilir (önceden 200 adım ve 8 seviye). Bu sınırları aşan akışlar 0.9.17 öncesi sürümlerde açılmaz.

**0.9.16:** **Buraya kadar çalıştır:** Bir adımı seçip akışı baştan o adımın hemen öncesine kadar çalıştırın; akış durur, o andaki değişkenler görünür. Sonra **Sonraki adım** ile tek tek, **Devam et** ile seçilen adıma yeniden gelinceye (ör. döngünün sonraki turu) kadar veya **Sonuna kadar** ilerleyin. Her adımdan önce Studio küçültülür. **Koşul** testi varsayılan olarak yalnız koşulu kontrol eder: Evet/Değilse dallarındaki adımlar çalışmaz, yalnız koşulun değerleri hazırlanır; sonuç ve karşılaştırılan değerler günlükte görünür. [Ayrıntılar](docs/adimlar.md).

**0.9.15:** Yeni **Metni bul, tıkla ve yaz** adımı: pencerede bir alan çizin; adım yazdığınız metni içeren yazıyı (bir parça yeterli, ör. `İad` → `İade`) her çalışmada OCR ile bulur; yazının ortasına veya **Sütun metni** (başlık) ile **Satır metni**nin kesişimine tıklar ve değeri yazar. Boş tablo hücreleri için de kullanılır. Metin bulunamazsa veya birden fazla yerde görünürse tıklamaz. Bu adımı kullanan akışlar 0.9.15 veya üzeri gerektirir. [Ayrıntılı kullanım](docs/pencere-tanitma.md#metni-bul-tıkla-ve-yaz-0915).

**0.9.14:** Boş hücreye yazmada **Tabloyu seç** noktası geniş tablolarda hedef sütundan uzak bir sütunda olsa da tablo doğru eşleştirilir; “Miktar / Onaylanan Miktar” gibi iç içe başlıklar artık sütun sırasını bozmaz. Hedef sütun başlığı okunamazsa hata, ekranda okunan başlıkları listeler. Uygulama simgesi Studio'daki siyah-sarı işaretle aynı oldu; pencere başlık çubuğu yan menüyle aynı koyu renktedir (Windows 11'de tam renk, Windows 10'da koyu başlık, macOS'ta koyu ve saydam başlık).

**0.9.13:** **Tabloya değer yaz** boş hücreye de yazar. Hücrenin yeri her çalışmada, ekrandaki sütun başlığı ile aynı satırda tabloda tek olan dolu bir hücrenin (ör. kayıt kodu) kesişiminden bulunur; ekran ölçeği veya sütun genişliği değişse de kayıtlı koordinat kullanılmaz. Boş görünmesi gereken yerde metin varsa yazılmaz. Akış dosyası değişmez. [Ayrıntılı kullanım](docs/pencere-tanitma.md#tabloya-değer-yaz-096).

**0.9.11:** **Tabloya değer yaz** sadeleştirildi: **Tabloyu seç**, ardından satır, sütun ve değer. “Diğer seçenekler” ve elle X/Y girişi kaldırıldı. Hücre düzenlemesi otomatik doğrulanır; değişkenin değeri bir kez yazılır ve tablonun tamamı yeniden okunarak kontrol edilir. Uzun değer ekranda kesilse de pano doğrulaması yapılır. Tablo seçiminde başlık ayarı, seçimden sonra ilk veri satırı görünür. [Ayrıntılı kullanım](docs/pencere-tanitma.md#tabloya-değer-yaz-096).

Bu test dağıtımı Apple noter onayı ve Windows yayıncı sertifikası olmadan hazırlanır; ilk kurulumda sistemin veya şirketinizin gerektirdiği onaylar çıkabilir.

Kaynak kodla Windows kurulumu yapanlar için `setup-windows.bat` masaüstüne terminal açmayan **RpaOrkestrAI Studio** kısayolu ekler.

## Başlangıç

Bu bölüm **kaynak koddan geliştirme** içindir; standart 64 bit Python **3.11, 3.12, 3.13 veya 3.14** gerekir. Free-threaded Python dağıtımları destek kapsamı dışındadır. Komutları proje klasöründe çalıştırın.

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
rpa-studio
```

Windows'ta GitHub'dan ilk kurulum:

1. ZIP dosyasını tamamen çıkarın. Örneğin `C:\RpaOrkestrAI` gibi yazabildiğiniz bir klasör kullanın.
2. **Python 3.11–3.14 (standart 64 bit)** kurulu olmalıdır. Kurulum betiği 3.14, 3.13, 3.12 ve 3.11 sırasıyla arar; varsa desteklenen mevcut `.venv` ortamını kullanır.
3. [setup-windows.bat](setup-windows.bat) dosyasını çift tıklayın. Sanal ortamı ve yerel pencere/otomasyon paketlerini kurar; internet gerekir.
4. Kurulum bitince masaüstündeki **RpaOrkestrAI Studio** kısayoluyla terminal açmadan başlatın. Hata ayıklamak için [start.bat](start.bat) kullanılabilir. Yerel pencere bileşeninde sorun varsa [start-browser.bat](start-browser.bat) aynı Studio'yu tarayıcıda açar.

GitHub indirmesi `.venv` içermez; Python ortamı her bilgisayarda yeniden kurulur. macOS ortamını Windows'a kopyalamayın. PowerShell komutları ve hata çözümleri [Windows kurulum rehberindedir](docs/kurulum.md#windows--powershell).

Arayüz varsayılan olarak **http://127.0.0.1:8765** adresinde açılır. Başka bir terminalden çalıştıracaksanız önce proje klasörüne geçip sanal ortamı etkinleştirin.

**0.6.0 ile adım kütüphanesi 63 adıma çıktı.** Kütüphane şu grupları kapsar:
- fare ve klavye: tıkla, sürükle, kaydır, yaz, kısayol, tuşu basılı tut
- pencere: öne getir, büyüt/küçült, taşı, kapat, kapanmasını bekle, alanın değerini oku
- ekran: görsel ara/tıkla, kurulum gerektirmeyen OCR ile metin oku/bekle, piksel rengi, ekran görüntüsü
- uygulama ve sistem: uygulama/dosya/adres aç (çift tıklama gibi), komut / script çalıştır (terminal veya PowerShell gibi), uygulamayı kapat, pano
- veritabanı: SQL Server, PostgreSQL, MySQL, Oracle ve SQLite'ta salt okunur SQL sorgusu
- dosya ve Excel: .xlsx/CSV oku-yaz, dosya listele, kopyala/taşı/sil, indirmeyi bekle
- veri: hesapla, metin, tarih, liste
- akış: tekrarla, döngüden çık, hata olursa, başka akışı çalıştır, akışı bitir
- etkileşim ve web: mesaj ve girdi kutusu, HTTP/API

**0.7.1 ile akış iki görünümde düzenlenir.** **Liste** görünümü alt alta kartlardır. **Diyagram** görünümü aynı adımları n8n'deki gibi soldan sağa düğümler ve bağlantı çizgileriyle gösterir: koşul ve hata dalları ayrı satırlarda, döngüler "Sonraki tur" dönüş çizgisiyle çizilir. Çizgilerdeki **+** düğmesiyle araya adım eklenir, düğümler sürüklenerek taşınır. Bir kutunun sağındaki noktayı başka bir kutuya sürükleyince akış oradan devam eder (**Adıma git**). Gerideki bir adıma dönmek için adımları kopyalamak gerekmez. Çizgideki **×** bağlantıyı kaldırır ve o yol orada biter; biten dal diğer dalla birleşmez. Son çalışmada her adımın kaç kez çalıştığı ✓ ve hata verdiği ✗ olarak düğümün üzerinde görünür; çalışma ayrıntısındaki **Diyagramda göster** hatalı adımı seçili açar. Çalışma mantığı iki görünümde de aynıdır.

**Görünüm.** Arayüz teknik çizim görünümündedir: kareli kâğıt zemin, mürekkep çizgili kutular ve tek bir vurgu rengi. Sağ üstteki ay/güneş düğmesi **açık** (çizim kâğıdı) ve **koyu** (blueprint) tema arasında geçer; **Ayarlar → Görünüm** altında bilgisayarın ayarını izleyen **Sistem** seçeneği de vardır. Diyagramda kutuları sürükleyerek istediğiniz yere taşıyabilirsiniz; bir **+** üzerine bırakılan kutu akışta o noktaya geçer.

**Bağlantılar adımın içindedir.** Google Sheets, veritabanı, e-posta, FTP ve mesaj adımlarının ilk alanı **Bağlantı**'dır; **HTTP isteği gönder** isteğe bağlı olarak bir API bağlantısı kullanır. Bağlantı orada oluşturulur, seçilir ve düzenlenir; aynı türde birden fazla adlandırılmış bağlantı olabilir (ör. "Satış tablosu", "İade tablosu"). Bağlantı seçilmeyen adım, o türün varsayılan bağlantısını kullanır. Editördeki **Bağlantılar** düğmesi tüm bağlantıları listeler. Şifre, anahtar ve dosya yolları yalnız o bilgisayarda saklanır; dışa aktarılan akışta yalnız bağlantının kimliği bulunur. 0.6'daki genel Sheets ve veritabanı ayarları ilk açılışta otomatik olarak varsayılan bağlantılara dönüştürülür.

**Adlar.** Bir adımın sonucuna verdiğiniz ad alanına yalnız ad yazılır (ör. `erp_window`); `${erp_window}` yazılırsa uygulama düzeltir. Pencere adımlarında pencere, önceki **Pencereyi tanı** adımlarında verilen adlardan oluşan listeden seçilir. Geçersiz bir ad, hangi adımda ve hangi alanda olduğu belirtilerek bildirilir.

**Hareketleri kaydet**, bir işi fare ve klavyeyle bir kez yapmanızı adımlara çevirir; kayıt F9 ile biter. Adımlar tutup sürüklenerek yer değiştirir ve döngü, koşul veya hata bloklarının içine bırakılabilir. **Bu adımı test et**, seçili adımı tek başına çalıştırır; pencereyi, sabit değerleri ve tablodaki ilk satırı önceki adımlardan kendisi alır, sizden değer istemez. Tıklama ve alan doldurma adımlarında **Yeri göster**, tıklamadan fareyi hedefe götürür. Her adımın ayarlarında kısa bir **Nasıl kullanılır?** kutusu ve her alanın altında açıklaması bulunur. **Çalıştır** adımları gerçekten uygular; **Önizleme (ekranı kullanmadan)** seçeneği ekran, dosya ve bağlantı adımlarını atlar. Tüm adımlar, AutoHotkey karşılıkları ve örnekler [adım rehberindedir](docs/adimlar.md). İlk denemeler için [examples/adim-turu.json](examples/adim-turu.json) ve [examples/metin-editoru.json](examples/metin-editoru.json) akışlarını içe aktarabilirsiniz.

Sheets adımları, Google Cloud veya JSON dosyası gerektirmeyen **Apps Script** bağlantısıyla ya da Google servis hesabıyla çalışır; [Google Sheets bağlantı rehberi](docs/google-sheets.md). **Sheets satırlarını oku** ile B sütununa `form_id`, C sütununa `status` adı verin; döngüde `${row.form_id}` ve `${row.status}` kullanın. Durumu **boş veya Bekliyor** olanları koşulla seçebilir, her dalın içine işlem veya başka bir döngü ekleyebilirsiniz. **Koşul sürdükçe tekrarla**, tekrar ve süre sınırlarıyla çalışır. [Sheets satır ve koşul rehberi](docs/sheets-satir-dongusu.md).

**Alanı doldur → Ekranda seç**, 3/5/10 saniyelik geri sayım sonunda fare konumunu alır. Uygulama alana bir kimlik veriyorsa (Windows UI Automation, macOS Erişilebilirlik) **Alan kimliği** önerilir: alan, pencere boyutu veya ekran ölçeği değişse de kimliğiyle bulunur. Kimlik vermeyen uygulamalarda konum veya görsel yöntem kullanılır; görsel yöntemde ekranın alınmış görüntüsü üzerinde fareyle alan kırpıp hedef noktayı seçersiniz. Önizlemeyi kontrol ederek **Hedefi kaydet** ile onaylayın; **Esc** seçimden vazgeçirir. **Görüntü üzerinde seç** aynı seçimi Studio içindeki görüntüde yapar ve tarayıcıdan kullanımda da çalışır. Her iki yöntemde ERP penceresi **ana ekranda ve tamamen görünür** olmalıdır. macOS ekran kaydı ve erişilebilirlik izinleri, Windows pencere odağı ve yetkileri [pencere tanıtma rehberinde](docs/pencere-tanitma.md) açıklanır.

İlk açılışta örnek akış oluşturulmaz. Mevcut akışlar düzenlenebilir ve çalıştırılabilir; eski **Sheets sütununu oku** / `${row.value}` ve odaktaki alana yazma adımları korunur. Kütüphaneye eklenen adımları yıldızlayarak en üstteki **Sık kullanılanlar** bölümüne taşıyabilirsiniz; favoriler uygulama yeniden açıldığında korunur. Gerçek otomasyon bağlantıları olmadan terminal demosu da çalışır:

```bash
rpa-studio demo
```

Studio zaten açıksa demo için ayrı bir veri klasörü kullanın:

```bash
rpa-studio demo --data-dir ./data/demo-check
```

Aynı veri klasörü eşzamanlı olarak yalnız bir Studio veya demo süreci tarafından açılabilir.

Tam kurulum, işletim sistemi izinleri ve bağlantılar için [kurulum rehberini](docs/kurulum.md) izleyin.

## Uygulamada neler yapılır?

| Alan | İşlev |
| --- | --- |
| Akış tasarımı | Adım ekleme, sıralama, düzenleme; iç içe koşul ve döngüler; her adımda **Sonraki adıma geçmeden bekle** süresi |
| Notlar | Akışın bir bölümünü seçip başlıklı, renkli not ekleme; diyagramda çerçeve, listede bant olarak görünür |
| Zamanlayıcı | Akışı bir kez, her gün, haftanın belirli günlerinde veya belirli aralıklarla çalıştırma; başlamadan önce iptal edilebilir geri sayım; çakışan akışlar için öncelik, gecikme ve süre sınırı, çakışma uyarısı ve 24 saatlik plan |
| Akış yönetimi | Kaydetme, açma, JSON içe/dışa aktarma ve departman bilgisi |
| Çalıştırma | Arka planda çalışma, adım günlükleri, geçmiş ve iptal isteği |
| Raporlar | Akış verisinden CSV üretme ve indirme |
| Veritabanı | **Veritabanı sorgusu** ile SQL Server, PostgreSQL, MySQL / MariaDB, Oracle veya SQLite'ta tek bir `SELECT` sorgusu çalıştırma; `${değişken}` değerleri parametre olarak gönderilir, sonuç **Her satır için** döngüsüne verilir; bu adım yalnız okur. **Veritabanında değişiklik yap** (0.9.30+) bağlantıda izin verilen tablo veya yordamlarda tek bir `INSERT`, `UPDATE ... WHERE`, `DELETE ... WHERE`, `MERGE` ya da saklı yordam çağrısı çalıştırır; değişen satır sınırı aşılırsa değişiklik geri alınır. Bağlantı sunucu, kullanıcı ve şifreyle formdan kurulur. [Adım rehberi](docs/adimlar.md#veritabanı) |
| Kayıtlı şifreler | ERP girişi gibi işler için şifreyi işletim sisteminin kasasında (Windows Kimlik Bilgisi Yöneticisi, macOS Anahtar Zinciri) tutma; adımda `${sifre.ad}` ile kullanma, günlükte gizleme |
| Script ve programlar | **Uygulama, dosya veya adres aç** programı, belgeyi veya klasörü çift tıklar gibi açar. Windows'ta programları başlatmak için masaüstü kısayolunu (`.lnk`) seçin; kısayolun parametreleri ve çalışma klasörü korunur. **Komut / script çalıştır** terminal (cmd / Terminal) veya PowerShell komutunu ya da seçilen `.py`, `.ps1`, `.bat`, `.vbs`, `.sh` script'ini çalıştırır, bitmesini bekler ve çıktısını akışta kullanır |
| Masaüstü | Geri sayımla fare konumu alma, alanı uygulama yapısındaki kimliğiyle bulma, fareyle görsel alanı seçme; hedefe tıklama, alan doldurma ve platforma uygun kısayollar |
| Yeni (0.9.20) | **Onay kutusu** (alan kimliği veya işaretli/işaretsiz görüntüyle), **PDF'ten oku** (metin, tablo, taranmış sayfalar için OCR), **Zip aç / oluştur**, **E-posta gönder** (SMTP bağlantısı), **Web sayfası** adımları (Edge/Chrome ile aç, tıkla, doldur, oku, listeden seç) ve **Hata olursa** bloğunda hata anında ekran görüntüsü |
| Ekrandaki metinle yazma | **Metni bul, tıkla ve yaz** ile çizilen alanda OCR ile metni bulup üzerine ya da sütun başlığı ile satır değerinin kesişimine (boş hücre dahil) tıklama ve değer yazma; koordinat kaydedilmez (0.9.15+) |
| Uygulama tabloları | **Tablodan değer oku** ile uygulama tablosundaki hücreyi sütun adıyla okuma ve satır sayma; **Tabloya değer yaz** ile erişilebilir tablo hücresini satır/sütun veya benzersiz kayıt değeriyle bulup yazma ve doğrulama (0.9.6+) |
| Görsel algılama | OpenCV şablon eşleştirme, OCR metni ve koşullu kararlar |
| Google Sheets | Adlandırılmış sütunlarla satır okuma, boş durumları koruma; hücre okuma/yazma ve servis katmanında satır ekleme |
| Web | **HTTP isteği gönder** ile web servisleri (API); API bağlantısıyla kimlik bilgisi adımda yazılmaz, adres yalnız yol olarak girilir (0.9.30+). Eski akışlardaki tarayıcı (Playwright) adımları çalışmaya devam eder |
| E-posta, FTP, mesaj (0.9.30) | **E-postaları oku** (IMAP; gönderen/konu süzgeci, ekleri klasöre kaydetme), **FTP dosya aktarımı** (FTP / FTPS indirme, yükleme, listeleme), **Mesaj gönder** (Teams, Slack, Google Chat, Discord) |
| Otomasyonlar | Ajanlar → **Otomasyonlar**: belirli zamanlarda, bir akış bittiğinde, klasöre dosya, tabloya kayıt (Sheets, veritabanı, Excel / CSV) veya posta kutusuna e-posta geldiğinde bir ajana görev verme ya da akışı doğrudan çalıştırma. [Kurumsal entegrasyon](docs/kurumsal-entegrasyon.md) |

Bu sürüm her bilgisayarda orkestrai.net hesabıyla açılır; akışlar ve ayarlar o bilgisayarın çalışma alanında kalır. Departman alanı raporları ve akışları sınıflandırır; akış bazında erişim yetkisi oluşturmaz. Zamanlayıcı bu bilgisayarda, Studio açıkken çalışır; Studio isterseniz bilgisayar açılınca simge durumunda başlar ([zamanlayıcı rehberi](docs/zamanlayici.md)). Merkezi çok kullanıcılı sunucu ve uzak robot yönetimi bu sürümün kapsamı dışındadır.

## İlk gerçek otomasyon

Masaüstü ERP için [pencere tanıtma rehberiyle](docs/pencere-tanitma.md) başlayın. Daha kapsamlı işlemler için aşağıdaki sırayı izleyin. Tabloda ve rehberlerde anlatılan mevcut motor işlemleri, eski veya içe aktarılan akışlarda desteklenmeye devam eder.

1. [Kurulum rehberindeki](docs/kurulum.md) otomasyon paketlerini ve gerekli sistem araçlarını kurun.
2. Sheets adımını ekleyip **Bağlantı** alanından bağlantı oluşturun.
3. Yeni akışa ad ve departman girin. Adım kitaplığından veri okuma adımını ve ardından bir döngü ekleyin.
4. Çıktı değişkenlerini sonraki adımlara `${orders}` veya `${item.MATERIAL}` biçiminde bağlayın.
5. ERP tıklama, alan doldurma ve arama adımlarını döngünün içine yerleştirin. OCR sonucuna göre koşul ekleyin.
6. Önizleme ile adım yapısını inceleyin; ardından hedef uygulama hazırken gerçek çalıştırmayı başlatın.
7. CSV raporu ekleyip çalışma çıktısını ilgili departmanla paylaşın.

Masaüstü Studio, gerçek akış ve adım testleri başlamadan önce otomatik küçülerek ekranı hedef uygulamaya bırakır. Zamanlanmış akışlarda da aynı davranış geçerlidir; ilk adım küçülme tamamlandıktan sonra çalışır. Önizlemede Studio açık kalır. Sonucu görmek veya çalışmayı durdurmak için görev çubuğundan / Dock'tan Studio'yu açabilirsiniz; çalışma sonunda pencere kendiliğinden öne gelmez. Tarayıcı sürümünde pencereyi elle küçültün.

Akış geliştirme, değişkenler ve önizleme ayrıntıları [kullanım rehberindedir](docs/akislar.md).

**Önizleme gerçek bağlantıları doğrulamaz.** Veritabanı, ekran, web ve Sheets gibi dış adımlar atlanır ve günlükte belirtilir. Yerel veri ve kontrol adımları değerlendirilir. Atlanan dış adıma bağlı veri bilinmiyorsa ona bağlı döngü/koşul da değerlendirilmez; hayali ERP sonucu üretilmez.

## Otomasyon ve yerel pencere

Gerçek dış bağlantılar için:

```bash
python -m pip install -e ".[automation,dev]"
python -m playwright install chromium
rpa-studio doctor
```

Tesseract ve SQL Server ODBC sürücüsü işletim sistemine ayrıca kurulur. macOS ekran/erişilebilirlik izinleri de masaüstü işlemleri için gereklidir. [Platform kurulum adımları](docs/kurulum.md).

İsteğe bağlı yerel pencere:

```bash
python -m pip install -e ".[native]"
rpa-studio --native
```

Bu kurulumdan sonra macOS'ta [start.command](start.command), Windows'ta [start.bat](start.bat) dosyasını çift tıklayarak yerel pencereyi açabilirsiniz. Başlatıcılar varsayılan olarak proje içindeki `.venv` sanal ortamını kullanır. Windows ilk kurulumunu `setup-windows.bat` yapar; `start.bat` ve `start-browser.bat` paket indirmez.

**macOS'ta Masaüstü/Belgeler iCloud ile eşitleniyorsa:** önce [setup-macos.command](setup-macos.command) dosyasını çalıştırın (`uv` veya proje içindeki `.bootstrap/bin/uv` gereklidir). Bu kurulum Python ve paketleri `~/Library/Application Support/RpaOrkestrAI/` içine yerleştirir. Ardından `start.command` bu yerel ortamı tercih eder ve güncel kaynak kodunu oraya eşitler; Python bileşenleri her açılışta buluttan beklenmez. Akışlar ve ayarlar projenin mevcut veri dizininde kalır.

Başlatıcı açılış durumunu Terminal'de gösterir. Aynı sürüm ve çalışma alanı zaten açıksa masaüstü penceresi o sunucuya bağlanır; ikinci sunucu başlatmaz. Sunucu kapalıysa kendisi başlatır. Önceden açık bir sunucuya bağlanan pencerenin kapanması o sunucuyu durdurmaz. Başlatıcı kendi sunucusunu açtıysa pencere kapatılırken onu da kapatır. Eski bir sürüm açıkken güncelleme yaptıysanız önce eski uygulamayı kapatın.

Başlatıcılar bu klasördeki güncel kaynak kodunu kullanır; her kod değişikliğinde paketi yeniden kurmanız gerekmez. Bağımlılıklar değişirse kurulum adımını tekrar çalıştırın. Açılış başarısız olursa Terminal hata mesajını gösterir ve Enter tuşuna basılana kadar açık kalır.

Tarayıcıyı otomatik açmadan çalıştırmak için `rpa-studio --no-browser` kullanın. CLI seçeneklerini `rpa-studio --help` ile görebilirsiniz.

## Yapılandırma ve saklama

| Ortam değişkeni | Varsayılan / amaç |
| --- | --- |
| `RPA_DATA_DIR` | `./data`; akışlar, çalışmalar, raporlar ve yerel ayarlar |
| `RPA_PORT` | `8765`; Studio portu |
| `RPA_DATABASE_URL` | Boş; SQLAlchemy veritabanı bağlantı adresi |
| `RPA_ALLOWED_TABLES` | `public.IASSALITEM,public.IASINVITEM`; virgülle ayrılan tam tablo adları |
| `RPA_MAX_ROWS` | `10000`; veritabanı satır üst sınırı |
| `RPA_GOOGLE_CREDENTIALS_PATH` | Boş; servis hesabı JSON dosyasının yolu |
| `RPA_TEMPLATE_DIR` | `./assets/templates`; eşleştirme şablonlarının kökü |
| `RPA_TESSERACT_CMD` | Boş; Tesseract PATH dışında ise program yolu |
| `RPA_OCR_LANGUAGE` | `tur+eng`; yüklü OCR dilleri |
| `RPA_ACTION_TIMEOUT` | `30`; adaptör beklemelerinde kullanılan saniye değeri |

Zaman aşımı tarayıcı, veritabanı, ekran bekleme ve OCR işlemlerine aktarılır. Sheets için istek başına üst sınır 120 saniyedir. Tek bir adım birden fazla istek, yeniden deneme veya dropdown sayfası içerebilir; bu değer tüm akışın toplam süre sınırı değildir.

Adlandırılmış bağlantılar `data/connections.json`, uygulama ayarları `data/settings.json`, zamanlamalar `data/schedules.json` içindedir. `RPA_DATABASE_URL` ve `RPA_GOOGLE_CREDENTIALS_PATH` gibi `.env` değerleri yalnız ilk açılışta varsayılan bağlantıya dönüştürülür; sonrasında bağlantıyı adımın **Bağlantı** alanından veya **Bağlantılar** penceresinden düzenleyin. `data/` ile `.env` Git'e eklenmez. Yerel ayar dosyası bir şifre kasası değildir; bilgisayar hesabı ve dosya erişimleri bu bilgileri korur.

Akış dışa aktarımı bağlantı bilgilerini içermez; adımda yalnız bağlantının kimliği kalır. Akışı başka bir bilgisayara aktardığınızda adım "bağlantı bu bilgisayarda yok" uyarısı gösterir; orada bağlantıyı seçin veya oluşturun. Adımların kullandığı referans görseller dışa aktarılan dosyaya eklenir ve içe aktarırken şablon klasörüne yazılır; aynı adla farklı bir görsel varsa üzerine yazılmaz, yeni görsel ek bir numarayla kaydedilir. Akış dosyası en fazla 16 MB olabilir. Not veya **Sonraki adıma geçmeden bekle** süresi içeren akış dosyaları 0.8.6 ve önceki sürümlerde içe aktarılamaz. Ancak adımlara sizin yazdığınız sabit metinler, değişkenler ve iş verileri JSON içinde yer alabilir. Çalışma günlükleri ve CSV dosyaları da iş verisi içerebilir; paylaşılacak çıktıyı inceleyin.

## Geliştirme ve doğrulama

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

GitHub Actions her push'ta macOS ve Windows üzerinde paketlenen Python 3.12 için; **Actions → Python checks → Run workflow** ile elle başlatıldığında Python 3.11, 3.12, 3.13 ve 3.14 için tam `native`/`automation` bağımlılıklarını kurar, paket tutarlılığını ve yerel pencere motorunun yüklenmesini doğrular, testleri çalıştırır. Bu testler canlı ERP oturumu, veritabanı hesabı veya Google anahtarı gerektirmez. Gerçek masaüstü, OCR, sürücü ve ağ bağlantıları hedef bilgisayarda ayrıca doğrulanmalıdır; CI bunların yerini tutmaz.

Uygulama localhost üzerinde kullanılır; bu sürümü port yönlendirmeyle internete veya ortak ağa açmayın. Masaüstü robotu çalışırken hedef pencere odağı ve ekran düzeni korunmalıdır. İptal isteği bir sonraki denetim noktasında uygulanır; tamamlanmış dış işlemleri geri almaz.

## Rehberler

- [Ajanlar ve dijital ekip](docs/ajanlar.md): geliştirme aşamaları, ayrı ajan lisansı,
  izinli akışlar, merkezi onay, insan görevleri, performans, yerel ofis önizlemesi
  ve sağlayıcı bağlantıları. Güncel Windows/macOS paketi 0.9.44. Ortak
  sunucu modelinin performans doğrulaması ve etkinleştirilmesi ayrıca bekliyor.

- [Kurumsal entegrasyon: ekran mı, API mi, veritabanı mı; bağlantılar ve otomasyonlar](docs/kurumsal-entegrasyon.md)
- [Adım rehberi: 92 adım, test etme, sürükle-bırak, AutoHotkey karşılıkları](docs/adimlar.md)
- [Google Sheets bağlantısı: Apps Script veya servis hesabı](docs/google-sheets.md)
- [Kullanıcı girişi, lisans, tek bilgisayar kuralı ve internet gereksinimi](docs/lisans.md)
- [Terminalsiz masaüstü uygulaması ve kurulum paketi](docs/masaustu-dagitim.md)
- [Otomatik güncelleme ve yeni sürüm yayımlama](docs/guncelleme-mimarisi.md)
- [Kurulum, macOS/Windows izinleri ve bağlantılar](docs/kurulum.md)
- [ERP penceresini tanıtma, alan kimliği ve Sheets hücresini kullanma](docs/pencere-tanitma.md)
- [Sheets satırları, boş/Bekliyor koşulu ve iç içe döngüler](docs/sheets-satir-dongusu.md)
- [Akış oluşturma, değişkenler ve raporlar](docs/akislar.md)
- [Zamanlayıcı: akışı belirli zamanlarda çalıştırma, bilgisayar açılınca başlatma](docs/zamanlayici.md)
- [Veritabanı hesabı: salt okunur ve kayıt değiştirme yetkisi](docs/veritabani.md)
- [Mimari ve genişletme](docs/mimari.md)
- [GitHub remote ve push](docs/github.md)
