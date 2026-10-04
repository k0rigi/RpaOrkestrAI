# Zamanlayıcı

Zamanlayıcı, bir akışı sizin yerinize belirlediğiniz zamanlarda başlatır: her sabah 09:00'da, hafta içi her yarım saatte bir veya tek seferlik bir tarihte. Windows Görev Zamanlayıcısı'na benzer; farkı, Studio'nun içinde çalışmasıdır. Böylece lisans denetimi, aynı anda tek akış kuralı, başlamadan önceki geri sayım ve çalışma geçmişi elle başlattığınız çalışmalarla aynıdır. macOS ve Windows'ta aynı şekilde çalışır.

## Zamanlama oluşturma

1. Sol menüden **Zamanlayıcı**'yı açıp **Yeni zamanlama**'ya basın. Akış düzenleyicideyken üstteki **Zamanla** düğmesi aynı pencereyi o akış seçili olarak açar.
2. **Akış** listesinden çalışacak akışı seçin. Zamanı gelince akışın **kaydedilmiş** hâli çalışır; kaydetmediğiniz değişiklikler kullanılmaz.
3. **Ne sıklıkla?** seçimini yapın:

| Seçim | Doldurulacak alanlar | Örnek |
| --- | --- | --- |
| Her gün | Saat | Her gün 09:00 |
| Belirli günler | Saat, günler | Hafta içi 09:00; Pzt, Çar 18:15 |
| Belirli aralıklarla | Başlangıç saati, kaç dakikada bir, bitiş saati (isteğe bağlı), günler | Her 30 dakikada bir, 09:00–18:00 arası, hafta içi |
| Bir kez | Tarih, saat | Bir kez: 31.12.2026 17:00 |

4. Günleri **Pzt … Paz** düğmeleriyle seçin; **Hafta içi**, **Her gün** ve **Hafta sonu** kısayolları da vardır. Belirli aralıklarla çalışan zamanlamada bitiş saati boş bırakılırsa gün sonuna kadar sürer; bitiş saatinin kendisinde yeni bir çalışma başlamaz.
5. Pencerenin altında zamanlamanın özeti ve sonraki üç çalışma zamanı görünür. Bir sorun varsa (gün seçilmemiş, bitiş saati başlangıçtan önce, tarih geçmişte) burada yazar.
6. **Studio kapalıyken kaçırılırsa, açılınca bir kez çalıştır** seçeneği, Studio kapalıyken geçen bir çalışma zamanını Studio açılınca bir kez yapar. Seçili değilse o zaman **Kaçırıldı** olarak yazılır ve sonraki zamana geçilir.
7. **Zamanlamayı oluştur**'a basın.

Zamanlayıcı sayfasındaki tabloda her zamanlamanın akışı, özeti, sonraki çalışma zamanı ve son durumu görünür. **Etkin** kutusu zamanlamayı silmeden kapatır ve açar; kalemle düzenler, çöp kutusuyla silersiniz. Sol menüdeki sayı, açık zamanlama sayısıdır. Bir akışın birden fazla zamanlaması olabilir; bir çalışma alanında en fazla 100 zamanlama tutulur.

## Zamanı gelince ne olur?

1. Studio penceresi öne gelir (simge durumundaysa açılır) ve ekranın üstünde geri sayım görünür: "Sabah raporu · 10 sn sonra başlıyor".
2. Bu sırada fareyi ve klavyeyi bırakın. **İptal et** o çalışmayı yapmaz (zamanlama sonraki zamanda yine çalışır), **Şimdi başlat** beklemeden başlatır.
3. Süre dolunca akış başlar. Çalışma, **Çalışma geçmişi**'nde **Zamanlanmış** etiketiyle görünür; Zamanlayıcı tablosundaki **Çalışmayı gör** bağlantısı da onu açar.

Geri sayım süresi Zamanlayıcı sayfasındaki **Başlamadan önce geri sayım** alanından değiştirilir (0–120 saniye, varsayılan 10). 0 yazarsanız Studio öne gelmeden akış hemen başlar.

**Son durum** sütununda şunlar görünür:

| Durum | Anlamı |
| --- | --- |
| Başlatıldı | Akış zamanında başladı. Sonucunu (tamamlandı / hata) çalışma geçmişinde görürsünüz. |
| Atlandı | Önündeki akışlar zamanlamanın **en fazla gecikme** süresi içinde bitmedi veya lisans o süre boyunca doğrulanamadı; o çalışma yapılmadı. |
| Süre aşıldı | Akış **en uzun çalışma süresi**ni aştığı için durduruldu; sıradaki akış başladı. |
| Kaçırıldı | Studio o saatte kapalıydı. |
| İptal edildi | Geri sayımda **İptal et**'e basıldı. |
| Hata | Akış başlatılamadı (ör. akışta eksik bir ayar var) veya akış silindi. Akış silindiğinde zamanlama kapanır. |

**Bir kez** zamanlaması çalıştıktan (veya atlandıktan) sonra kendiliğinden kapanır. Bir akışı sildiğinizde zamanlamaları da silinir.

## Çakışan akışlar

Aynı anda tek akış çalışır, çünkü fare ve klavye ortaktır. Zamanı gelen akışlar **sıraya girer** ve biri bitince sıradaki başlar. Elle başlattığınız bir çalışma, hareket kaydı veya ekranda hedef seçimi sürerken de zamanlanmış akışlar sırada bekler. Zamanlama penceresindeki **Çakışma ve süre ayarları** bölümünde her zamanlama için üç ayar vardır:

| Ayar | Varsayılan | Anlamı |
| --- | --- | --- |
| Öncelik | Normal | Sırada bekleyenlerden önce **Yüksek**, sonra **Normal**, en son **Düşük** öncelikli başlar. Aynı öncelikte saati daha erken olan önce başlar. |
| En fazla gecikme (dakika) | 60 | Önündeki akışlar yüzünden bundan daha geç başlayacak çalışma **Atlandı** olarak yazılır ve sonraki zamanı beklenir. Saatinde yapılmazsa anlamsız olan işler için kısa tutun. |
| En uzun çalışma süresi (dakika) | 0 (sınır yok) | Akış bu süreyi aşarsa durdurulur (**Süre aşıldı**) ve sıradaki akış başlar. Bir pencereyi sonsuza dek bekleyen akışın diğerlerini kilitlemesini önler. |

Studio her akışın son başarılı çalışmalarına bakarak genelde ne kadar sürdüğünü hesaplar:

- **Çakışma uyarısı:** Zamanlama penceresinin altındaki önizleme, önümüzdeki 7 günde bu zamanlamanın kaç kez bekleyeceğini veya atlanacağını, hangi akışlarla çakıştığını ve başka zamanlamaları geciktirip geciktirmediğini yazar. Akış genelde aralığından uzun sürüyorsa veya en uzun çalışma süresini aşıyorsa da uyarır. Hiç çalışmamış akış 1 dakika sayılır; birkaç çalışmadan sonra uyarılar doğrulaşır.
- **Önümüzdeki 24 saat:** Zamanlayıcı sayfasındaki çizelge, açık zamanlamaların önümüzdeki 24 saatte ne zaman başlayacağını gösterir. Mavi zamanında, turuncu bekleyerek başlayan, kırmızı atlanacak çalışmadır. Bir bloğun üzerine gelince saat ve süre görünür.

Birbirine bağlı akışları (B, A'nın sonucuyla çalışıyorsa) ayrı ayrı zamanlamak yerine bir ana akışta **Başka akışı çalıştır** adımlarıyla sırayla çağırın ve yalnız ana akışı zamanlayın; böylece sıra kesinleşir. Her akışın ilk adımları ERP'yi bilinen bir duruma getirsin (pencereyi tanı, açık kalmış uyarıları kapat); önceki akış yarıda kaldıysa sonraki akış kirli bir ekranla başlamaz.

## Studio açık olmalı

Zamanlanmış akışlar yalnız Studio açıkken çalışır. Pencere simge durumunda (küçültülmüş) kalabilir. Açık bir zamanlama varken Studio penceresini kapatırsanız Studio "Zamanlanmış akışlar yalnız Studio açıkken çalışır. Studio kapatılsın mı?" diye sorar.

Masaüstü adımları kullanıcı oturumunun ekranını kullanır. Bu yüzden:

- Bilgisayar uyku modundaysa veya kapalıysa akış çalışmaz. İş saatlerinde uyku modunu kapatın (Windows: **Ayarlar → Sistem → Güç**; macOS: **Sistem Ayarları → Ekran / Pil**).
- Ekran kilitliyken (Windows'ta kilit ekranı, macOS'ta oturum kilidi) fare ve klavye adımları çalışamaz. Zamanlanmış akışların çalışacağı saatlerde oturumu açık bırakın.
- macOS'ta RpaOrkestrAI'nin Erişilebilirlik ve Ekran Kaydı izinleri gerekir ([kurulum rehberi](kurulum.md)). Windows'ta yönetici olarak çalışan bir ERP'ye, RpaOrkestrAI de yönetici olarak çalışmıyorsa tıklanamaz.

## Bilgisayar açılınca Studio'yu başlat

Zamanlayıcı sayfasındaki **Bilgisayar açılınca Studio'yu başlat (simge durumunda)** ayarı açıkken, bilgisayarda oturum açtığınızda Studio kendiliğinden ve küçültülmüş olarak açılır; zamanlanmış akışlar siz Studio'yu açmadan çalışır. Studio açılırken lisansınızı her zamanki gibi orkestrai.net üzerinden doğrular.

- **Windows:** Ayar, kullanıcı hesabınızın başlangıç listesine **RpaOrkestrAI Studio** kaydını ekler (Görev Yöneticisi → **Başlangıç uygulamaları**'nda görünür). Yönetici izni gerekmez. Uygulamayı kaldırdığınızda bu kayıt da silinir.
- **macOS:** Ayar, `~/Library/LaunchAgents/net.orkestrai.rpa.studio.plist` dosyasını oluşturur. macOS ilk seferde "Arka plan öğesi eklendi" bildirimi gösterebilir; kayıt **Sistem Ayarları → Genel → Giriş Öğeleri** altında görünür ve oradan da kapatılabilir. RpaOrkestrAI'yi **Uygulamalar** klasörüne taşıyıp oradan açın; disk görüntüsünden (DMG) açılmış uygulama için bu ayar açılmaz. Uygulamayı silmeden önce ayarı kapatın.
- Ayar yalnız kurulu masaüstü uygulamasında kullanılabilir; kaynak koddan veya tarayıcıdan çalışan Studio'da devre dışıdır.
- Bilgisayar açıldığında Studio'nun başlaması için oturum açılmış olmalıdır.

## Windows Görev Zamanlayıcısı ile karşılaştırma

| Görev Zamanlayıcısı | RpaOrkestrAI Zamanlayıcı |
| --- | --- |
| Bir kez / Günlük / Haftalık tetikleyici | Bir kez / Her gün / Belirli günler |
| "Görevi şu aralıkla yinele … süresince" | Belirli aralıklarla, başlangıç ve bitiş saati |
| "Zamanlanmış başlatma kaçırılırsa görevi en kısa sürede çalıştır" | Studio kapalıyken kaçırılırsa, açılınca bir kez çalıştır |
| "Görev zaten çalışıyorsa yeni örnek başlatma" | Aynı anda tek akış; çakışan çalışmalar öncelik sırasıyla bekler, en fazla gecikmeyi aşan atlanır |
| "Görev şu süreden uzun çalışırsa durdur" | En uzun çalışma süresi |
| Görev geçmişi | Son durum sütunu ve **Zamanlanmış** etiketli çalışma geçmişi |

Saatler bilgisayarın yerel saatine göredir. Studio'nun kendisi kapalıyken çalışma başlatılamaz; bunun için **Bilgisayar açılınca Studio'yu başlat** ayarını kullanın.
