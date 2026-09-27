# ERP penceresini ve alanını tanıtma

Bu rehber 0.3.0 için geliştirilen pencere ve satır döngüsü adımlarını anlatır. İade faturası ilk örnektir; aynı adımlar başka masaüstü uygulamalarında da kullanılabilir. Sheets'teki B2, B3, B4 değerlerini sırayla işlemek için [satır döngüsü rehberini](sheets-satir-dongusu.md) kullanın.

## Pencereyi tanı

1. ERP uygulamasını açın ve ilgili pencereyi görünür hale getirin. Küçültülmüş veya başka masaüstündeki pencereler listelenmez.
2. Studio'da akışınıza **Pencereyi tanı** ekleyin.
3. Sağ panelde **Açık pencerelerden seç** düğmesine basıp ERP penceresini seçin. Uygulama adı ve başlığı doldurulur.
4. **Şimdi kontrol et** ile eşleşmeyi doğrulayın. Bu düğme pencere bilgilerini okur; tıklama veya yazma yapmaz.
5. Başlık belge numarası gibi değişken bilgi içeriyorsa sabit kısmını yazıp **İçerir** seçin. Uygulama adı tam eşleşir. Birden fazla pencere eşleşirse daha belirgin başlık kullanın.
6. Akışı kaydedin. Pencere her çalıştırmada yeniden bulunur; geçici pencere kimliği akış dosyasına kaydedilmez.

Varsayılan çıktı `erp_window` olur. `${erp_window.found}` pencerenin bulunup bulunmadığını, `${erp_window}` ise sonraki pencere adımlarına verilecek pencere bilgisini taşır. Bulunan sonuç ayrıca `title`, `application`, `x`, `y`, `width`, `height` alanlarını içerir. Bulunamayan sonuç yalnız `found: false` içerir.

Varsayılan olarak pencere 5 saniye beklenir; bulunamazsa akış durur. Alternatif olarak **Bulunamadı sonucu ile devam et** seçip sonraki **Koşul** adımında `${erp_window.found}` değerini **Dolu / doğru** ile değerlendirin. ERP işlemlerini koşulun Evet dalına yerleştirin.

Pencere tanıma uygulama adı ve başlığını denetler. Aynı başlık altında birden fazla form açılabiliyorsa doğru formun hazır olduğunu **Pencerede görseli bekle** adımıyla ayrıca kontrol edin.

## FormID alanına değer yaz

**Alanı doldur**, hedef alanı bulur, tıklar ve değeri yazar. Bu işlem için ayrıca **Pencerede tıkla** eklemek gerekmez.

- **Pencere değişkeni:** `${erp_window}`.
- **Yazılacak değer:** tek hücre okuduysanız `${cell_value}`, satır döngüsündeyseniz `${row.value}`.
- **Önce alandaki mevcut değeri temizle:** açık bırakın. Önceki satırın değeri temizlenip yenisi yazılır; kapatırsanız mevcut değere ekleme yapılır.

### Pencere içi X / Y

**Hedefi bulma yöntemi** olarak **Pencere içi X / Y** seçin. **ERP ekranından hedef seç** düğmesine basın. Açılan pencere görüntüsünde FormID yazı kutusunun içine tıklayıp **Hedefi kaydet** seçin; X/Y değerleri doldurulur. X/Y'yi elle de girebilirsiniz. Seçmeniz gereken yer `FormID` etiketi değil, yanındaki yazı kutusudur.

Koordinatlar başlık çubuğu dahil pencerenin sol üst köşesine göredir. Pencere taşınırsa yeni konumu kullanılır. Pencere boyutu, uygulama düzeni, tema veya ekran ölçeği değişirse hedefi yeniden seçin. ERP penceresini ana ekranda ve tamamen görünür tutun.

### Referans görsel

**ERP ekranından hedef seç** düğmesine basıp açılan araçta **Görsel referans** seçin. Hedefi iki aşamada belirleyin:

1. Pencere görüntüsünde **FormID etiketini ve hemen çevresini** kapsayan küçük bir dikdörtgen çizin.
2. Ardından değerin yazılacağı **yazı kutusunun içine tıklayın** ve **Hedefi kaydet** seçin. Yazı kutusu çizdiğiniz referansın dışında olabilir.

Referans görsel kaydedilir; görselin merkezi ile seçtiğiniz yazı kutusu arasındaki X/Y farkı otomatik hesaplanır. Gerekirse **Görsel merkezinden sağa / sola** ve **aşağı / yukarı** değerlerini sonradan elle düzeltebilirsiniz. **Pencerede görseli bekle** adımında yalnız referans dikdörtgeni seçilir; tıklanacak alan gerekmez.

Kutunun içindeki değişen fatura/form numarasını referansa dahil etmeyin; sonraki satırda bu içerik değişecektir. Aynı etiket birden fazla yerde görünüyorsa çevresindeki sabit ayrıntıları da seçerek hedefi ayırt edin.

Arama yalnız tanıtılan pencerenin içinde yapılır. Görsel süre içinde bulunamazsa işlem durur. Eşleşme eşiği varsayılan olarak `0.9`'dur. Tema, ölçek veya yazı tipi değişirse referansı yeniden alın; yalnızca eşiği düşürmek benzer bir öğenin seçilmesine yol açabilir.

## Tıklama, doldurma ve tuş adımlarının farkı

| Adım | Görevi |
| --- | --- |
| **Pencerede tıkla** | Hedef butona/öğeye tek, çift veya sağ tık yapar; metin yazmaz. |
| **Alanı doldur** | Hedef yazı alanına tıklar, istenirse içeriğini temizler, değeri yazar. |
| **Pencerede tuşa bas** | Tanıtılan pencereye Enter, Tab veya bir kısayol gönderir; hedef alan aramaz. |
| **Pencerede görseli bekle** | Bir işaretin görünmesini ya da kaybolmasını bekler; fare/klavye işlemi yapmaz. |
| **Bekle** | Sabit süre bekler; ekranın hazır olduğunu doğrulamaz. |

Eski akışlardaki **Pencereye metin yaz** adımı **Odaktaki alana yaz (eski)** adıyla düzenlenebilir. Bu adım yalnız odaktaki alana ekleme yapar. Yeni kütüphanede alanı açıkça seçen **Alanı doldur** kullanılır; mevcut akışların davranışı sessizce değiştirilmez.

Her giriş adımı hedef pencereyi öne getirip odağı doğrular. Pencere kapanır, seçiciyle eşleşmez veya odak doğrulanamazsa işlem durur. Başlığı değişen bir ekrana geçtikten sonra yeniden **Pencereyi tanı** ekleyin. Akış çalışırken fare ve klavyeyi başka işler için kullanmayın.

## macOS ve Windows

- Kurulum paketleri gerekli Python otomasyon bağımlılıklarını içerir. Kaynak koddan çalıştırırken `.[automation]` bağımlılıkları kurulmalıdır.
- **macOS:** pencere başlıkları ve ekran görüntüleri için Ekran Kaydı; pencereyi öne getirme ve giriş için Erişilebilirlik / Otomasyon izinleri gerekir. Kurulu uygulamada izinleri **RpaOrkestrAI** için verin. Kaynak koddan çalıştırıyorsanız başlatan Python/Terminal için izin gerekebilir. İzin değişikliğinden sonra uygulamayı yeniden açın.
- **Windows:** pencere listeleme Windows API'sini kullanır. ERP farklı bir oturumda veya yükseltilmiş yetkiyle çalışıyorsa giriş engellenebilir. Odağın doğrulanamadığı durumda adım durur.
- Temizleme kısayolu Windows'ta **Ctrl+A**, macOS'ta **Command+A** kullanır. İki işletim sisteminde ERP uygulama adı, pencere başlığı, görünüm veya koordinatlar farklıysa hedefleri o bilgisayarda yeniden seçin.

**Deneme modu**, akış parametrelerini kontrol eder; hedefi henüz seçilmemiş bir alan için yapılandırma ister. Pencere aramaz, Sheets'e bağlanmaz ve fare/klavye kullanmaz. Harici veri gerçek olmadığı için satır döngüsünün gerçek sonuçlarını göstermez. **ERP ekranından hedef seç** ve **Şimdi kontrol et** tasarım araçlarıdır; bunları ayrıca kullanarak hedefi belirleyin. Gerçek çalışmayı önce tek satır ve onay/kayıt işlemi içermeyen bir örnekle doğrulayın.

Kütüphanedeki adımları yıldızlayarak **Sık kullanılanlar** bölümüne taşıyabilirsiniz.
