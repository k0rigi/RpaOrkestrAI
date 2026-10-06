# ERP penceresini ve alanını tanıtma

Bu rehber 0.6.0 sürümündeki pencere tanıma, fareyle hedef seçimi ve alan kimliğiyle hedefleme yöntemlerini anlatır. İade faturası ilk örnektir; aynı adımlar başka masaüstü uygulamalarında da kullanılabilir. Sheets'teki B2, B3, B4 değerlerini durum sütununa göre işlemek için [satır ve koşul rehberini](sheets-satir-dongusu.md) kullanın.

## Pencereyi tanı

1. ERP uygulamasını açın ve ilgili pencereyi görünür hale getirin. Küçültülmüş veya başka masaüstündeki pencereler listelenmez.
2. Studio'da akışınıza **Pencereyi tanı** ekleyin.
3. Sağ panelde **Açık pencerelerden seç** düğmesine basıp ERP penceresini seçin. Uygulama adı ve başlığı doldurulur.
4. **Şimdi kontrol et** ile eşleşmeyi doğrulayın. Bu düğme pencere bilgilerini okur; tıklama veya yazma yapmaz.
5. Başlık belge numarası gibi değişken bilgi içeriyorsa sabit kısmını yazıp **İçerir** seçin. Uygulama adı tam eşleşir. Birden fazla pencere eşleşirse daha belirgin başlık kullanın.
6. **Pencereye verilecek ad** alanında pencereye kısa bir ad verin; varsayılan `erp_window`. Buraya yalnız ad yazılır, `${ }` işaretleri yazılmaz. `${erp_window}` yazarsanız uygulama bunu `erp_window` olarak düzeltir.
7. Akışı kaydedin. Pencere her çalıştırmada yeniden bulunur; geçici pencere kimliği akış dosyasına kaydedilmez.

Sonraki pencere adımlarında (**Pencerede tıkla**, **Alanı doldur** vb.) **Pencere** alanı bir listedir: önceki **Pencereyi tanı** adımlarında ad verdiğiniz pencereler görünür, yazmanız gerekmez. `${erp_window.found}` pencerenin bulunup bulunmadığını verir. Bulunan sonuç ayrıca `title`, `application`, `x`, `y`, `width`, `height` alanlarını içerir. Bulunamayan sonuç yalnız `found: false` içerir.

Varsayılan olarak pencere 5 saniye beklenir; bulunamazsa akış durur. Alternatif olarak **Bulunamadı sonucu ile devam et** seçip sonraki **Koşul** adımında `${erp_window.found}` değerini **Dolu / doğru** ile değerlendirin. ERP işlemlerini koşulun Evet dalına yerleştirin.

Pencere tanıma uygulama adı ve başlığını denetler. Aynı başlık altında birden fazla form açılabiliyorsa doğru formun hazır olduğunu **Pencerede görseli bekle / ara** adımıyla ayrıca kontrol edin.

## FormID alanına değer yaz

**Alanı doldur**, hedef alanı bulur, tıklar ve değeri yazar. Bu işlem için ayrıca **Pencerede tıkla** eklemek gerekmez.

- **Pencere:** listeden, **Pencereyi tanı** adımında ad verdiğiniz pencereyi seçin.
- **Yazılacak değer:** tek hücre okuduysanız `${cell_value}`; **Sheets satırlarını oku** adımında B sütununa `form_id` adını verdiyseniz `${row.form_id}`. Eski **Sheets sütununu oku** akışlarında `${row.value}` geçerlidir.
- **Önce alandaki mevcut değeri temizle:** açık bırakın. Önceki satırın değeri temizlenip yenisi yazılır; kapatırsanız mevcut değere ekleme yapılır.

### Fare konumunu geri sayımla al

**Hedefi bulma yöntemi** olarak **Pencere içi X / Y** seçin:

1. **Ekranda seç** düğmesine basın ve **Konum** yöntemini seçin.
2. **Hazırlık süresi** olarak 3, 5 veya 10 saniye seçin; varsayılan 5 saniyedir.
3. **Tamam, geri sayımı başlat** düğmesine basın. ERP penceresi öne gelir.
4. Fareyi FormID yazı kutusunun içine götürün ve geri sayım bitene kadar orada tutun. Tıklamanız gerekmez; süre sonunda farenin konumu alınır.
5. Studio'ya dönen önizlemede işaretlenen yeri kontrol edin. **Hedefi kaydet** ile X/Y'yi adıma aktarın. **Yeniden ekranda seç** ile geri sayımı tekrar hazırlayabilirsiniz.

Seçmeniz gereken yer `FormID` etiketi değil, yanındaki yazı kutusudur. Seçim işlemi ERP’ye tıklama veya metin göndermez. **Esc**, **Seçimi iptal et** veya seçim penceresini kapatma mevcut hedefi değiştirmeden vazgeçirir. X/Y'yi sağ panelden elle de düzenleyebilirsiniz.

Koordinatlar başlık çubuğu dahil pencerenin sol üst köşesine göredir. Pencere taşınırsa yeni konumu kullanılır. Pencere boyutu, uygulama düzeni, tema veya ekran ölçeği değişirse hedefi yeniden seçin. ERP penceresini ana ekranda ve tamamen görünür tutun.

### Alanı kimliğiyle bul (uygulama yapısı)

Birçok masaüstü uygulaması, ekran okuyucular için alanlarına bir kimlik ve ad verir. Windows'ta bu bilgi **UI Automation** (AutomationId, ad, alan türü), macOS'ta **Erişilebilirlik** (AXIdentifier, başlık/açıklama, rol) üzerinden okunur. Alan bu kimlikle bulunursa tıklanacak nokta, alanın o anki konumundan hesaplanır. Böylece pencere büyütülse, küçültülse, taşınsa veya ekran ölçeği değişse de aynı alana yazılır.

1. **Ekranda seç** → **Konum** yöntemiyle fareyi FormID yazı kutusunun üzerine getirin.
2. Süre bitince Studio, farenin altındaki alanı uygulama yapısından okur. Alan bir kimlik veya ad veriyorsa önizlemede *Uygulama yapısında alan bulundu* yazısı ve iki seçenek görünür:
   - **Alan kimliğiyle bul (önerilen):** Adım, **Hedefi bulma yöntemi = Alan kimliği (uygulama yapısı)** olarak kaydedilir.
   - **Konumla bul (X / Y):** Önceki sürümlerdeki gibi pencere içi X/Y kaydedilir.
3. **Hedefi kaydet** seçin. Sağ panelde kaydedilen alan türü ve kimliği gösterilir. **En fazla bekle (saniye)** alanı, ekran geç açılıyorsa alanın görünmesini bu süre kadar bekler.

Aynı kimlikte birden fazla alan varsa seçtiğiniz alanın sırası kaydedilir. Başka bir sekmede kalan veya görünmeyen alanlara hiçbir zaman tıklanmaz. Alan süre içinde bulunamazsa adım durur; ERP'ye tahmini bir konumda tıklama yapılmaz. Kimlik, seçildiği işletim sistemine özeldir. Aynı akış diğer işletim sisteminde kullanılacaksa alanı o bilgisayarda yeniden seçin.

**Her uygulama alan kimliği vermez.** Önizlemede *uygulama bu alana kimlik veya ad vermiyor* yazıyorsa konum veya görsel yöntemini kullanın. Bu durum genellikle şu uygulamalarda görülür:

- Kendi çizimini yapan veya oyun motoru benzeri arayüzler.
- Windows'ta Java tabanlı istemciler. Bu istemciler alanlarını ancak Java Access Bridge açıksa gösterir; bu sürüm Java Access Bridge'i kullanmaz.
- Citrix, RDP veya başka bir uzak masaüstü içindeki uygulamalar. Burada yalnız ekran görüntüsü vardır.

Adın, alanın içindeki değerle aynı olduğu alanlarda (bazı uygulamalar yazı kutusunun içeriğini ad olarak bildirir) ad kimlik olarak kullanılmaz. Değer her satırda değişeceği için bu alanlar konum veya görsel yöntemiyle hedeflenir.

macOS'ta alan kimliğini okumak için RpaOrkestrAI'ye **Erişilebilirlik** izni verilmelidir. Bu izin, pencereyi öne getirmek için de zaten gereklidir.

### Fareyle görsel alanını kırp

**Ekranda seç** düğmesine basıp **Görsel referans** yöntemini seçin. Hazırlık süresini belirleyip **Tamam, geri sayımı başlat** seçin. Süre sonunda ERP penceresinin görüntüsü üzerinde seçim aracı açılır:

1. Fareyi basılı tutup sürükleyerek **FormID etiketini ve hemen çevresini** kapsayan küçük bir dikdörtgen çizin. Bu, ekranın o anda alınmış görüntüsüdür; ERP üzerinde sürükleme yapılmaz.
2. Ardından değerin yazılacağı **yazı kutusunun içine tıklayın**. Yazı kutusu çizdiğiniz referansın dışında olabilir.
3. **Seçimi kullan** ile Studio'daki önizlemeye dönün. Araç çubuğu hedefi kapatıyorsa **H** ile taşıyabilir; seçimi **R** ile sıfırlayabilirsiniz.
4. Önizlemede hem kırpılacak alanı hem hedef noktayı kontrol edip **Hedefi kaydet** seçin. Önizleme üzerinde hedefi değiştirebilir; **Seçimi temizle** ile dikdörtgeni yeniden çizebilirsiniz.

Yalnız seçilen küçük referans görsel kaydedilir; tüm pencere görüntüsü akışa eklenmez. Görselin merkezi ile seçtiğiniz yazı kutusu arasındaki X/Y farkı otomatik hesaplanır. Gerekirse **Görsel merkezinden sağa / sola** ve **aşağı / yukarı** değerlerini sonradan elle düzeltebilirsiniz. **Pencerede görseli bekle / ara** adımında yalnız referans dikdörtgeni seçilir; tıklanacak alan gerekmez. Önizleme onaylanmadan adımın hedefi değiştirilmez.

Kutunun içindeki değişen fatura/form numarasını referansa dahil etmeyin; sonraki satırda bu içerik değişecektir. Aynı etiket birden fazla yerde görünüyorsa çevresindeki sabit ayrıntıları da seçerek hedefi ayırt edin.

Arama yalnız tanıtılan pencerenin içinde yapılır. Görsel süre içinde bulunamazsa işlem durur. Eşleşme eşiği varsayılan olarak `0.9`'dur. Tema, ölçek veya yazı tipi değişirse referansı yeniden alın; yalnızca eşiği düşürmek benzer bir öğenin seçilmesine yol açabilir.

### Studio içindeki görüntüden seçme

**Görüntü üzerinde seç**, geri sayım kullanmadan ERP pencere görüntüsünü Studio'da açar. Konum için görüntüye tıklayın; görsel için fareyle dikdörtgen çizip hedef noktayı işaretleyin. **Hedefi kaydet** ile uygulayın. Bu yöntem Studio tarayıcıda çalışırken de kullanılabilir; **Ekranda seç** ise yerel masaüstü uygulaması gerektirir.

Konum ve görsel yöntemleri bu sürümde ERP penceresinin **ana ekranda ve tamamı görünür** olmasını gerektirir. Ekran ölçeği, pencere düzeni veya tema değiştiğinde bu hedefleri yeniden tanıtın; alan kimliğiyle kaydedilen hedefler bu değişikliklerden etkilenmez. Seçim sırasında ERP penceresi taşınır/kapanırsa veya başlığı değişirse seçim hata ile durur; doğru pencereyi açıp tekrar seçin. Seçim sürerken akış başlatılamaz; akış çalışırken de hedef seçimi başlatılamaz.

## Tıklama, doldurma ve tuş adımlarının farkı

| Adım | Görevi |
| --- | --- |
| **Pencerede tıkla** | Hedef butona/öğeye tek, çift veya sağ tık yapar; metin yazmaz. |
| **Alanı doldur** | Hedef yazı alanına tıklar, istenirse içeriğini temizler, değeri yazar. |
| **Pencerede tuşa bas** | Tanıtılan pencereye Enter, Tab veya bir kısayol gönderir; hedef alan aramaz. |
| **Pencerede görseli bekle / ara** | Bir işaretin görünmesini ya da kaybolmasını bekler; fare/klavye işlemi yapmaz. |
| **Bekle** | Sabit süre bekler; ekranın hazır olduğunu doğrulamaz. |

Eski akışlardaki **Pencereye metin yaz** adımı **Odaktaki alana yaz (eski)** adıyla düzenlenebilir. Bu adım yalnız odaktaki alana ekleme yapar. Yeni kütüphanede alanı açıkça seçen **Alanı doldur** kullanılır; mevcut akışların davranışı sessizce değiştirilmez.

Her giriş adımı hedef pencereyi öne getirip odağı doğrular. Pencere kapanır, seçiciyle eşleşmez veya odak doğrulanamazsa işlem durur. Başlığı değişen bir ekrana geçtikten sonra yeniden **Pencereyi tanı** ekleyin. Akış çalışırken fare ve klavyeyi başka işler için kullanmayın.

## macOS ve Windows

- Kurulum paketleri gerekli Python otomasyon bağımlılıklarını içerir. Kaynak koddan çalıştırırken `.[automation]` bağımlılıkları kurulmalıdır.
- **macOS:** pencere başlıkları ve ekran görüntüleri için Ekran Kaydı; pencereyi öne getirme, alan kimliğini okuma ve giriş için Erişilebilirlik / Otomasyon izinleri gerekir. Kurulu uygulamada izinleri **RpaOrkestrAI** için verin. Kaynak koddan çalıştırıyorsanız başlatan Python/Terminal için izin gerekebilir. İzin değişikliğinden sonra uygulamayı yeniden açın.
- **Windows:** pencere listeleme Windows API'sini, alan kimliği UI Automation'ı kullanır. ERP farklı bir oturumda veya yükseltilmiş yetkiyle çalışıyorsa giriş engellenebilir. Odağın doğrulanamadığı durumda adım durur.
- Temizleme kısayolu Windows'ta **Ctrl+A**, macOS'ta **Command+A** kullanır. İki işletim sisteminde ERP uygulama adı, pencere başlığı, görünüm veya koordinatlar farklıysa hedefleri o bilgisayarda yeniden seçin.

**Önizleme (ekranı kullanmadan)** seçeneği akış parametrelerini kontrol eder; hedefi henüz seçilmemiş bir alan için yapılandırma ister. Pencere aramaz, Sheets'e bağlanmaz ve fare/klavye kullanmaz. Harici veri gerçek olmadığı için satır döngüsünün gerçek sonuçlarını göstermez. **Ekranda seç**, **Görüntü üzerinde seç** ve **Şimdi kontrol et** tasarım araçlarıdır; bunları ayrıca kullanarak hedefi belirleyin. Gerçek çalışmayı önce tek satır ve onay/kayıt işlemi içermeyen bir örnekle doğrulayın. Tek bir pencere adımını, örneğin **Alanı doldur**, sağ paneldeki **Bu adımı test et** ile `${row.form_id}` için örnek değer girerek deneyebilirsiniz. Adım gerçekten tıklar ve yazar, akışın geri kalanı çalışmaz.

Kütüphanedeki adımları yıldızlayarak **Sık kullanılanlar** bölümüne taşıyabilirsiniz.


## Tabloya değer yaz (0.9.6+)

Önce **Pencereyi tanı**, ardından **Tabloya değer yaz** ekleyin. 0.9.7 sürümünden itibaren **Ekranda seç** ile tablonun içindeki bir noktayı veya sabit bir başlığı gösterin. Referans görsel, konum ve alan kimliği yöntemleri tablo okuma adımıyla aynıdır. Bir görselin dışındaki tabloyu hedefliyorsanız hedef noktayı tablonun içinde seçin; fark otomatik kaydedilir.

Ana formda **Satır**, **Yazılacak sütun** ve **Yazılacak değer** bulunur. Satır ve sütun numaraları 1'den başlar, başlık satırı sayılmaz; sütun adı da kullanılabilir. Her akış kendi sabit değerlerini veya değişkenlerini kullanır; belirli bir kayıt türü varsayılmaz.

**Diğer seçenekler** altında değere göre satır bulma, eşleştirme ayarları ve sonuç değişkeni bulunur. Kayıt sırası değişiyorsa **Satır seçimi → Benzersiz değeri bul** seçin; aranacak sütunu ve o kaydı ayırt eden değeri belirtin. Tam eşleşme aranır. Hiç satır bulunmazsa veya birden fazlası eşleşirse yazılmaz.

**Penceredeki tek tablo** yöntemi, hedef seçmeden tek tabloyu kullanır. Gerekirse **Diğer seçenekler** altında tablo adı/kimliği girilebilir. 0.9.6 ile kaydedilen adımlar bu yöntemle aynen çalışır; otomatik olarak görsel istemeye başlamaz. Referanslı tablo yazma için 0.9.7 veya üzeri gerekir.

**Yeri göster** yalnız hücreyi gösterir. Gerçek çalıştırma değeri doğrudan hücreye yazar ve geri okuyarak doğrular. Salt okunur/görünmeyen hücre, değişen pencere veya kaybolan odakta akış durur. Doğrulama başarısızsa uygulamayı kontrol edin: yazma denenmiş olabilir. Kaydetme veya onay gerekiyorsa ilgili adımı akışınıza göre ekleyin. Bu adım tek adım testinin hazırlığında kendiliğinden çalıştırılmaz.

Windows'ta UI Automation Grid/Table ve Value, macOS'ta Erişilebilirlik tablo ve düzenlenebilir hücre desteği gerekir. Referans, hangi tablonun kullanılacağını belirler; uygulamanın sunmadığı hücre erişimini sağlamaz. Kopyalanabilen her tablo doğrudan yazmayı desteklemeyebilir. Destek yoksa adım açıklamayla durur; **Alanı doldur** gibi diğer yöntemler kullanılabilir.

## Metin okunacak bölgeyi çizme

**Ekrandan metin oku (OCR)** ve bölge destekleyen ekran adımlarında **Bölge çiz** seçin. Ekran görüntüsünü alın, fareyi basılı tutarak bir dikdörtgen çizin, **Bölgeyi kaydet** deyin. **Seçimi temizle** ile yeniden çizebilir, Escape ile değişikliği iptal edebilirsiniz. Görüntü küçültülmüş gösterilse bile gerçek piksel koordinatları kaydedilir.

**Pencereye göre** seçiliyse önceki **Pencereyi tanı** adımındaki pencerenin görüntüsü kullanılır ve bölge pencere içinde kaydedilir. **Ekrana göre** seçim ana ekran koordinatlarını kullanır. Köşeleri ayrı ayrı üç saniye bekleyerek seçmeye gerek yoktur.
