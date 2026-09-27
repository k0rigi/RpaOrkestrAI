# Sheets B2, B3, B4 değerlerini ERP'de sırayla kullanma

Bu akış 0.3.0 için geliştirilen adımları kullanır. **Sheets sütununu oku**, B2'den başlayan değerleri bir kez listeye alır. **Her satır için**, bu listedeki her değer için kendi içine eklediğiniz ERP adımlarını çalıştırır. B3 ve B4 için ayrı okuma adımı eklemeniz veya hücreyi elle artırmanız gerekmez.

## Önce bağlantıyı ve ERP hedefini hazırlayın

**Bağlantılar ve ayarlar** bölümünde Google servis hesabının JSON dosyasını seçin/yolunu tanımlayın. Google Sheets tablosunu servis hesabının e-posta adresiyle paylaşın. Okuma için görüntüleme; sonuçları tabloya yazmak için düzenleme izni gerekir. Servis hesabı dosyası çalışmanın yapıldığı bilgisayarda bulunmalıdır.

**Google Sheets adresi veya kimliği** alanına tablonun tam `https://docs.google.com/spreadsheets/d/.../edit` bağlantısını yapıştırabilirsiniz. Yalnız tablo kimliği de kabul edilir. **Sayfa adı**, alt sekmenin tam adıdır; örneğin `Sayfa1`.

ERP'de FormID alanının bulunduğu ekranı açın. [Pencere ve hedef seçimi rehberine](pencere-tanitma.md) göre pencereyi tanıtın ve alanı seçin.

## Akışı kurun

| Sıra | Adım | Ayarlar |
| --- | --- | --- |
| 1 | **Pencereyi tanı** | ERP penceresini seçin; çıktı `erp_window`; bulunamazsa **Akışı durdur**. |
| 2 | **Sheets sütununu oku** | Tablo adresi, `Sayfa1`, başlangıç `B2`, azami satır `100`, boş hücrede **Okumayı bitir**, çıktı `sheet_rows`. |
| 3 | **Her satır için** | Satır listesi `${sheet_rows}`, geçerli satır değişkeni `row`. |
| 3.1 | **Alanı doldur** — döngünün içinde | Pencere `${erp_window}`, seçtiğiniz FormID hedefi, yazılacak değer `${row.value}`, mevcut değeri temizleme açık. |

**Alanı doldur** adımını ana akışın sonuna değil, **Her satır için** kutusunun içine ekleyin. Yalnızca alan doldurulan ilk örnekte döngü sonunda son satırın değeri görünür; her satır için arama veya başka işlem yapılacaksa o adımları da döngünün içine ekleyin.

Örneğin B2=`000142`, B3=`000143`, B4=`000144` ise FormID alanına sırayla bu değerler yazılır. Baştaki sıfırlar Sheets'te görüntülendiği biçimde korunur. Hücre Sheets'te zaten `142` görünüyorsa uygulama kendiliğinden `000142` üretmez; sütunun biçimini Sheets'te ayarlayın.

| Değişken | İlk turda | Sonraki turda |
| --- | --- | --- |
| `${row.value}` | `000142` | `000143` |
| `${row.cell}` | `B2` | `B3` |
| `${row.row_number}` | `2` | `3` |

### Boş hücreler ve okuma sınırı

- **Okumayı bitir:** ilk boş hücrede liste sona erer. B3 boşsa B2 işlenir; B4 işlenmez.
- **Atla ve devam et:** okuma sınırı içindeki boş hücreler atlanır. B3 boşsa B2'den sonra B4 işlenir; B4'ün `row_number` değeri yine `4` olur.
- Yalnız boşluk içeren hücreler boş sayılır. `0` değeri boş değildir ve işlenir.
- Varsayılan sınır **100**, izin verilen sınır **1–1000 fiziksel satır**dır. B2'den 100 satır, **B2:B101** aralığı demektir. Boş satırları atlamak bu aralığı aşağı doğru uzatmaz.
- Liste akış başında bir kez okunur. Çalışma sırasında Sheets'te yapılan değişiklikler mevcut listeyi değiştirmez. Döngü liste bittiğinde sona erer.
- Her yeni çalıştırma tekrar B2'den başlar. Otomatik kaldığı yerden devam etme veya daha önce işlendi işaretlerini kendiliğinden atlama yoktur. C sütununa sonuç yazılması tek başına sonraki çalıştırmada tekrar işlemeyi engellemez.

## Döngüye gerektiğinde eklenebilecek işlemler

**Pencerede tuşa bas**, alan doldurulduktan sonra Enter veya Tab gönderebilir. ERP'nizde bu tuşun işlevini doğrulayın. Örnek dosya Enter, kaydet veya fatura onaylama işlemi içermez.

**Pencerede görseli bekle**, sonraki işleme geçmeden önce doğru ekranın veya sonucun hazır olmasını kontrol eder. Yükleniyor işaretinin kaybolmasını, ardından beklenen sonuç işaretinin görünmesini bekletebilirsiniz. Önceki kayıttan kalan ve zaten görünür olan bir işaret yeni kaydın başarılı işlendiğini kanıtlamaz; işaretin ilgili işleme ait olduğunu ve beklenen geçişi doğrulayın.

**Pencerede tıkla**, ayrıca basılması gereken arama butonu gibi bir öğe içindir. **Alanı doldur** zaten kendi hedef alanına tıkladığından aynı hedef için ikinci tıklama adımı gerekmez.

**Sheets hücresine yaz** ile doğrulanmış sonucu aynı satıra kaydedebilirsiniz:

- Tablo ve sayfa: okuma adımındaki tablo ve sayfa.
- Yazılacak hücre: `C${row.row_number}`.
- Yazılacak değer: örneğin `Tamamlandı`.

Bu yazma adımını, **ERP işleminin başarıyla tamamlandığını doğrulayan adımlardan sonra**, döngünün içine koyun. Yalnız FormID alanının dolması faturanın işlendiği anlamına gelmez. Başarı doğrulaması hata verirse akış durur ve sonraki sonuç yazma adımı çalışmaz. Hücreye formül çalıştırmadan metin olarak yazılır.

## Kütüphanedeki adımların ayrı görevleri

| Adım | Kullanım amacı |
| --- | --- |
| **Pencereyi tanı** | Açık ERP penceresini bulur ve pencere değişkeni oluşturur. |
| **Pencerede tıkla** | Seçilen buton veya öğeye tıklar. |
| **Alanı doldur** | Seçilen yazı alanını bulur, gerekiyorsa temizler ve değer yazar. |
| **Pencerede tuşa bas** | Enter, Tab veya klavye kısayolu gönderir. |
| **Pencerede görseli bekle** | Görselin görünmesini ya da kaybolmasını bekler. |
| **Sheets hücresini oku** | Tek bir hücreyi bir kez okur; döngü listesi oluşturmaz. |
| **Sheets sütununu oku** | Belirlenen sütun aralığını satır bilgileriyle listeye alır. |
| **Sheets hücresine yaz** | Tek bir hücreye sonuç veya başka bir değer yazar. |
| **Her satır için** | Listedeki her satırda kendi içindeki adımları tekrarlar. |
| **Bekle** | Belirli süre bekler; ekranı veya sonucu denetlemez. |
| **Koşul** | Bir karşılaştırmanın sonucuna göre Evet veya Değilse dalını çalıştırır. |

## Örnek dosya ve ilk doğrulama

[sheets-formid-loop.json](../examples/sheets-formid-loop.json) bu temel düzeni içerir. Tablo kimliği ve ERP başlığı örnektir; FormID koordinatları bilerek boş bırakılmıştır. Önce kendi tablonuzu, pencerenizi ve hedefinizi seçin. Yapılandırılmamış hedef, deneme modunda da çalıştırma doğrulamasına takılır.

Deneme modu Sheets'e bağlanmaz veya ERP'ye yazmaz; gerçek satır değerlerini ve ekran eşleşmesini sınamaz. İlk gerçek doğrulamayı **azami satır 1** ile yapın. FormID hedefinin doğru olduğunu gördükten sonra satır sınırını artırıp ERP'ye özgü arama/sonuç kontrolü adımlarını ekleyin. Bu örnek kendi başına fatura kaydetmez, onaylamaz veya işlenmiş kabul etmez.

Akış biçimi Windows ve macOS'ta aynıdır; uygulama başlığı, izinler, ekran ölçeği ve görsel hedefler her bilgisayarda doğrulanmalıdır. Kullanıcının ERP ortamına bağlanılarak canlı işlem testi yapılmış olduğu varsayılmaz.
