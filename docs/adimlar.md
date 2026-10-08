# Adım rehberi

Adım kütüphanesi 65 adımdır ve hareketleriniz kaydedilip adımlara çevrilebilir. Her adım macOS ve Windows'ta aynı biçimde çalışır; işletim sistemine özgü farklar tabloda belirtilmiştir. Kütüphanenin üstündeki **Adım ara** kutusuna "excel", "tıkla", "bekle" gibi bir kelime yazarak adımı bulabilirsiniz.

## Akışı düzenleme

- **Adım eklemek:** Kütüphanedeki adıma tıklayın veya adımı sürükleyip akıştaki istediğiniz yere bırakın.
- **Yer değiştirmek:** Kartı tutup sürükleyin. Kartın üst yarısına bırakırsanız önüne, alt yarısına bırakırsanız arkasına yerleşir. Bir döngünün, koşulun veya **Hata olursa** bloğunun kesikli alanına bırakırsanız o bloğun içine girer. Bir blok kendi içine taşınamaz. Yukarı/aşağı düğmeleri de çalışmaya devam eder.
- **Diyagram görünümü:** Akış alanının sağ üstündeki **Liste / Diyagram** düğmesiyle geçilir; seçim hatırlanır. Diyagramda adımlar soldan sağa düğümlerdir. **Koşul** düğümünden **Doğruysa** ve **Değilse**, **Hata olursa** düğümünden **Dene** ve **Hata olursa** dalları çıkar. Sonuna kadar giden dallar sağda birleşir ve akış sıradaki adımla devam eder. **Sonraki tura geç**, **Döngüden çık**, **Akışı bitir** veya **Adıma git** ile biten dal birleşme noktasına bağlanmaz; kendi okuyla gittiği yere çizilir. Döngünün iç adımları **Her öğe** çizgisiyle sağa uzanır, sondan kesikli **Sonraki tur** çizgisiyle döngüye döner; döngü bitince **Bitince** çizgisiyle sonraki adıma geçilir.
  - Çizgilerdeki **+** düğmesi o noktaya adım ekler: açılan kutuda adı yazıp Enter'a basın. Boş dallardaki kesikli kutular da aynı işi görür.
  - **Kutuyu taşımak:** Kutuyu tutup istediğiniz yere sürükleyin; bağlantı çizgileri kutuyu izler ve yeri akışla birlikte kaydedilir. Bu yalnız görünümü değiştirir, adımların çalışma sırasını değiştirmez. Alt + ok tuşları seçili kutuyu 10 piksel (Shift ile 40) kaydırır. Sağ alttaki **Kutuları otomatik diz** düğmesi tüm kutuları otomatik yerlerine döndürür.
  - **Sırayı değiştirmek:** Kutuyu bir **+** düğmesinin veya boş bir dalın üzerine bırakın; adım akışta o noktaya taşınır ve yeniden otomatik dizilir. Kütüphaneden sürüklemek için **Kütüphane** düğmesiyle kütüphaneyi açın.
  - Boş alanı sürükleyerek veya kaydırarak gezinin; Ctrl/⌘ + kaydırma veya sağ alttaki düğmeler yakınlaştırır, ⊞ tümünü sığdırır.
  - **Bağlantı kurmak:** Bir kutunun sağındaki yuvarlak noktayı tutup başka bir kutuya bırakın. Akış o adımdan sonra bıraktığınız adımdan devam eder; gerideki bir adıma da bağlayabilirsiniz. Böylece aynı adımları tekrar kopyalamanız gerekmez. Bağlantı mavi kesikli okla çizilir ve **Adıma git** kutusu olarak görünür. Bir koşul veya blok kutusunun bitişinden, boş bir dalın sağından da bağlantı çekilebilir. **Bitiş**'e bırakmak yolu bitirir.
  - **Bağlantıyı kaldırmak:** Fareyi iki kutu arasındaki çizginin (veya **+** düğmesinin) üzerine getirin, çıkan **×** düğmesine basın. O yol orada biter. Döngünün içindeyse **Sonraki tura geç**, değilse **Akışı bitir** kutusu eklenir; istediğiniz zaman değiştirebilirsiniz.
  - **Bu adımdan sonra:** Aynı seçimler sağ paneldeki **Bu adımdan sonra** listesinde de vardır: sıradaki adım, sonraki tur, döngüden çık, akışı bitir veya başka bir adıma git. Liste görünümünde de kullanılır.
  - Hiçbir yolun gelmediği adımlar soluk ve kesikli çizilir; çalışmazlar. Bir bağlantıyla bağlayın veya silin. Bir adımı sildiğinizde ona gelen **Adıma git** bağlantıları da kaldırılır.
  - Düğümün üzerine gelince test ▶, çoğalt ve sil düğmeleri çıkar. Seçili düğümde Delete tuşu adımı siler.
  - Son çalışmada her düğümün sağ üstünde ✓ (birden çok çalıştıysa kaç kez) veya ✗ (hata verdi) görünür. Çalışma ayrıntısındaki **Diyagramda göster**, o çalışmanın sonuçlarını hatalı adım seçili olarak açar.
- **Sonraki adıma geçmeden bekle:** Her adımın ayarlarının en altındaki alandır; varsayılanı 0'dır (beklemez). Örneğin 1,5 yazarsanız adım bittikten sonra akış 1,5 saniye bekler, sonra sıradaki adıma geçer; ayrıca **Bekle** adımı eklemeniz gerekmez. Döngü, koşul ve **Hata olursa** bloklarında blok bütünüyle bittikten sonra bir kez beklenir. Bekleme liste kartında ve diyagram kutusunda saat simgesiyle görünür. Yolu bitiren adımlarda (**Adıma git**, **Sonraki tura geç**, **Döngüden çık**, **Akışı bitir**) ve **Bekle** adımında bu alan yoktur. Önizleme ve **Bu adımı test et** beklemez; **Durdur** beklemeyi hemen keser. Ekranın gerçekten hazır olmasını beklemek için **Pencerede görseli bekle / ara** daha güvenlidir.
- **Not eklemek (bölge seçimi):** Akışın bir bölümünü seçip ona başlıklı bir not ekleyebilirsiniz.
  - Adımları seçmek için Shift veya Ctrl (Mac'te ⌘) basılıyken adımlara tıklayın. Liste görünümünde Shift + tıklama, son tıkladığınız adımla arasındaki adımları da seçer. Diyagramda boş alanda Shift basılıyken sürükleyerek bir bölge çizin; bölgenin değdiği kutular seçilir. Sağ alttaki **Bölge seç** düğmesi açıkken Shift'e basmadan da sürükleyerek seçebilirsiniz.
  - Alttaki çubukta **Not ekle**'ye basın. Sağ panelde notun **Başlık**, **Not** ve **Renk** (sarı, mavi, yeşil, pembe, gri) alanlarını doldurun. Esc tuşu seçimi bırakır.
  - Diyagramda not, adımlarının çevresinde renkli bir çerçeve olarak çizilir; bir döngü veya koşul seçildiyse bloğun tamamını çerçeveler. Liste görünümünde not, ilk adımının üstünde bir bant olarak görünür; kapsadığı adımların sol kenarı notun rengini alır.
  - Notu düzenlemek için başlığına (bandına) tıklayın. Sağ panelde kapsadığı adımlar listelenir: bir adımı nottan çıkarabilir veya seçtiğiniz başka adımları **Seçili adımları bu nota ekle** ile ekleyebilirsiniz. **Notu sil** yalnız notu siler, adımlara dokunmaz.
  - Notlar akışın çalışmasını etkilemez. Bir adımı sildiğinizde notlardan da çıkar; notun son adımı silinirse not da kaldırılır. Bir akışta en fazla 100 not olabilir.
- **Bağlantı seçmek:** Google Sheets ve veritabanı adımlarının ilk alanı **Bağlantı**'dır. Listeden bir bağlantı seçin, **+ Yeni … bağlantısı** ile oluşturun veya kalemle düzenleyin. Boş bırakılan adım varsayılan bağlantıyı kullanır. Ayrıntılar: [Google Sheets bağlantısı](google-sheets.md).
- **Çalıştır:** Adımları gerçekten uygular. **Önizleme (ekranı kullanmadan)** işaretliyse fare, klavye, ekran, dosya, bağlantı ve mesaj adımları atlanır; yalnız veri, metin, hesap ve akış adımları çalışır.
- **Çalışırken Studio:** Masaüstü uygulaması gerçek akış veya adım testi başlamadan önce Windows görev çubuğuna / macOS Dock'a otomatik küçülür. Zamanlanmış çalışmalarda da küçülmenin tamamlanması beklenir; küçültülemezse adımlar başlamaz. Önizlemede pencere açık kalır. Çalışma bitince ya da hata alınca kendiliğinden öne gelmez; sonucu görmek veya **Durdur** düğmesine ulaşmak için görev çubuğundan / Dock'tan açabilirsiniz. Tarayıcı sürümünde pencereyi kendiniz küçültün.
- **Nasıl kullanılır? kutusu:** Bir adıma tıkladığınızda sağ panelin üstünde o adımın kısa kullanım özeti çıkar: sırayla ne yapılacağı, adımın ne ürettiği ve bir ipucu. Her alanın altında da ne yazılacağını anlatan bir açıklama vardır. Kutuyu **Gizle** ile kapatabilirsiniz; adım seçili değilken aynı yerde akışın nasıl kurulacağı özetlenir.
- **Bu adımı test et:** Adımı seçin, sağ paneldeki düğmeye basın. Sadece o adım, içinde başka adımlar varsa onlarla birlikte, gerçek olarak çalışır; akışın geri kalanı çalışmaz. Değer yazmanız gerekmez:
  - Adımın ihtiyaç duyduğu değerler önceki adımlardan kendiliğinden alınır. **Pencereyi tanı**, **Değişken ata**, Sheets/Excel/veritabanı okuma ve ekrandan okuma (OCR) gibi yalnız okuyan adımlar test başlarken çalıştırılır.
  - Döngü içindeki adımda `${row}` olarak listenin **ilk satırı** kullanılır. Pencerede hangi değerin nereden alındığı listelenir; sonuçta kullanılan değerler de gösterilir.
  - Farklı bir değerle denemek için **Başka bir değerle denemek istiyorum** bölümünü açıp yalnız o değeri yazın.
  - Yalnız tıklama yapan veya size soru soran bir adımın ürettiği değer otomatik alınamaz; pencere o değeri sorar.
  - **Yeri göster (tıklamadan):** Tıklama, alan doldurma ve görsele tıklama adımlarında pencereyi öne getirip fareyi hedefin üzerine götürür; tıklamaz ve yazmaz. Hedefin doğru seçildiğini böyle kontrol edin. **Gerçekten çalıştır** adımı uygular.
  - **Tabloya değer yaz → Sütun başlığıyla ekranda bul** yönteminde düğme **Yeri göster (değer yazmadan)** olur: tabloyu tıklayıp kopyalar, hücrenin güncel yerini gösterir; hücreye değer yazmaz ve panoyu geri yükler. Bu yöntem 0.9.8 veya üzerinde kullanılabilir.
  - Döngü içindeki **Sonraki tura geç** / **Döngüden çık** içeren adımlar da test edilir; sonuçta "bu satır atlanır" veya "döngüden çıkılır" yazar.
- **Acil durdurma:** Fareyi ekranın bir köşesine hızla götürmek çalışan akışı durdurur. Çalışma sayfasındaki **Durdur** düğmesi de bir sonraki adımda durdurur.

## Hareketleri kaydet

Editörün üstündeki **Hareketleri kaydet** düğmesi, bir işi bir kez fare ve klavyeyle yapmanızı izler ve adımlara çevirir; AutoHotkey'deki kaydediciye benzer.

1. Hazırlık süresini seçip **Kaydı başlat**'a basın. Masaüstü uygulamasında Studio gizlenir, ekranın sağ altında kırmızı noktalı kayıt kutusu görünür.
2. Hedef uygulamada işi yapın: tıklayın, yazın, kısayol kullanın, sürükleyin, kaydırın.
3. **F9** tuşuna veya kutudaki **Kaydı bitir** düğmesine basın.
4. Oluşan adımları kontrol edin, istemediklerinizin işaretini kaldırıp **Akışa ekle** deyin.

| Hareket | Oluşan adım |
| --- | --- |
| Bir penceredeki tıklama | **Pencereyi tanı** (pencere başına bir kez) ve pencereye göre **Pencerede tıkla**. Pencere taşınsa da doğru yere tıklanır. |
| Ard arda iki tıklama | Çift tık |
| Yazılan metin | **Metin yaz**; yazarken sildiğiniz harfler metinden çıkarılır, Türkçe karakterler korunur |
| Enter, Tab, oklar, F tuşları | **Tuşa bas**; art arda aynı tuş tek adımda sayıyla birleşir |
| Ctrl/Command + tuş | **Klavye kısayolu gönder**. Windows'ta Ctrl, Mac'te Command `mod` olarak kaydedilir; akış diğer işletim sisteminde de çalışır. |
| Basılı tutup sürükleme | **Sürükle ve bırak** |
| Tekerlek | **Fare tekerleğiyle kaydır** |
| 1,5 saniyeden uzun duraklama | **Bekle** (isteğe bağlı) |

Studio'nun kendi pencerelerindeki ve kayıt kutusundaki tıklamalar kaydedilmez. Kaydedilen koordinatlı tıklamaları, uygulama alan kimliği veriyorsa sağ panelde **Ekranda seç → Konum** ile alan kimliğine çevirmeniz önerilir. Böylece ekran boyutu değişse de doğru alan bulunur.

- **macOS:** RpaOrkestrAI'ye Erişilebilirlik ve **Girdi İzleme** izni verilmelidir. İzin yoksa kayıt başlamaz ve Sistem Ayarları'na yönlendiren mesaj görünür.
- **Windows:** Yönetici olarak çalışan uygulamalardaki hareketler, RpaOrkestrAI de yönetici olarak çalışmıyorsa kaydedilemez.
- Kayıt en fazla 30 dakika ve 5.000 hareket sürer. Şifre yazmayın; yazdığınız her şey adım olur.

## Adlar ve değişkenler

Bir adımın sonucu bir **adla** saklanır, sonraki adımlar o adı `${ad}` biçiminde kullanır.

- **Ad verilen alanlar** (ör. **Pencereye verilecek ad**, **Sonucu değişkene kaydet**, **Değişken adı**): yalnız adı yazın, ör. `erp_window`. `${ }` işaretleri burada yazılmaz. Ad harfle başlar; İngilizce harf, rakam ve alt çizgi içerir. `${erp_window}` yazarsanız `erp_window` olarak, alandan çıkınca `Fatura No` gibi bir yazım `Fatura_No` olarak düzeltilir. Alanın altında adın sonraki adımlarda nasıl kullanılacağı görünür.
- **Değerin kullanıldığı alanlar** (ör. **Yazılacak değer**, **Sol değer**): `${erp_window}`, `${row.form_id}` gibi `${ }` ile yazılır. Sağ paneldeki **Akış değişkenleri** etiketine tıklayınca kopyalanır.
- **Pencere** alanı listedir: önceki **Pencereyi tanı** adımlarında ad verdiğiniz pencerelerden seçilir. Seçili ad önceki adımlarda yoksa alanın altında uyarı çıkar.
- Bir adımın kullandığı adı hiçbir önceki adım vermiyorsa **Bu adımı test et** bunu "Bulunamayan değerler" başlığıyla söyler ve yakın bir ad varsa önerir.

## Kayıtlı şifreler

ERP girişi gibi işlerde şifreyi adıma yazmayın. **Ayarlar → Kayıtlı şifreler** bölümünde bir ad (ör. `erp`) ve şifreyi girip kaydedin; adımda `${sifre.erp}` yazın (ör. şifre alanı için **Alanı doldur**). Tipik giriş: **Uygulama, dosya veya adres aç** → **Pencereyi tanı** → **Alanı doldur** (kullanıcı adı) → **Alanı doldur** (`${sifre.erp}`) → **Tuşa bas** (Enter).

- Şifre bu bilgisayarın şifre kasasında durur: Windows'ta **Kimlik Bilgisi Yöneticisi**, Mac'te **Anahtar Zinciri**. Studio yalnız adını tutar ve şifreyi bir daha göstermez; değiştirmek için aynı adla yeniden kaydedin.
- Şifre akış dosyasına ve dışa aktarıma girmez; akışı başka bilgisayara aktarırsanız orada aynı adla yeniden kaydedin. Çalışma günlüğünde, hata mesajlarında ve **Bu adımı test et** sonuçlarında `[gizlendi]` olarak görünür. Gizleme şifrenin aynısını arar: şifreyi yalnız şifre alanına yazdırın; bir adımla değiştirirseniz (büyük harfe çevirme, dosya yolu veya metin içine ekleme) değişmiş hâli gizlenemez.
- Zamanlanmış akışlar da şifreyi kasadan alır. Mac'te Studio güncellendikten sonra ilk kullanımda Anahtar Zinciri erişim izni sorabilir; **Her Zaman İzin Ver** deyin, aksi halde gözetimsiz çalışan akış bu adımda bekler.
- Her çalışma alanının şifreleri ayrıdır; en fazla 200 şifre kaydedilebilir.

## Hazır değişkenler

Her çalışmada `${sistem}` hazır gelir. Aynı akış Windows'ta ve Mac'te doğru klasörü bulur.

| Değişken | Örnek |
| --- | --- |
| `${sistem.masaustu}` | `C:\Users\ali\OneDrive\Masaüstü` · `/Users/ali/Desktop` |
| `${sistem.indirilenler}`, `${sistem.belgeler}`, `${sistem.ev}` | Kullanıcının İndirilenler, Belgeler ve ana klasörü |
| `${sistem.bugun}` | `29.09.2026` |
| `${sistem.baslangic}` | Çalışmanın başladığı tarih ve saat |
| `${sistem.isletim_sistemi}` | `Windows` veya `macOS`. Koşul adımında platforma göre dallanın. |
| `${sistem.kullanici}` | Oturum açan kullanıcı adı |
| `${loop_index}` | Döngülerde 0'dan başlayan tur numarası |

Dosya yolu alanlarında `~/Desktop/rapor.xlsx`, `%USERPROFILE%\Desktop\rapor.xlsx` veya `${sistem.masaustu}/rapor.xlsx` yazabilirsiniz. Mac'te ve Windows'ta `/` ayracı çalışır.

## Pencere

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Pencereyi tanı | Açık pencereyi uygulama adı ve başlığıyla bulur. Diğer pencere adımları bunu kullanır. | `${erp_window}`, `${erp_window.found}` |
| Pencerede tıkla | Alanı konumu, görseli veya alan kimliğiyle bulup tıklar. | — |
| Alanı doldur | Alanı bulur, tıklar, temizler ve değeri yazar. | — |
| Alanın değerini oku | Alandaki değeri okur. Alan kimliğinde doğrudan okunur. Konum ve görselde alan seçilip kopyalanır, pano eski haline döner. Hedef bir tablo/liste ise tablonun tamamı başlıklarıyla gelir. | `${field_value}` |
| Tablodan değer oku | Uygulama tablosundaki bir hücreyi sütun başlığıyla okur; satır numarası 1'den başlar. **Kaç satır var?** seçeneği aramanın sonuç verip vermediğini söyler (0: kayıt yok). | `${table_value}` |
| Tabloya değer yaz (0.9.6+) | **Tablo alanını çiz** ile tek bir tabloyu başlık ve satırlarıyla bir kez seçin; satır, sütun adı ve yeni değeri belirtin. 0.9.8 ile **Sütun başlığıyla ekranda bul**, başlıklarıyla kopyalanan tabloyu seçilen alandaki metinle eşleştirir; sütun genişliği/sırası değişse de dolu ve tamamen görünen hücrenin güncel yerini bulur, yazar ve doğrular. Hücre X/Y'si gerekmez; sütun numarası kabul edilmez. Eski adımlar uygulamanın tablo yapısını kullanmayı sürdürür. Belirsiz veya desteklenmeyen tabloda durur. Kaydetme/onay ayrıca tanımlanır. | `${table_write.row}`, `${table_write.column}`, `${table_write.value}` |
| Pencerede tuşa bas | Tanıtılan pencereye tuş veya kısayol gönderir. | — |
| Pencerede görseli bekle / ara | Pencerede bir işaretin (düğme, başlık, hata kutusu) görünmesini veya kaybolmasını bekler. **Süre dolarsa:** akışı durdurur ya da "bulunamadı" sonucuyla devam eder; böylece bir hata kutusu çıkıp çıkmadığına Koşul ile karar verilir. | `${image.found}`, `${image.center_x}`, `${image.center_y}` |
| Pencereyi öne getir | Pencereyi öne alır; küçültülmüşse açar. | — |
| Pencereyi büyüt / küçült | Büyütür, küçültür veya geri yükler. | — |
| Pencereyi taşı ve boyutlandır | Pencereyi sabit konum ve boyuta getirir. X/Y hedeflerini sabitlemek için akışın başında kullanın. | Güncel pencere |
| Pencereyi kapat | Kapat düğmesine basar; uygulama kaydetmek isterse sorar. | — |
| Pencerenin kapanmasını bekle | Kayıt, yazdırma veya yükleme penceresi kapanana kadar bekler. | — |

Alan kimliği, konum ve görsel yöntemleri [pencere tanıtma rehberinde](pencere-tanitma.md) anlatılır.

**Kaldırılan adım:** *Ekranda görsel ara / bekle* kütüphaneden kaldırıldı ve **Pencerede görseli bekle / ara** ile birleştirildi. Kayıtlı akışlarda aynen çalışmaya devam eder; adımın ayarlarındaki **dönüştür** düğmesi ayarları koruyarak yeni adıma çevirir (bölge kullanılmaz, görsel pencerenin tamamında aranır).

## Fare ve klavye

Bu adımlar ana ekranın koordinatlarını kullanır. **Fare konumunu al (3 sn)** düğmesine basıp 3 saniye içinde fareyi hedefe götürün; X/Y otomatik dolar. Masaüstü uygulamasında Studio bu sırada gizlenir. Pencereye bağlı işlerde **Pencere** adımları daha güvenlidir, çünkü pencere taşınsa da doğru yere tıklarlar.

| Adım | Ne yapar |
| --- | --- |
| Ekranda tıkla | Sol, sağ veya orta düğmeyle tek, çift veya üç tık yapar. |
| Fareyi taşı | İmleci götürür (menü açmak, üzerine gelince açılan listeler). |
| Sürükle ve bırak | Başlangıçtan bitişe basılı tutarak sürükler. İki konum ayrı ayrı alınır. |
| Fare tekerleğiyle kaydır | Dikey veya yatay kaydırır; eksi değer aşağı (yatayda sola), artı değer yukarı (yatayda sağa) kaydırır. |
| Metin yaz | Metni yazar. **Fare konumunu al** ile yazılacak yeri gösterirseniz önce oraya tıklar; boş bırakılırsa imlecin bulunduğu yere yazar. Türkçe karakterler Otomatik yöntemde panodan yapıştırılır. ERP alanları için **Alanı doldur** daha güvenlidir: pencereyi izler ve odak değişirse yazmaz. |
| Klavye kısayolu gönder | `mod+s`, `ctrl+shift+esc`, `alt+f4`, `alt+tab` gibi. `mod`, Windows'ta Ctrl, Mac'te Command'dır. |
| Tuşa bas | Enter, Tab, F5, ok tuşları; tekrar sayısı ve bekleme ile. |
| Tuşu basılı tut / bırak | Shift veya Ctrl basılıyken tıklama (çoklu seçim) için. Akış bittiğinde veya hata verdiğinde basılı kalan tuşlar otomatik bırakılır. |
| Fare konumunu oku | İmlecin konumunu `${mouse.x}`, `${mouse.y}` olarak kaydeder. |

## Ekran ve görsel

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Ekranda görsele tıkla | Görseli bulup tıklar; merkezden fark verilebilir. Aramayı bir bölgeyle sınırlamak için **Bölge çiz**. | Bulunan konum |
| Ekrandan metin oku (OCR) | Bölgedeki yazıyı okur. | `${screen_text}` |
| Ekranda metni bekle | "Kaydedildi" gibi bir yazı görünene kadar bekler. i/İ/ı/I ve büyük/küçük harf farkı gözetilmez. | `${text_found}` |
| Piksel rengini oku | Bir noktanın rengini `#RRGGBB` olarak okur. | `${pixel}` |
| Ekran görüntüsü al | Ekranı veya bölgeyi PNG olarak çalışma çıktılarına ve isterseniz bir klasöre kaydeder. | Dosya yolu |

- **Görsel:** **Ekrandan görsel seç** düğmesine basın. Geri sayımdan sonra ekran yakalanır; aranacak ikon veya düğmeyi fareyle çevreleyin. **Ekranda görsele tıkla** adımında ardından tıklanacak noktayı da seçebilirsiniz.
- **Bölge:** **Bölge çiz** ile görüntüyü alın, fareyi basılı tutarak okunacak alanı dikdörtgen şeklinde çizin ve kaydedin. **Bölge neye göre? = Tanıtılan pencere** seçerseniz bölge pencereye göre saklanır; ERP penceresi taşınsa da doğru yer okunur.
- **OCR:** Ek kurulum gerekmez. macOS'ta Apple Vision, Windows'ta Windows OCR kullanılır ve Türkçe desteklenir. Windows'ta Türkçe veya İngilizce dil paketinin yüklü olması gerekir; çoğu kurulumda zaten vardır. Tesseract kuruluysa yedek olarak kullanılır.

## Uygulama ve sistem

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Uygulama, dosya veya adres aç | **Masaüstünde çift tıklamak gibi.** Programı (ERP'nin `.exe` dosyası), belgeyi, klasörü veya web adresini açar; **Seç…** ile dosya gösterilebilir. Akış programın kapanmasını beklemez. Windows: `notepad.exe`, `C:\Program Files\ERP\erp.exe`, `C:\Rapor.xlsx` · Mac: `TextEdit`, `Microsoft Excel`, `~/Desktop/rapor.xlsx` · `https://…` | — |
| Komut / script çalıştır | **Terminale veya PowerShell'e komut yazmak gibi.** **Ne çalıştırılsın?** alanında: *Komut yaz* — Windows'ta Komut İstemi (cmd), Mac'te Terminal komutu; **Komut nerede çalışsın? = PowerShell** ile PowerShell komutu (Mac'te `pwsh` kurulu olmalıdır). *Script dosyası seç* — `.py` (Python), `.ps1` (PowerShell), `.bat`/`.cmd`, `.vbs` (Windows), `.sh`/`.command`, `.scpt` (Mac), `.jar` (Java) dosyasını türüne uygun programla çalıştırır; parametre verilebilir. Akış bitene kadar bekler; hata koduyla biterse akış durur (kapatılabilir), zaman aşımında ve **Durdur**'da işlem kapatılır. Python için bilgisayarda Python kurulu olmalıdır. Excel, PDF gibi belgeleri bu adım çalıştırmaz; onlar için **Uygulama, dosya veya adres aç**. | `${command.output}`, `${command.error}`, `${command.code}` |
| Uygulamayı kapat | Windows: `EXCEL.EXE` · Mac: `Microsoft Excel`. Zorla kapatma kaydedilmemiş işi kaybettirir. | Kapatıldı mı |
| Panoya kopyala / Panodaki metni oku | Pano üzerinden veri aktarır. | `${clipboard}` |

**Java Web Start ile açılan uygulamalar:** **Ne açılsın? → Seç…** ile normalde çift tıklayarak açtığınız masaüstü kısayolunu (`.lnk`) seçin ve **Parametreler** alanını boş bırakın. Windows'ta kısayolun kayıtlı parametreleri ve çalışma klasörü kullanılır. Alternatif olarak `.jnlp` dosyasını seçebilirsiniz. `javaws.exe` dosyasını doğrudan seçerseniz **Parametreler** alanına kısayolun başlatma parametrelerini, JNLP dosyası veya adresi dahil, yazmanız gerekir; boşluk içeren yolları çift tırnak içine alın.

Eski sürümde kısayol seçerken yalnız `javaws.exe` yolu kaydedilmişse güncellemeden sonra kısayolu yeniden seçip akışı kaydedin. Kaybolmuş parametreler eski kayıttan geri getirilemez. Güncelleme öncesinde kısayolun tam `.lnk` yolunu **Ne açılsın?** alanına elle yazabilirsiniz.

**Dosya / script çalıştır** adımı kütüphaneden kaldırıldı: script'ler **Komut / script çalıştır**, programlar ve belgeler **Uygulama, dosya veya adres aç** ile çalıştırılır. Bu adımı içeren akışlar aynen çalışır; adımı seçince **…adımına dönüştür** düğmesi ayarlarını koruyarak yeni adıma çevirir. **Komut / script çalıştır** adımında *Script dosyası seç* veya *PowerShell* kullanan akışlar 0.9.3 ve önceki sürümlerde açılmaz; yalnız komut yazan akışlar eski sürümlerle uyumludur.

## Dosya ve Excel

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Excel / CSV oku | `.xlsx` veya `.csv` dosyasını satır listesine çevirir. Başlıklar alan adı olur: `${row.Tutar}`. `${row.row_number}` Excel satır numarasıdır. | `${rows}` |
| Excel / CSV'ye yaz | Kayıt listesini yeni dosyaya yazar veya sonuna ekler. Yeni sütunlar başlığa eklenir; `=` ile başlayan metinler formül olarak çalışmaz. | Dosya yolu |
| Metin dosyası oku / yaz | `.txt`, `.json`, günlük dosyaları. Yazmada "sonuna ekle" günlük tutmak içindir. | `${file_text}` |
| Dosya / klasör var mı? | Sonucu Koşul adımında kullanın. | `${file_exists}` |
| Klasördeki dosyaları listele | Desen (`*.pdf`), alt klasör ve sıralama. Liste `name`, `path`, `size` ve `modified` alanlarını içerir. | `${files}` |
| Dosya kopyala / taşı / sil | Kopyala, taşı/yeniden adlandır, sil, klasör oluştur. | Hedef yol |
| Dosyanın oluşmasını bekle | İndirilen dosya tamamlanana kadar bekler (`.crdownload`/`.part` dosyalarını beklemez). Desen kullanılabilir: `~/Downloads/rapor*.xlsx`. | `${file_path}` |
| Departman raporu (CSV) | Kayıtları çalışma çıktılarına indirilebilir CSV olarak yazar. | — |

Masaüstü uygulamasında yol alanlarının yanındaki **Seç…** düğmesi dosya seçme penceresini açar. Excel'de açık bir dosyaya yazılamıyorsa adım bunu bildirir.

## Veri ve metin

| Adım | Ne yapar | Örnek |
| --- | --- | --- |
| Değişken ata | Metin, sayı, liste veya başka bir değişkenin değerini atar. | `sayac` = `0` |
| Hesapla | Güvenli ifade hesaplar. `1.234,56` gibi Türkçe sayılar otomatik çevrilir. | `${sayac} + 1`, `round(tutar * 1.2, 2)`, `adet > 0 and durum == 'Bekliyor'` |
| Metin işlemi | Temizle, BÜYÜK/küçük (Türkçe i/İ kurallı), bul-değiştir, böl, parça al, desenle çıkar/değiştir (regex), sayıya çevir, soldan doldur (`00042`), içeriyor/başlıyor/bitiyor mu? | `Fatura No: (\S+)` → `INV-2026-0042` |
| Tarih ve saat | Şimdi, biçimlendir, gün/ay/yıl ekle, iki tarih farkı, haftanın günü. | `%d.%m.%Y` → `29.09.2026` |
| Liste işlemi | Say, ilk/son/sıradaki öğe, filtrele, sırala, tekrarları kaldır, topla, alan değerleri, birleştir, parça al. | `${rows}` içinde durumu Bekliyor olanlar |
| Listeye ekle | Sonuçları toplayıp sonra Excel'e yazmak için. | `${results}` |

**Hesapla** adımında kullanılabilenler: `+ - * / // % **`, karşılaştırmalar, `and`, `or`, `not`, `x if koşul else y` ve `round`, `abs`, `min`, `max`, `int`, `float`, `number`, `str`, `len`, `sum`, `floor`, `ceil`. Program çalıştıran veya dosyaya erişen ifadeler reddedilir.

## Veritabanı

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Veritabanı sorgusu | Seçilen bağlantıda tek bir `SELECT` (veya `WITH`) sorgusu çalıştırır; sonuç sütun adlarıyla gelen satır listesidir ve doğrudan **Her satır için** döngüsüne verilir. | `${rows}` |

**Bağlantı:** Adımın **Bağlantı** alanından (veya editördeki **Bağlantılar** düğmesinden) **Veritabanı türü** seçilir: SQL Server, PostgreSQL, MySQL / MariaDB, Oracle (servis adıyla) veya SQLite dosyası. Sunucu, port (boşsa varsayılan), veritabanı adı, kullanıcı ve şifre girilir; **Bağlantıyı test et** bağlantıyı dener. SQL Server'da adlı örnek için sunucuya `SUNUCU\SQLEXPRESS` yazıp portu boş bırakın. Windows'ta SQL Server bilgisayardaki ODBC sürücüsüyle (varsa ODBC Driver 18/17, yoksa Windows'un kendi "SQL Server" sürücüsü), Mac'te uygulamayla gelen sürücüyle bağlanır; ek kurulum gerekmez. Listede olmayan durumlar için **Bağlantı adresi (gelişmiş)** seçilip SQLAlchemy adresi yazılabilir.

**Değerler:** Sorguda akış değerlerini `${…}` ile yazın; tırnak koymayın:

```sql
SELECT FATURANO, MUSTERI, TUTAR
FROM FATURALAR
WHERE DURUM = ${durum} AND TARIH >= ${baslangic}
  AND MUSTERIKODU IN (${kodlar})
  AND MUSTERI LIKE '%${ad}%'
```

Tırnak dışındaki `${durum}` sorguya metin olarak eklenmez, ayrı parametre olarak gönderilir; değerdeki tırnak işareti sorguyu bozamaz. Liste değeri (`${kodlar}`) her öğe için bir parametreye açılır. Tırnak içindeki değer (`LIKE '%${ad}%'`) tırnakları kaçırılarak yazılır.

**Yalnız okuma:** Adım `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `SELECT … INTO`, `FOR UPDATE`, `EXEC` gibi değiştiren veya kilitleyen ifadeleri ve noktalı virgülle ayrılmış birden fazla komutu reddeder. Sorgu bittikten sonra işlem her zaman geri alınır. PostgreSQL, MySQL ve Oracle oturumu ayrıca salt okunur açılır; SQLite dosyası salt okunur açılır. SQL Server'da salt okunur oturum yoktur: bağlantıda yalnız okuma yetkisi olan bir kullanıcı kullanın ([veritabanı yetki rehberi](veritabani.md)).

**Satır sınırı:** **En fazla satır** (varsayılan 1000, en çok 100.000) aşılırsa ilk satırlar alınır ve çalışma günlüğünde uyarı görünür. Tarihler `2026-10-05 09:30:00` biçiminde metin, ondalıklar sayı olarak gelir.

Eski akışlardaki **Tablo oku** adımı çalışmaya devam eder; yeni akışlarda **Veritabanı sorgusu** kullanın. **Veritabanı sorgusu** adımı ve yeni bağlantı formu 0.9.3 ve önceki sürümlerde yoktur; bu adımı içeren akışlar o sürümlerde açılmaz.

## Akış

| Adım | Ne yapar |
| --- | --- |
| Koşul | Evet ve Değilse dalları. |
| Her satır için | Listedeki her öğe için iç adımlar (en fazla 100.000 öğe). **Kaçıncı satırdan başlasın?** boşsa ilk kayıttan başlar; 50 yazılırsa ilk 49 kayıt atlanır (yarıda kalan işi sürdürmek için). 1 listenin ilk kaydıdır: Excel'deki başlık satırını **Excel / CSV oku** (**Başlık satırı**), Sheets'tekini **Sheets satırlarını oku** (**Başlangıç satırı**) zaten listeye almaz. `${loop_index}` atlanan kayıtlarla birlikte sayılır (50. kayıtta 49). Bu alanı kullanan akışlar 0.9.3 ve önceki sürümlerde açılmaz. |
| Tekrarla (N kez) | İç adımları N kez çalıştırır; `${loop_index}` 0'dan başlar. |
| Koşul sürdükçe tekrarla | Koşul doğru oldukça tekrarlar; tekrar ve süre sınırı vardır. |
| Döngüden çık / Sonraki tura geç | En içteki döngüyü bitirir veya turu atlar. Yalnız döngü içinde eklenebilir. |
| Adıma git | Akışı seçilen adımdan sürdürür; gerideki bir adıma dönüp adımları tekrarlamak (ör. aramayı başka filtreyle yeniden yapmak) veya iki dalı ortak bir adımda buluşturmak için. Bir döngünün içindeki adıma ancak aynı döngünün içinden gidilir; dışarıdan döngü kutusuna bağlanır, döngünün kendi kutusuna bağlamak sonraki tura geçer. Döngü dışına gitmek döngüyü bitirir. **Her turda en fazla** (varsayılan 10) sonsuz döngüyü önler: aynı bağlantı bir turda daha çok kullanılırsa akış durur. |
| Hata olursa | **DENE** dalında hata olursa akışı durdurmak yerine **HATA OLURSA** dalını çalıştırır. Mesaj `${error_message}` içindedir. Örneğin hatalı satırı Excel'e "Hata" olarak işaretleyip sonraki satıra geçmek için kullanılır. |
| Başka akışı çalıştır | Kayıtlı bir akışı bu noktada çalıştırır; değişkenler ortaktır. ERP'ye giriş gibi ortak işleri tek yerde tutun. En fazla 5 seviye olabilir ve akış kendini çağıramaz. |
| Akışı bitir | Başarıyla veya hata mesajıyla sonlandırır. |
| Bekle / Çalışma notu | Sabit bekleme; günlüğe değer yazma. Bir adımdan sonra beklemek için o adımın **Sonraki adıma geçmeden bekle** alanı da kullanılabilir. |

Bir akış en fazla 200 adım ve 8 seviye iç içe blok içerebilir; Studio bir adımı daha derine bırakmanıza izin vermez. Bir çalışma en fazla 1.000.000 adım çalıştırır.

## Kullanıcı etkileşimi ve web

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Mesaj kutusu göster | Tamam, Tamam/İptal veya Evet/Hayır; yanıt beklenir. **Otomatik kapanma** verilirse kutu o kadar saniye sonra kendiliğinden kapanır (macOS ve Windows). | `${answer}`: `ok`, `cancel`, `yes`, `no`; süre dolarsa `timeout` |
| Kullanıcıdan değer iste | Çalışma sırasında tarih veya fatura no gibi bir değer sorar. | `${user_input}` |
| HTTP isteği gönder (API) | GET/POST/PUT/PATCH/DELETE; JSON gövde ve başlıklarla. | `${response.status}`, `${response.body}` |

## AutoHotkey karşılıkları

| AutoHotkey | RpaOrkestrAI |
| --- | --- |
| `Click`, `MouseMove`, `MouseClickDrag` | Ekranda tıkla, Fareyi taşı, Sürükle ve bırak |
| `Send`, `SendText`, `Send {Enter 3}` | Metin yaz, Klavye kısayolu gönder, Tuşa bas |
| `WinActivate`, `WinWait`, `WinWaitClose`, `WinMaximize`, `WinMove`, `WinClose` | Pencereyi tanı, Pencereyi öne getir, Pencerenin kapanmasını bekle, Pencereyi büyüt / küçült, Pencereyi taşı ve boyutlandır, Pencereyi kapat |
| `ControlSetText`, `ControlGetText`, `ControlClick` | Alanı doldur, Alanın değerini oku, Tablodan değer oku, Pencerede tıkla (alan kimliğiyle) |
| `ImageSearch`, `PixelGetColor` | Pencerede görseli bekle / ara, Ekranda görsele tıkla, Piksel rengini oku |
| `Run`, `RunWait`, `WinClose` / `ProcessClose` | Uygulama, dosya veya adres aç; Komut / script çalıştır; Uygulamayı kapat |
| `FileRead`, `FileAppend`, `Loop Files`, `FileCopy`, `FileMove`, `FileDelete` | Dosya ve Excel adımları |
| `A_Clipboard` | Panoya kopyala / Panodaki metni oku |
| `MsgBox`, `InputBox` | Mesaj kutusu göster, Kullanıcıdan değer iste |
| Macro Recorder | Hareketleri kaydet |
| `Loop`, `Loop Parse`, `while`, `break`, `continue`, `try/catch`, `Gosub`, `Goto` | Tekrarla, Her satır için, Koşul sürdükçe tekrarla, Döngüden çık, Sonraki tura geç, Hata olursa, Başka akışı çalıştır, Adıma git |
| `FormatTime`, `DateAdd`, `StrReplace`, `RegExMatch`, `StrSplit` | Tarih ve saat, Metin işlemi |

## Örnek akışlar

`examples/` klasöründeki akışları **Akışlarım → İçe aktar** ile açıp adım adım test edebilirsiniz.

- [adim-turu.json](../examples/adim-turu.json): ERP gerektirmez. Liste üzerinde döngü, hesaplama, Excel'e yazma ve geri okuma, toplama ve mesaj kutusu adımlarını içerir. Masaüstüne `rpa-adim-turu.xlsx` oluşturur.
- [metin-editoru.json](../examples/metin-editoru.json): Windows'ta Not Defteri'ni, Mac'te TextEdit'i açar. Platforma göre koşul, klavye kısayolu, Türkçe metin yazma ve pencere kapatmayı gösterir.

## İzinler ve sınırlar

- **macOS:** Ekran Kaydı (görsel, OCR, piksel) ve Erişilebilirlik (fare, klavye, pencere, alan kimliği) izinleri RpaOrkestrAI'ye verilmelidir.
- **Windows:** Yönetici olarak çalışan bir uygulamaya normal yetkiyle çalışan RpaOrkestrAI giriş gönderemez; ikisini aynı yetkiyle çalıştırın.
- Ekran ve fare adımları **ana ekranı** kullanır. Kilitli ekranda veya uzak masaüstü küçültülmüşken çalışmaz.
- Komut çalıştırma ve dosya silme adımları sizin yetkinizle çalışır; akışları güvendiğiniz kişilerle paylaşın.
