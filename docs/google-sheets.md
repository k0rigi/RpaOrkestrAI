# Google Sheets bağlantısı

Sheets adımları (Sheets satırlarını oku, hücresini oku/yaz) için iki bağlantı yöntemi vardır. İkisi de ücretsizdir. Seçim **Bağlantılar ve ayarlar → Google Sheets → Bağlantı yöntemi** alanından yapılır.

| | Apps Script (önerilen) | Google servis hesabı |
| --- | --- | --- |
| Gereken | Tablonun sahibi olan Google hesabı | Google Cloud projesi, Sheets API, JSON anahtar dosyası |
| Kurulum süresi | 5 dakika | 10–15 dakika |
| Tablonun paylaşımı | Değişmez; tablo gizli kalır | Tablo, servis hesabının e-postasıyla paylaşılır |
| Güvenlik | Yalnız RpaOrkestrAI'nin bildiği anahtarla çalışır | JSON dosyası bir şifre gibi korunur |
| Birden fazla tablo | Betik, hesabınızın erişebildiği her tabloyu açabilir | Her tablo servis hesabıyla paylaşılır |

## Apps Script ile kurulum

1. RpaOrkestrAI'de **Bağlantılar ve ayarlar → Google Sheets** bölümünde **Bağlantı yöntemi**'ni **Apps Script** seçin.
2. **Apps Script kodunu göster**'e basın, ardından **Kopyala**'ya basın. Kodun içinde bu bilgisayar için oluşturulmuş gizli bir anahtar vardır.
3. Google Sheets'te tablonuzu açın ve **Uzantılar → Apps Script** menüsüne girin.
4. Editördeki mevcut kodun tamamını silip kopyaladığınız kodu yapıştırın. Kaydet simgesine basın veya Ctrl+S / Command+S kullanın.
5. Sağ üstten **Dağıt → Yeni dağıtım**'ı seçin. Açılan pencerede:
   - Türü seç (dişli simgesi): **Web uygulaması**
   - **Yürütme:** Ben
   - **Erişimi olanlar:** **Herkes**
6. **Dağıt**'a basın ve izin isteğini onaylayın. "Google bu uygulamayı doğrulamadı" uyarısı çıkarsa **Gelişmiş → (proje adı) sayfasına git (güvenli değil)** yolunu izleyin. Bu uyarı kendi yazdığınız betiklerde her zaman görünür; betik yalnız sizin hesabınızla çalışır.
7. Verilen **Web uygulaması URL**'sini kopyalayın. Adres `https://script.google.com/macros/s/…/exec` biçimindedir.
8. RpaOrkestrAI'de bu adresi **Web uygulaması adresi** alanına yapıştırıp **Kaydet**'e basın.
9. **Test tablosu** alanına tablonun adresini yazıp **Bağlantıyı test et**'e basın. "Bağlantı çalışıyor" mesajı görünmelidir.

Artık Sheets adımlarında tablonun adresini ve sayfa adını girmeniz yeterlidir.

### Neden "Erişimi olanlar: Herkes"?

RpaOrkestrAI, Google hesabınızla oturum açmadan betiğe istek gönderir. "Herkes" ayarı tablonuzu açık hale getirmez; yalnızca betiğin adresine istek gönderilebilmesini sağlar. Betik her istekte gizli anahtarı kontrol eder, anahtar tutmazsa hiçbir şey okumaz veya yazmaz. Adresi ve anahtarı paylaşmayın.

### Sık karşılaşılanlar

| Mesaj | Çözüm |
| --- | --- |
| Güvenlik anahtarı eşleşmiyor | Betikteki kod eski anahtarla kalmış. **Apps Script kodunu göster** ile kodu yeniden kopyalayıp yapıştırın ve yeniden dağıtın. |
| Dağıtımda Erişimi olanlar: Herkes seçilmemiş olabilir | **Dağıt → Dağıtımları yönet → Düzenle** bölümünde erişimi **Herkes** yapın. |
| Sayfa bulunamadı | Adımdaki **Sayfa adı** alttaki sekmenin adıyla birebir aynı olmalıdır (ör. `Sayfa1`). |
| Kodu değiştirdim ama eski davranış sürüyor | Apps Script değişiklikleri yeniden dağıtılmadan yayına çıkmaz: **Dağıt → Dağıtımları yönet → Düzenle → Sürüm: Yeni sürüm → Dağıt**. Adres değişmez. |

**Yeni anahtar oluştur**, eski anahtarı geçersiz kılar. Yeni kodu yapıştırıp yeni sürüm olarak dağıtmanız gerekir. Anahtarın başkasının eline geçtiğinden şüphelenirseniz bu yolu kullanın.

Betik, bir hücreye yazarken `=`, `+`, `-` veya `@` ile başlayan metinleri, sayı ve tarih gibi görünen metinleri (`0042`, `01.02.2026`) düz metin olarak yazar. Böylece iş verisi formüle veya sayıya dönüşmez. Eşzamanlı yazmalar sırayla işlenir.

## Google servis hesabı ile kurulum

1. [console.cloud.google.com](https://console.cloud.google.com) adresinde yeni bir proje oluşturun.
2. **API'ler ve Hizmetler → Kitaplık** bölümünde **Google Sheets API**'yi etkinleştirin.
3. **IAM ve Yönetici → Hizmet Hesapları** bölümünde bir hizmet hesabı oluşturun; rol vermeyin.
4. Hizmet hesabının **Anahtarlar** sekmesinden **Anahtar ekle → JSON** ile anahtar dosyasını indirin.
5. Tablonuzu dosyadaki `client_email` adresiyle **Düzenleyen** olarak paylaşın.
6. RpaOrkestrAI'de **Bağlantı yöntemi**'ni **Google servis hesabı** seçip dosyanın tam yolunu yazın ve kaydedin.

Google Workspace kuruluşlarında anahtar oluşturma, yönetici politikasıyla kapalı olabilir. Bu durumda Apps Script yöntemini kullanın.

## Kotalar

Her iki yöntem de ücretsizdir. Apps Script için Google'ın günlük çalıştırma süresi sınırları vardır; satır okuma/yazma gibi kısa işlemler bu sınırların çok altında kalır. Binlerce hücreye ayrı ayrı yazmak yerine mümkünse bir aralığı tek adımda yazın.
