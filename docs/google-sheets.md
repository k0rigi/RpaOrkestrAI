# Google Sheets bağlantısı

Sheets adımları (Sheets satırlarını oku, hücresini oku/yaz) bir **bağlantı** ile çalışır. Bağlantı, adımın ilk alanı olan **Google Sheets bağlantısı**'ndan oluşturulur ve seçilir. Aynı bilgisayarda birden fazla bağlantı olabilir; örneğin "Satış tablosu" bir Google hesabının betiğiyle, "İade tablosu" başka bir hesabın betiğiyle çalışabilir. Bağlantı seçilmeyen Sheets adımı **varsayılan** bağlantıyı kullanır. Tüm bağlantılar editördeki **Bağlantılar** düğmesinden de yönetilir.

Her bağlantı iki yöntemden birini kullanır; ikisi de ücretsizdir.

| | Apps Script (önerilen) | Google servis hesabı |
| --- | --- | --- |
| Gereken | Tablonun sahibi olan Google hesabı | Google Cloud projesi, Sheets API, JSON anahtar dosyası |
| Kurulum süresi | 5 dakika | 10–15 dakika |
| Tablonun paylaşımı | Değişmez; tablo gizli kalır | Tablo, servis hesabının e-postasıyla paylaşılır |
| Güvenlik | Yalnız RpaOrkestrAI'nin bildiği anahtarla çalışır | JSON dosyası bir şifre gibi korunur |
| Birden fazla tablo | Betik, hesabınızın erişebildiği her tabloyu açabilir | Her tablo servis hesabıyla paylaşılır |

## Apps Script ile kurulum

1. Akışa bir Sheets adımı ekleyin. Sağdaki **Google Sheets bağlantısı** alanında **+ Yeni Google Sheets bağlantısı…** seçin (ilk bağlantıda **Google Sheets bağlantısı oluştur** düğmesi görünür).
2. Bağlantıya bir ad verin (ör. `Satış tablosu`), **Bağlantı yöntemi** **Apps Script** kalsın. **Apps Script kodunu göster**'e, ardından **Kopyala**'ya basın. Kodun içinde bu bağlantı için oluşturulmuş gizli bir anahtar vardır; bağlantı bu anda kaydedilir, pencereyi kapatsanız da anahtar kaybolmaz.
3. Google Sheets'te tablonuzu açın ve **Uzantılar → Apps Script** menüsüne girin.
4. Editördeki mevcut kodun tamamını silip kopyaladığınız kodu yapıştırın. Kaydet simgesine basın veya Ctrl+S / Command+S kullanın.
5. Sağ üstten **Dağıt → Yeni dağıtım**'ı seçin. Açılan pencerede:
   - Türü seç (dişli simgesi): **Web uygulaması**
   - **Yürütme:** Ben
   - **Erişimi olanlar:** **Herkes**
6. **Dağıt**'a basın ve izin isteğini onaylayın. "Google bu uygulamayı doğrulamadı" uyarısı çıkarsa **Gelişmiş → (proje adı) sayfasına git (güvenli değil)** yolunu izleyin. Bu uyarı kendi yazdığınız betiklerde her zaman görünür; betik yalnız sizin hesabınızla çalışır.
7. Verilen **Web uygulaması URL**'sini kopyalayın. Adres `https://script.google.com/macros/s/…/exec` biçimindedir.
8. RpaOrkestrAI'deki bağlantı penceresinde bu adresi **Web uygulaması adresi** alanına yapıştırın.
9. **Test tablosu** alanına tablonun adresini yazıp **Bağlantıyı test et**'e basın. "Bağlantı çalışıyor" mesajı görünmelidir. **Kaydet**'e basın.

Adım artık bu bağlantıyı kullanır; durum satırında **Hazır** yazar. Diğer Sheets adımlarında aynı bağlantıyı listeden seçin; tablonun adresini ve sayfa adını adımda girmeniz yeterlidir.

### Neden "Erişimi olanlar: Herkes"?

RpaOrkestrAI, Google hesabınızla oturum açmadan betiğe istek gönderir. "Herkes" ayarı tablonuzu açık hale getirmez; yalnızca betiğin adresine istek gönderilebilmesini sağlar. Betik her istekte gizli anahtarı kontrol eder, anahtar tutmazsa hiçbir şey okumaz veya yazmaz. Adresi ve anahtarı paylaşmayın.

### Sık karşılaşılanlar

| Mesaj | Çözüm |
| --- | --- |
| Güvenlik anahtarı eşleşmiyor | Betikteki kod eski anahtarla kalmış veya başka bir bağlantının kodu yapıştırılmış. Adımdaki bağlantının yanındaki kalemle pencereyi açıp **Apps Script kodunu göster** ile kodu yeniden kopyalayın, yapıştırın ve yeniden dağıtın. |
| Seçilen bağlantı bu bilgisayarda yok | Akış başka bir bilgisayardan aktarılmış. Bağlantı bilgileri akışla taşınmaz; adımda listeden bir bağlantı seçin veya yeni oluşturun. |
| Bağlantının ayarları eksik | Bağlantı kaydedilmiş ama Web uygulaması adresi girilmemiş. Adımdaki kalemle bağlantıyı açıp adresi ekleyin. |
| Dağıtımda Erişimi olanlar: Herkes seçilmemiş olabilir | **Dağıt → Dağıtımları yönet → Düzenle** bölümünde erişimi **Herkes** yapın. |
| Sayfa bulunamadı | Adımdaki **Sayfa adı** alttaki sekmenin adıyla birebir aynı olmalıdır (ör. `Sayfa1`). |
| Kodu değiştirdim ama eski davranış sürüyor | Apps Script değişiklikleri yeniden dağıtılmadan yayına çıkmaz: **Dağıt → Dağıtımları yönet → Düzenle → Sürüm: Yeni sürüm → Dağıt**. Adres değişmez. |

Bağlantı penceresindeki **Yeni anahtar oluştur**, o bağlantının eski anahtarını geçersiz kılar. Yeni kodu yapıştırıp yeni sürüm olarak dağıtmanız gerekir. Anahtarın başkasının eline geçtiğinden şüphelenirseniz bu yolu kullanın.

Betik, bir hücreye yazarken `=`, `+`, `-` veya `@` ile başlayan metinleri, sayı ve tarih gibi görünen metinleri (`0042`, `01.02.2026`) düz metin olarak yazar. Böylece iş verisi formüle veya sayıya dönüşmez. Eşzamanlı yazmalar sırayla işlenir.

## Google servis hesabı ile kurulum

1. [console.cloud.google.com](https://console.cloud.google.com) adresinde yeni bir proje oluşturun.
2. **API'ler ve Hizmetler → Kitaplık** bölümünde **Google Sheets API**'yi etkinleştirin.
3. **IAM ve Yönetici → Hizmet Hesapları** bölümünde bir hizmet hesabı oluşturun; rol vermeyin.
4. Hizmet hesabının **Anahtarlar** sekmesinden **Anahtar ekle → JSON** ile anahtar dosyasını indirin.
5. Tablonuzu dosyadaki `client_email` adresiyle **Düzenleyen** olarak paylaşın.
6. RpaOrkestrAI'de adımın **Google Sheets bağlantısı** alanından yeni bağlantı oluşturun, **Bağlantı yöntemi**'ni **Google servis hesabı** seçin, **Seç…** ile JSON dosyasını gösterin. **Bağlantıyı test et** dosyadaki `client_email` adresini gösterir; tabloyu bu adresle paylaştığınızdan emin olup kaydedin.

Google Workspace kuruluşlarında anahtar oluşturma, yönetici politikasıyla kapalı olabilir. Bu durumda Apps Script yöntemini kullanın.

## 0.6'dan gelenler

0.6'da **Bağlantılar ve ayarlar** sayfasında kurulan Sheets ve veritabanı ayarları, 0.7'ye ilk açılışta **Google Sheets** ve **Veritabanı** adlı varsayılan bağlantılara dönüştürülür. Mevcut akışlar değişmeden çalışır. Ayarlar sayfasında artık yalnız lisans, güncellemeler ve gelişmiş OCR ayarları bulunur.

## Kotalar

Her iki yöntem de ücretsizdir. Apps Script için Google'ın günlük çalıştırma süresi sınırları vardır; satır okuma/yazma gibi kısa işlemler bu sınırların çok altında kalır. Binlerce hücreye ayrı ayrı yazmak yerine mümkünse bir aralığı tek adımda yazın.
