# Sheets satırları, durum koşulları ve ERP işlemleri

0.4.0'da **Sheets satırlarını oku** adımı, FormID ve durum gibi sütunları aynı kayıtta okur. **Her satır için** döngüsüne **Koşul** ekleyerek yalnız durumu boş veya `Bekliyor` olan kayıtları işleyebilirsiniz. Koşulun dallarına başka koşullar ve döngüler de eklenebilir.

## Bağlantıyı ve ERP hedefini hazırlayın

**Bağlantılar ve ayarlar** bölümünde Google servis hesabının JSON dosyasını seçin/yolunu tanımlayın. Google Sheets tablosunu servis hesabının e-posta adresiyle paylaşın. Okuma için görüntüleme; sonuçları tabloya yazmak için düzenleme izni gerekir. Servis hesabı dosyası çalışmanın yapıldığı bilgisayarda bulunmalıdır.

**Google Sheets adresi veya kimliği** alanına tablonun tam `https://docs.google.com/spreadsheets/d/.../edit` bağlantısını yapıştırabilirsiniz. Yalnız tablo kimliği de kabul edilir. **Sayfa adı**, alt sekmenin tam adıdır; örneğin `Sayfa1`.

ERP'de FormID alanının bulunduğu ekranı açın. [Pencere ve hedef seçimi rehberine](pencere-tanitma.md) göre pencereyi tanıtın ve alanı fareyle seçin.

## B sütunundaki FormID'yi C sütunundaki duruma göre işle

| Sıra | Adım | Ayarlar |
| --- | --- | --- |
| 1 | **Pencereyi tanı** | ERP penceresi; çıktı `erp_window`; bulunamazsa **Akışı durdur**. |
| 2 | **Sheets satırlarını oku** | Tablo adresi, `Sayfa1`, başlangıç satırı `2`, ilk denemede azami satır `1`. |
| 2 — sütun ayarları | **Okunacak sütunlar** | `B → form_id`, `C → status`; ana alan `form_id`; çıktı `sheet_rows`. |
| 3 | **Her satır için** | Satır listesi `${sheet_rows}`; geçerli satır değişkeni `row`. |
| 3.1 — döngünün içinde | **Koşul** | Sol değer `${row.status}`; karşılaştırma **Boş veya eşittir**; sağ değer `Bekliyor`. |
| 3.1.1 — Evet dalında | **Alanı doldur** | Pencere `${erp_window}`; seçtiğiniz FormID hedefi; metin `${row.form_id}`; mevcut değeri temizleme açık. |
| 3.2 — Değilse dalı | Boş bırakın | Örneğin `Tamamlandı` olan kaydı atlar ve sonraki satıra geçer. |

Sütun eşleştirmelerini arayüzdeki satırlarla düzenleyin; JSON yazmanız gerekmez. Alan adları harf, rakam ve alt çizgi kullanır; boşluk içermez. `row_number` fiziksel satır numarası için ayrılmıştır. Aynı sütunu iki farklı alana eşleştirmeyin.

Örneğin tablo şöyle olsun:

| Sheets satırı | B: FormID | C: durum | Koşulun sonucu |
| --- | --- | --- | --- |
| 2 | `000142` | boş | ERP adımları çalışır. |
| 3 | `000143` | `Tamamlandı` | Atlanır. |
| 4 | `000144` | `Bekliyor` | ERP adımları çalışır. |

`${row.form_id}` FormID'yi, `${row.status}` aynı kaydın durumunu, `${row.row_number}` gerçek Sheets satır numarasını verir. Baştaki sıfırlar Sheets'te görüntülendiği biçimde korunur. Hücre Sheets'te zaten `142` görünüyorsa uygulama kendiliğinden `000142` üretmez.

**Alanı doldur** adımını ana akışın sonuna değil, döngüdeki koşulun **Evet** dalına ekleyin. Yalnız alan doldurulan örnekte son işlenen satırın değeri ekranda kalır. Arama veya başka ERP işlemleri yapılacaksa o adımları da aynı dala ekleyin.

## Boş değerler ve karşılaştırmalar

- **Boş:** değer yoksa, boş metinse veya yalnız boşluk içeriyorsa doğrudur. `0` ve `false` boş sayılmaz.
- **Boş değil:** yukarıdaki kontrolün tersidir.
- **Boş veya eşittir:** boş değerleri ve sağdaki değere tam eşit olanları seçer. `Bekliyor` ile `bekliyor` farklıdır.
- **Listedeki değerlerden biri:** sağdaki listedeki tam değerlerden birine eşitliği denetler; kısmi metin eşleşmesi yapmaz.
- **İçerir (harf duyarsız):** metnin bir bölümünü harf büyüklüğünü ayırt etmeden arar.

**Sheets hücresini oku** adımındaki **Boş hücreyi hata vermeden oku** seçeneği açıkken boş hücre boş metin olur. Sonrasında **Koşul → Boş** ile karar verebilirsiniz. Seçenek kapalıysa önceki sürümlerde olduğu gibi boş hücrede hata verilir.

Tablo okuma adımında yalnız **ana alan** satırın varlığını belirler. `form_id` dolu olduğu sürece `status` boş olan kayıt korunur. Ana alan boşsa:

- **Okumayı bitir:** ilk boş ana alanda okuma sona erer.
- **Satırı atla, devam et:** okuma sınırı içindeki boş ana alanlı satırlar atlanır. Fiziksel satır numaraları değişmez.

Azami satır **1–1000 fiziksel satır**dır. Başlangıç 2, sınır 100 ve sütunlar B/C ise **B2:C101** okunur. Boşları atlamak aralığı aşağı doğru uzatmaz. 1–32 farklı alan eşleştirilebilir; seçili sütunların ilkinden sonuncusuna uzaklığı en fazla 64 sütun olabilir.

Liste çalışma başında bir kez okunur. Çalışma sırasında Sheets'te yapılan değişiklikler mevcut listeyi değiştirmez. Her yeni çalıştırma başlangıç satırından tekrar okur; durum koşulu yeni okunan `Tamamlandı` kayıtlarını atlar. Bu davranış otomatik kaldığı yerden devam etme veya birden fazla bilgisayar arasında kayıt kilitleme değildir.

## Koşul sürdükçe tekrar et

**Her satır için**, bir listedeki kayıtları dolaşır. **Koşul sürdükçe tekrarla**, karşılaştırmayı her turdan önce yeniden değerlendirir ve doğru kaldığı sürece içindeki adımları çalıştırır.

Örneğin bir hücrenin `Tamamlandı` olmasını sınırlı süre boyunca kontrol etmek için:

1. **Sheets hücresini oku** ile ilk değeri `status` değişkenine alın; boş hücreye izin verin.
2. **Koşul sürdükçe tekrarla** ekleyin: sol `${status}`, karşılaştırma **Eşit değildir**, sağ `Tamamlandı`.
3. İçine **Bekle** ve ardından aynı hücreyi tekrar `status` değişkenine okuyan adımı ekleyin.
4. **En fazla tekrar** ve **Toplam süre sınırı** belirleyin.

Sütun okuma listesindeki eski değeri tekrar karşılaştırmak dışarıdaki değişikliği okumaz; bu nedenle örnekte hücre döngünün içinde yeniden okunur. Koşul ilk kontrolde yanlışsa içerideki adımlar hiç çalışmaz.

Tekrar sınırı **1–1000**, süre sınırı **1–3600 saniye**dir. Sınıra ulaşıldığında koşul hâlâ doğruysa akış hata ile durur. Süre adımlar arasında kontrol edilir; devam eden tek bir ağ/ERP işlemini anında kesmez. İç işlemlerin kendi zaman aşımı değerlerini de uygun ayarlayın. **Durdur** komutu yeni bir tura veya sonraki adıma geçilmesini engeller.

Koşulları ve döngüleri iç içe yerleştirebilirsiniz. `${loop_index}` içinde bulunulan döngünün sıfırdan başlayan sayacıdır; iç döngü bittiğinde dış döngünün sayacı geri gelir.

## ERP işlemini doğruladıktan sonra sonuç yaz

**Pencerede tuşa bas**, FormID doldurulduktan sonra Enter veya Tab gönderebilir. ERP'nizde bu tuşun işlevini doğrulayın. **Pencerede tıkla** ayrıca basılacak arama butonu gibi bir öğe içindir; **Alanı doldur** zaten kendi hedefine tıklar.

**Pencerede görseli bekle**, beklenen ekranın veya sonucun hazır olmasını kontrol eder. Gerekiyorsa yükleniyor işaretinin kaybolmasını ve ardından beklenen sonucun görünmesini bekleyin. Önceki kayıttan kalan, zaten görünür bir işaret yeni kaydın başarıyla işlendiğini tek başına kanıtlamaz.

Doğrulanmış sonucu aynı satıra yazmak için koşulun **Evet** dalının sonuna **Sheets hücresine yaz** ekleyin:

- Tablo ve sayfa: okuma adımındaki tablo ve sayfa.
- Hücre: `C${row.row_number}`.
- Değer: `Tamamlandı`.

Yalnız FormID alanının dolması faturanın işlendiği anlamına gelmez. Bu yazma adımı ERP'deki başarıyı doğrulayan adımlardan sonra gelmelidir. Doğrulama hata verirse akış durur ve sonraki sonuç yazma adımı çalışmaz. Yazılan değer metindir; formül çalıştırılmaz.

## İlk doğrulama ve eski akışlar

[sheets-pending-formids.json](../examples/sheets-pending-formids.json) yeni koşullu düzeni içerir. Tablo kimliğini ve ERP başlığını değiştirin; FormID hedefini fareyle belirleyin. Hedef koordinatları bilerek boştur; hedef seçilmeden deneme modu da çalıştırma doğrulamasını geçmez. Örnek **1 fiziksel satır** okur, yalnız alan doldurur; Enter, fatura kaydı veya sonuç yazma işlemi içermez.

Deneme modu Sheets'e bağlanmaz veya ERP'ye yazmaz; gerçek kayıtları ve görsel eşleşmesini sınamaz. İlk gerçek doğrulamayı azami satır 1 ile yapın. FormID hedefini doğruladıktan sonra satır sınırını artırıp ERP'ye özgü işlemleri ekleyin.

Eski **Sheets sütununu oku** adımı ve [sheets-formid-loop.json](../examples/sheets-formid-loop.json) çalışmaya devam eder. Bu adımın çıktısı `${row.value}`, `${row.cell}`, `${row.row_number}` alanlarıdır. Yeni kütüphanede çok sütunlu **Sheets satırlarını oku** kullanılır; mevcut akışlar ve değişken adları kendiliğinden dönüştürülmez.

Akış biçimi Windows ve macOS'ta aynıdır. Pencere başlığı, izinler, ekran ölçeği ve görsel hedefler her bilgisayarda doğrulanmalıdır.
