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

**0.9.11 ile sadeleştirilen kullanım:** tabloyu bir noktadan tanıtın; satır, sütun ve yeni değeri belirtin. Alan çizmek veya okuma adımından ayar aktarmak gerekmez.

1. **Pencereyi tanı** ile pencereyi tanıtın ve **Tabloya değer yaz** ekleyin.
2. **Tabloyu seç** düğmesine basın. Açılan pencere görüntüsünde tablonun herhangi bir hücresine tıklayın. Windows’ta Ctrl+A/C, macOS’ta Command+A/C ile tablo kopyalanır; doğrudan erişim veren uygulamalarda tablo yapısı da kullanılabilir. Kopyalanan ilk satır veri ise seçim ekranındaki **Kopyalanan ilk satır sütun başlıklarıdır** kutusunu kapatın. Satır sayısı ve sütunlar okununca seçim tamamlanır; pano yolunda kopyalanan ilk beş satır önizlenir. **Başlık yap** ile sütun adlarını içeren satırı seçin. Başlık yoksa **Başlık yok** seçin. **Başlık**, **Atlanır** ve **Veri 1** etiketleri hangi satırın nasıl kullanılacağını gösterir. Bu seçim uygulamaya tekrar tıklamaz veya değer yazmaz; önizleme ve kayıtlı ayar güncellenir.
3. **Satır**, **Yazılacak sütun** ve **Yazılacak değer** girin. Örneğin `1`, `Durum`, `Tamamlandı`. Sütunu önerilen listeden seçebilir, adını veya `sutun_2` / `2` yazabilirsiniz. Değişken kullanılabilir.
4. **Bu adımı test et → Yeri göster (değer yazmadan)** hedefi kontrol eder. **Gerçekten çalıştır** seçilen hücreyi değiştirir.

Seçilen nokta yalnız tabloyu tanıtır; yazılacak hücrenin sabit X/Y konumu değildir. Sütun genişliği değiştiğinde hücre güncel yapıdan yeniden bulunur. Pencere içindeki tablo bütünüyle başka yere taşınırsa **Tabloyu seç** ile yeniden tanıtın.

Uygulama hücrelerine doğrudan erişim sunuyorsa tablo yapısı kullanılır. Sunmuyorsa tıklanan tablonun tamamı kopyalanır; hedef hücre ve aynı kaydı ayırt eden başka bir görünür değer doğrulanır. Dikdörtgen çizmek gerekmez. Aynı içerikte birden fazla tablo veya belirsiz bir hücre varsa yazılmaz. Bu ikinci yöntemde ayırt edici hücre dolu ve görünür olmalıdır; ekran dışındaki/kırpılmış hücrelere tahminle giriş yapılmaz.

**Boş hücreye yazma (0.9.13+):** Kopyalanan tabloda hedef hücre boşsa yeri iki ölçümün kesişiminden bulunur: hedef sütunun ekrandaki başlığı (yatay) ve aynı satırda, tablonun hiçbir başka hücresinde geçmeyen dolu bir değer (dikey; ör. kayıt veya fatura kodu). Sütun genişliği, satır yüksekliği veya ekran ölçeği tahmin edilmez ve kaydedilmez; her çalışmada yeniden ölçülür. **Tabloyu seç** noktası tablonun herhangi bir veri satırında, hedef sütundan uzak bir sütunda olabilir; yatay konum yalnız yan yana duran tabloları ayırmak için kullanılır (0.9.14+). Başka bir başlığın içinde geçen başlıklar (ör. Miktar ve Onaylanan Miktar) birbirine karıştırılmaz. Şu durumlarda yazılmaz: hedef sütunun başlığı görünmüyorsa (hata mesajı ekranda okunan başlıkları listeler; başlık kısaltılmış görünüyorsa sütunu genişletin), satırı ayırt eden değer yoksa veya ekranda değilse (satır kaydırılmışsa), tabloda boş olan yerde ekranda metin görünüyorsa, aynı satır birden fazla yerde eşleşiyorsa. Hücre düzenlemeye açıldığında içinin boş olduğu kontrol edilir; yazma sonrasında tablonun tamamı yeniden kopyalanıp yalnız hedef hücrenin değiştiği doğrulanır. Bu özellik akış dosyasına yeni alan eklemez; akışlar eski sürümlerde de açılır, ancak boş hücreye yazma 0.9.13 veya üzeri gerektirir.

**Diğer seçenekler kaldırıldı.** Yeni adımda elle koordinat, alan veya hücre düzenleme yöntemi girilmez. Başlık tercihi önizlemeden düzeltilebilir. Hücre düzenlemesi tek tıklama, F2 veya çift tıklamayla otomatik kontrol edilir; başka açma yöntemine yalnız kopyalanan tablo hâlâ değişmemişse geçilir. Mevcut hücre metni ve konumu doğrulanmadan değer gönderilmez. Eski benzersiz satır eşleşmesi kullanan adımlarda aranan sütun/değer açıkça görünür.

Sütun numarası soldan başlayan tablo sırasıdır; boş/kutucuk sütunları da sayılır. Gerçek başlık aynı adla bulunuyorsa adı önceliklidir. Sütun sırası değişiyorsa gerçek başlığı tercih edin.

Yazma sonrasında yalnız hedef hücrenin değiştiği, tüm tablo yeniden kopyalanarak doğrulanır; yeni metnin ekrana sığması gerekmez. Ayrıntılarda tablo okuma, hedef bulma, hücre açma, yazma ve doğrulama aşamaları izlenebilir. Sonuç belirsizse başka yöntemle yeniden yazılmaz. Pano eski haline getirilir; pencere veya odak değişirse işlem durur. Kaydetme/onay ayrı bir adımdır.

Eski adımlar açılıp kaydedildiğinde otomatik olarak değiştirilmez. **Tabloyu seç** başarılı olunca yeni yönteme geçilir; satır, sütun ve değer korunur. İptal veya tablo okuma hatası eski hedefi değiştirmez. Eski alan/yapı yöntemleri kayıtlı akışlarda çalışmaya devam eder; hedefi değiştirmek için **Tabloyu seç** kullanılır. Noktadan seçilmiş tablolarda düzenleme artık otomatik doğrulanır. Bu sadeleştirilmiş kullanım için **0.9.11 veya üzeri** gerekir.

**0.9.12 başlık düzeltmesi:** Kopyanın başında boş bir satır, ardından sütun adları varsa sütun adlarının bulunduğu ikinci satırda **Başlık yap** seçin. İlk iki satır veri sayılmaz; bir sonraki kayıt Satır 1 olur. Sütun adları ilk veri satırında görünüyorsa da aynı şekilde o satırı başlık seçin. Başlık seçimi, yazılacak sütun/değer değişkenlerini veya mevcut Satır değerini değiştirmez; Satır 1’i önizlemedeki Veri 1 ile karşılaştırın.

**Tablodan değer oku** adımında aynı kopyalama düzeni için **İlk satır sütun başlıklarıdır** açıkken **Başlık satırı** değerini eşitleyin (ilk satır: 1; önünde boş satır varsa: 2). Tamamen boş fakat sütun ayırıcıları içeren gerçek veri satırları korunur; okuma ve yazma satırları aynı sayar. Başlık metninden veya boş hücrelerden otomatik tahmin yapılmaz.

Başlık ilk satırdaysa yeni `header_row` parametresi akış dosyasına eklenmez. Daha sonraki bir başlığı seçen akışlar `header_row` kullanır ve **0.9.12 veya üzeri** gerektirir. Uygulama doğrudan tablo yapısı sunuyorsa kendi başlık/veri ayrımı kullanılır. Boş hedef hücreler için yukarıdaki **Boş hücreye yazma** bölümüne bakın.


## Metni bul, tıkla ve yaz (0.9.15+)

Tablo veya form, uygulamanın kopyalama/erişilebilirlik desteğinden bağımsız olarak ekranda görünen metinle hedeflenir.

1. **Pencereyi tanı** ile pencereyi tanıtın ve **Metni bul, tıkla ve yaz** ekleyin.
2. **Bölge çiz** ile pencere görüntüsünde aranacak alanı seçin (ör. yalnız tablo). Alan pencereye göre saklanır; boş bırakılırsa pencerenin tamamında aranır.
3. **Nereye tıklansın?**
   - **Bulunan metnin üzerine:** **Aranacak metin** alanda bulunur ve merkezine tıklanır.
   - **Sütun ve satır kesişimine:** **Sütun metni** (ör. `Miktar` başlığı) ile **Satır metni** (aynı satırda başka bir sütundaki değer, ör. kayıt kodu `${row.kod}`) bulunur; başlığın altına, o satırın hizasına tıklanır. Hücre boş olabilir.
4. **Yazılacak değer**, gerekirse **Çift tık** (hücreyi düzenlemeye açar), **Önce mevcut değeri temizle** ve **Yazdıktan sonra** Tab/Enter seçin.
5. **Bu adımı test et → Yeri göster** ile noktayı kontrol edin, sonra **Gerçekten çalıştır**.

Konum her çalışmada yeni bir ekran görüntüsünden ölçülür; ekran ölçeği, pencere boyutu veya sütun genişliği değişse de kaydedilmiş koordinat kullanılmaz. Büyük/küçük harf fark etmez; sütun başlığında OCR'ın İ/ı/l karışıklığı tolere edilir, satır metni birebir eşleşmelidir.

Şu durumlarda tıklanmaz ve yazılmaz: metin alanda okunamazsa, alanda birden fazla yerde görünürse (alanı daraltın; ör. `Miktar` başlığı `Onaylanan Miktar` içinde de geçer), satır metni başlığın üstündeyse veya yazılacak sütunun içindeyse, pencere/odak değişirse. Satır kaydırılıp görünmez olduysa önce kaydırın. **Önce mevcut değeri temizle** tümünü seçip siler; yalnız tıklama bir yazı alanını veya hücre düzenlemesini açıyorsa kullanın. Yazma sonrası tablo doğrulaması yapılmaz; kaydetme/onayı ayrıca ekleyin, gerekirse **Ekrandan metin oku** ile sonucu kontrol edin.

Bu adımı kullanan akışlar 0.9.15 veya üzeri gerektirir; eski sürümler bilinmeyen adım türünü açmaz.

## Metin okunacak bölgeyi çizme

**Ekrandan metin oku (OCR)** ve bölge destekleyen ekran adımlarında **Bölge çiz** seçin. Ekran görüntüsünü alın, fareyi basılı tutarak bir dikdörtgen çizin, **Bölgeyi kaydet** deyin. **Seçimi temizle** ile yeniden çizebilir, Escape ile değişikliği iptal edebilirsiniz. Görüntü küçültülmüş gösterilse bile gerçek piksel koordinatları kaydedilir.

**Pencereye göre** seçiliyse önceki **Pencereyi tanı** adımındaki pencerenin görüntüsü kullanılır ve bölge pencere içinde kaydedilir. **Ekrana göre** seçim ana ekran koordinatlarını kullanır. Köşeleri ayrı ayrı üç saniye bekleyerek seçmeye gerek yoktur.
