# Kurumsal entegrasyon: ekran, API ve veritabanı

RpaOrkestrAI bir işi üç yoldan yapabilir: ekranda bir kişi gibi tıklayıp yazarak, uygulamanın API'si üzerinden veya doğrudan veritabanında. Bu sayfa hangi yolun ne zaman seçileceğini, bağlantıların nasıl kurulacağını ve işlerin nasıl kendiliğinden başlatılacağını anlatır (0.9.30+).

## Dört katman

| Katman | Görevi | Nerede |
| --- | --- | --- |
| **Bağlantılar** | Nereye ve nasıl bağlanılacağı: veritabanı, Google Sheets, e-posta gönderme (SMTP) ve okuma (IMAP), web servisi (API), FTP, Teams / Slack. Şifre ve anahtarlar yalnız bu bilgisayarda saklanır, günlükte gizlenir, dışa aktarılan akışlara eklenmez. | Ayarlar → Bağlantılar veya adımdaki Bağlantı alanı |
| **Akışlar** | Ne yapılacağı: adım adım, her seferinde aynı biçimde. API veya SQL adımı ile ekran adımları aynı akışta kullanılabilir. | Akışlarım |
| **Ajanlar** | Hangi akışın hangi bilgiyle çalışacağına karar vermek; belirsizlikte sormak, gerekirse internette araştırmak. Ajan SQL'e veya API'ye doğrudan dokunmaz, izinli akışı çağırır. | Ajanlar |
| **Otomasyonlar** | Ne zaman başlanacağı: belirli zamanlar, bir akışın bitişi, klasöre dosya, tabloya kayıt, posta kutusuna e-posta. Hedef bir ajan veya doğrudan bir akıştır. | Ajanlar → Otomasyonlar; yalnız zamanlı akışlar için Zamanlayıcı |

Bu ayrımın nedeni: akış test edilebilir, sürümlenir ve risk sınıfına göre onaya bağlanır. Ajan yalnız izin verdiğiniz akışları çalıştırabildiği için, bir API veya veritabanı işlemini ajana açmanın tek yolu onu bir akışa koymak ve akışa izin vermektir.

## Hangi yol?

| Durum | Önerilen yol |
| --- | --- |
| Uygulamanın belgelenmiş bir API'si var (REST / JSON, SOAP) | **HTTP isteği gönder (API)** + API bağlantısı. En hızlı ve en sağlam yol; pencere değişikliklerinden etkilenmez. |
| ERP üreticisi saklı yordam (stored procedure) veya aktarım tablosu sunuyor | **Veritabanında değişiklik yap** ile `EXEC dbo.yordam …`. İş kuralları yordamın içinde kalır. |
| Raporlama, kontrol, eşleştirme için veri gerekiyor | **Veritabanı sorgusu** (yalnız okur). |
| Ne API ne yordam var; iş yalnız ekrandan yapılabiliyor | **Pencere** adımları (Pencereyi tanı, Alanı doldur, Tabloya değer yaz …). Hedef bulunamazsa adım tahminle tıklamaz, durur. |
| Web tabanlı bir uygulama | **Web sayfası** adımları; API'si varsa önce API. |
| Gelen işi haber vermek | **Mesaj gönder (Teams, Slack…)** veya **E-posta gönder**. |

ERP tablolarına doğrudan yazmak, ERP'nin stok, muhasebe ve onay kurallarını atlayabilir. Tabloya doğrudan yazmadan önce ERP sorumlusuyla konuşun; mümkünse API veya yordam kullanın ve önce test veritabanında deneyin.

## Bağlantılar

### Web servisi (API)

- **Ana adres:** Tüm isteklerin başladığı adres (ör. `https://erp.firma.com/api`). Adımlarda yalnız yol yazılır: `/v1/siparisler/${row.no}`.
- **Kimlik doğrulama:** Bearer token; kullanıcı adı ve şifre (Basic); API anahtarı (başlıkta veya adres parametresinde, adı servisin belgesindeki gibi); OAuth 2.0 istemci bilgileri (token adresi, istemci kimliği ve sırrı, isteğe bağlı kapsam). OAuth token'ı bellekte tutulur ve süresi dolmadan yenilenir.
- **Varsayılan başlıklar:** Her istekte gönderilen düz başlıklar (ör. `{"Accept": "application/json"}`). Authorization, Cookie ve API anahtarı başlıkları buraya yazılamaz; kimlik doğrulama alanlarını kullanın.
- Kimlik bilgileri yalnız ana adresin sunucusuna gönderilir. Adımda başka bir sunucunun tam adresi yazılırsa istek gönderilmez. Ana adresin sunucusu değiştirilirse kayıtlı token ve şifreler yeniden girilmelidir.
- **Bağlantıyı test et** ana adrese veya **Test adresi** yoluna GET isteği gönderir.

### Gelen e-posta (IMAP)

Sunucu, şifreleme (SSL/TLS 993, STARTTLS 143), kullanıcı, şifre ve klasör (genellikle `INBOX`). Gmail'de uygulama şifresi gerekir. Microsoft 365'te IMAP ile kullanıcı adı / şifre girişi kurum yöneticisinin iznine bağlıdır. Test yalnız bağlanır ve okunmamış iletileri sayar.

### FTP / FTPS

Sunucu, güvenlik (açık TLS ile FTPS önerilir), port, kullanıcı, şifre, pasif mod ve başlangıç klasörü. Adımlar başlangıç klasörünün dışına çıkamaz. SFTP (SSH) farklı bir protokoldür ve desteklenmez.

### Mesajlaşma (Teams, Slack, Google Chat, Discord)

Kanalın webhook adresi parola gibi saklanır. Teams'te kanalın **İş Akışları** bölümünden «Webhook isteği alındığında kanala gönder» şablonu kullanılır; mesaj Adaptive Card olarak gider. Test kanala gerçek bir deneme mesajı gönderir.

### Veritabanı: yazma izni

Veritabanı bağlantısında **Kayıt değiştirmeye izin ver** işaretlenmeden ve değiştirilebilecek tablo / yordam adları yazılmadan **Veritabanında değişiklik yap** çalışmaz. Kurallar [adım rehberindedir](adimlar.md#veritabanı), kullanıcı yetkileri [veritabanı rehberindedir](veritabani.md#kayıt-değiştirme-yetkisi-veritabanında-değişiklik-yap).

## Ajanlar ve entegrasyon adımları

0.9.30 ile ajanlar API ve veritabanı adımı içeren akışları da çalıştırabilir:

- **HTTP isteği** ajan akışında bir API bağlantısı kullanmalı ve adres bağlantıya göre bir yol olmalıdır. Çalışma sırasında adres başka bir sunucuya çözülürse adım durur.
- **Veritabanı sorgusu** ve **Veritabanında değişiklik yap** akışta sabit seçilmiş bağlantıyla çalışır; ajanın verdiği değerler her zaman parametredir, SQL metnine eklenmez.
- **E-postaları oku** yalnız okurken okuma sınıfındadır; okundu işaretleyen veya ek kaydeden adım değişiklik sınıfına girer. Eklerin kaydedileceği klasör ajanın izinli klasörlerinde olmalıdır.
- **FTP dosya aktarımı**nda yerel dosya ajanın izinli klasörlerinde olmalıdır; listeleme okuma, indirme ve yükleme değişiklik sınıfındadır.
- Bağlantı ajan akışında değişkenden gelemez. Değişiklik sınıfındaki akışlar, onaysız çalışma izni verilmedikçe kurum onayı ister.

## Otomasyonlar: işi kendiliğinden başlatmak

**Ajanlar → Otomasyonlar**'da her otomasyonun bir hedefi ve bir tetikleyicisi vardır:

- **Hedef:** *Ajana görev ver* (karar gerektiren işler: belge incelemek, sınıflandırmak, kime gideceğine karar vermek) veya *Akışı doğrudan çalıştır* (her seferinde aynı adımlar; yapay zekâ kullanmaz, maliyet doğurmaz).
- **Tabloya yeni kayıt geldiğinde:** Google Sheets sayfası (ilk satır başlıktır), veritabanı `SELECT` sorgusu veya Excel / CSV dosyası belirli aralıklarla okunur. **Her kaydı ayıran sütun** (ör. Fatura No) daha önce görülmemiş bir değer taşıyan satır yeni kayıttır. İsteğe bağlı süzgeç (ör. Durum = Bekliyor) yalnız eşleşen satırları alır. Otomasyon kaydedildiğinde tabloda olan kayıtlar, **Kayıt anında tabloda olan kayıtları da işle** seçilmedikçe işlenmez. Kayıt `${kayit}` olarak gelir; Türkçe harfli veya boşluklu sütun adları değişkende sade yazılır: «Müşteri Adı» → `${kayit.Musteri_Adi}`, «Fatura No» → `${kayit.Fatura_No}`. Anahtar değeri `${kayit_anahtari}` içindedir.
- **Yeni e-posta geldiğinde:** IMAP klasörü belirli aralıklarla denetlenir; gönderen ve konu süzgeçleri vardır. Otomasyon kaydedildiğinde kutuda olan iletiler işlenmez. İleti `${eposta}` olarak gelir (`subject`, `from`, `text`, `attachments`); ekler istenirse bir klasöre kaydedilir ve yolları `${eposta.attachments}` içinde yer alır. İleti okundu yapılmaz.
- **Klasöre yeni dosya geldiğinde, Bir akış bittiğinde, Belirli zamanlarda:** [Ajan rehberi](ajanlar.md#otomasyonlar-0929-0930).

Gelen işler sıraya girer (en fazla 200) ve önceki iş bitince sıradaki başlar; hiçbiri sessizce atlanmaz. Bir otomasyon saatte en fazla 30 ajan görevi veya 120 akış başlatır. Akış hedefinde masaüstü meşgulse 30 dakikaya kadar beklenir. Otomasyonun başlattığı akışlar başka bir otomasyonu tetiklemez; bir akış kendi bitişiyle yeniden başlatılamaz. Otomasyonlar yalnız Studio açık ve oturum geçerliyken çalışır.

## Örnek kurgular

1. **E-postayla gelen faturalar:** *Yeni e-posta geldiğinde* (konu: Fatura, ekleri `C:\Gelen faturalar` klasörüne kaydet) → hedef: *Fatura İşleme ajanı*. Ajanın izinli akışları: «PDF faturayı oku» (PDF'ten oku), «ERP'ye fatura kaydet» (API veya saklı yordam; onay ister). Ajan uygun olmayan faturayı Teams'e bildirir.
2. **Sheets'e düşen sipariş:** *Tabloya yeni kayıt geldiğinde* (Google Sheets «Siparişler», anahtar: Sipariş No, Durum = Yeni) → hedef: *Sipariş akışı* (doğrudan). Akış `${kayit.Siparis_No}` ile ERP API'sine siparişi yazar, sonra Sheets hücresine «İşlendi» yazar.
3. **Gece kontrolü:** *Belirli zamanlarda* (her gün 22:00) → hedef: *Kontrol ajanı*. Ajan Veritabanı sorgusu akışıyla açık kalan kayıtları bulur, özeti Mesaj gönder akışıyla kanala iletir.
4. **Banka dosyası:** *Klasöre yeni dosya geldiğinde* (`*.xml`) → hedef: *Banka aktarım akışı* (doğrudan): FTP dosya aktarımı ile bankaya yükler, sonucu e-postayla bildirir.

Bu adımları veya bağlantı alanını kullanan akışlar 0.9.29 ve önceki sürümlerde açılmaz; kullanmayan akışların dosya biçimi değişmez.
