# Akış oluşturma ve çalıştırma

Bir akış ad, açıklama, departman ve sıralı adımlardan oluşur. Her adımın bir işlem türü ve parametreleri vardır. Koşul ve döngü adımları alt adımlar içerir. Studio, Python kodu yazmadan bu yapıyı düzenlemek için kullanılır.

## Tasarım düzeni

Önce küçük bir akış oluşturun: örnek veri → günlük → CSV. Ardından veri kaynağını gerçek veritabanı veya Sheets okumasıyla değiştirin. ERP tıklamaları ve OCR koşullarını sonradan eklemek, veri ve ekran sorunlarını birbirinden ayırarak doğrulamayı kolaylaştırır.

Kaydettiğiniz akış yerel veri klasörüne yazılır. Çalıştırılan sürümle sonradan yaptığınız düzenlemeleri karıştırmamak için her değişiklikten sonra kaydedip yeni bir çalışma başlatın. Farklı bilgisayara taşımak için JSON dışa aktarın ve diğer Studio'da içe aktarın. Hedef bilgisayarın bağlantıları, şablonları ve ekran ayarları ayrıca hazırlanmalıdır.

Harici bağlantı gerektirmeyen küçük bir JSON örneği:

```json
{
  "name": "Örnek departman raporu",
  "description": "Yerel örnek siparişlerden CSV üretir.",
  "department": "Finans",
  "steps": [
    {
      "action": "data.sample",
      "title": "Örnek veriyi hazırla",
      "params": {"output": "orders"}
    },
    {
      "action": "data.export_csv",
      "title": "Raporu oluştur",
      "params": {"rows": "${orders}", "filename": "siparis-raporu.csv"}
    }
  ]
}
```

Bir `.json` dosyasına kaydedip içe aktarabilirsiniz. Studio'nun kendi dışa aktarımı ayrıca akış ve adım kimlikleri gibi alanlar içerebilir.

## Değişkenler

Veri üreten adımın `output` parametresi sonucu saklayacağı değişken adını belirler. Örneğin `orders` çıktısı sonraki adımlarda kullanılabilir:

| Değer | Anlamı |
| --- | --- |
| `${orders}` | Veri kaynağının ürettiği listenin kendisi |
| `${item.MATERIAL}` | Döngüdeki mevcut kaydın `MATERIAL` alanı |
| `Malzeme: ${item.MATERIAL}` | Sabit metin içine yerleştirilmiş alan değeri |

Tüm parametre tek bir değişken referansıysa liste, sayı veya nesne tipi korunur. Metnin içinde kullanılan referans metne dönüştürülür. Alan adları gerçek verideki büyük/küçük harflerle eşleşmelidir. Şablonlar Python veya JavaScript kodu çalıştırmaz; `eval` kullanılmaz.

## Döngü ve koşul

`control.for_each` adımında `items` alanına `${orders}` gibi bir liste verin. `item_name` mevcut kaydın adıdır; varsayılan `item` olur. Döngünün `children` alanındaki adımlar her kayıt için sırayla çalışır.

`control.if` adımı `left`, `operator` ve `right` alanlarını değerlendirir. Sonuç doğruysa `children`, yanlışsa `otherwise` adımları çalışır. Operatörü Studio'daki desteklenen seçeneklerden seçin. Koşullar döngü içinde kullanılabilir; veri alanının eksik olması gerçek çalıştırmada sessizce başarılı sayılmaz.

Operatörler: `eq` (eşit), `ne` (eşit değil), `contains` (harf duyarsız metin içerir), `gt` / `gte` (büyük / büyük veya eşit), `lt` / `lte` (küçük / küçük veya eşit), `truthy` (dolu/doğru). Sayısal karşılaştırmada sağ değeri JSON sayısı olarak, örneğin `1000` yazın; `"1000"` bir metindir.

Akış yapısı en fazla 200 adım ve 8 iç içe seviye kabul eder. Bir döngü en fazla 1.000 öğe, bir çalışma toplam en fazla 10.000 adım yürütür. Aynı akış içindeki adım kimlikleri benzersizdir. JSON'u elle düzenlediğinizde yapı sınırları da doğrulanır.

## ERP dropdown akışı

Bilinen bir değer listesi varsa doğrudan o liste üzerinde döngü kurun. Liste yalnız ekranda görünüyorsa dropdown OCR taramasıyla seçenekleri toplayın, sonucunu bir çıktı değişkenine bağlayın ve sonra döngüye verin. Tarama bölgesi yalnız seçeneklerin bulunduğu alanı kapsamalıdır.

Her değer için tipik sıra:

1. Dropdown'u açıp değeri seçin veya arama alanına yazın.
2. Arama düğmesine tıklayın; beklenen sonucu zaman aşımıyla bekleyin.
3. OCR veya şablon kontrolüyle hata/uyarı durumunu okuyun.
4. Koşul doğruysa beklenen işlem adımlarını çalıştırın; değilse açıklayıcı günlük ekleyin veya akışı durdurun.
5. Sonucu rapor için hazırlayın.

Studio'daki `desktop.scan_dropdown` adımı **önceden açılmış** listeyi tarar; hemen öncesine listeyi açan tıklama adımı koyun. Bir seçeneği seçmek listeyi kapatıyorsa her döngüde yeniden açılması gerekir. Koordinatlar ve ekran bölgeleri mantıksal ekran koordinatlarıdır; bölge biçimi `[x, y, genişlik, yükseklik]` olur.

OCR taraması tekrarları azaltır ve kaydırma sınırıyla sonlanır; bütün özel ERP bileşenlerinde eksiksiz liste çıkarma garantisi vermez. Sanallaştırılmış listelerde aynı görünen etiketin farklı kayıtlara ait olması gibi durumlar için ERP'ye özgü doğrulama gerekir. Sabit çözünürlük ve şablonlar ilk gerçek kullanımda kalibre edilmelidir.

## Uyarı pencereleri ve kararlar

OCR metnini bir çıktı değişkenine alın ve beklenen metne göre koşul oluşturun. Örneğin hata metnini içeren bir sonuç farklı kola, bilinen bir onay penceresi onay koluna gidebilir. Onay işlemini yalnız beklenen pencereyle eşleştirin; tanınmayan pencereyi otomatik onaylamak yerine hata kaydı ve inceleme adımı kullanın.

Görsel şablon eşleştirme metin okumadan pencereyi tespit edebilir. OCR ise o penceredeki içeriği karar için sağlar. Küçük yazı veya yanlış tarama bölgesi hatalı karar üretebileceğinden gerçek akışı önce az sayıda test kaydıyla çalıştırın.

## Önizleme

Önizleme (`dry_run`) veritabanı, masaüstü, OCR, web ve Sheets gibi dış işlemleri atlar. Atlanan adımlar çalışma günlüğünde görünür. Örnek veri, değişken atama, koşul ve döngü gibi çekirdek işlemler mümkün olduğunda değerlendirilir; yalnız yerel örnek veriden CSV üretilebilir.

Atlanan veri kaynağının sonucu **bilinmeyen** olarak taşınır. Bu veriye bağlı döngü ve koşul değerlendirilmez; önizleme gerçek dış veri okumuş gibi rapor üretmez. Gerçek veri türlerini ve bağlantıların çalışmasını doğrulamak için daha sonra gerçek çalıştırma gerekir.

Önizleme, örnek verinin kullandığı dalı gösterir. Diğer dalları da incelemek için örnek girdileri değiştirip ayrı çalıştırmalar yapın. Önizlemenin başarılı olması tüm olası ERP ekranlarının veya iş kurallarının doğrulandığı anlamına gelmez.

## Çalışma geçmişi ve iptal

Çalışma durumu kuyrukta, çalışıyor, başarılı, başarısız veya iptal edilmiş olabilir. Adım günlükleri ve üretilen dosyalar çalışma kaydında tutulur. Uygulama kapanırken yarım kalan çalışma, sonraki açılışta kesilmiş olarak işaretlenir; kaldığı yerden otomatik devam etmez.

İptal isteği işbirliklidir: motor adımlar arasında ve desteklenen beklemelerde isteği denetler. Devam eden veritabanı veya tarayıcı çağrısı kendi zaman aşımına kadar sürebilir. Yapılmış bir ERP kaydı veya Sheets yazması geri alınmaz. Tekrar çalıştırmadan önce dış sistemde önceki işlemin tamamlanıp tamamlanmadığını kontrol edin.

## Departmana çıktı verme

`data.export_csv` adımında `rows` alanına rapor listesi, `filename` alanına `siparis-raporu.csv` gibi bir ad verin. Çalışma tamamlandığında çıktıyı Studio'dan indirin ve departmana kendi paylaşım kanalınızla iletin. Uygulama raporu otomatik e-posta göndermez.

Departman etiketi raporu sınıflandırır. Bu sürümde departmanların ayrı oturumları veya rapor erişim izinleri yoktur. İçe/dışa aktarılan akış, kurulumdaki bağlantı ayarlarını taşımaz; adımların içine yazılmış sabit iş verilerini taşıyabilir.

## Sık kullanılan işlem alanları

| İşlem | Temel parametreler |
| --- | --- |
| `database.read` | `table`: `dbo.IASSALITEM`; `columns`: sütun listesi veya `null`; `filters`: alan/değer nesnesi; `limit`; `output` |
| `desktop.click_template` | `template`: şablon klasöründeki dosya; `region`: bölge veya `null`; `confidence`: eşik |
| `desktop.hotkey` | `keys`: `["mod", "a"]`; `mod`, Mac'te Command, Windows'ta Ctrl olur |
| `desktop.ocr` | `region`; `output`: örneğin `screen_text` |
| `browser.open` | `url`: açılacak sayfa |
| `browser.fill` | `selector`: CSS/Playwright seçicisi; `value`: yazılacak değer |
| `browser.text` | `selector`; `output` |
| `sheets.read` | `spreadsheet_id`; `worksheet`; `range`: örneğin `A1:C10`; `output` |
| `sheets.write` | `spreadsheet_id`; `worksheet`; `range`; `values`: `[["Başlık", "Değer"], ["Toplam", 42]]` gibi satır matrisi |
| `data.append` | `name`: liste değişkeni; `value`: eklenecek kayıt |

JSON türündeki Studio alanlarında değişken referansını doğrudan `${orders}` biçiminde yazabilirsiniz; `"${orders}"` da kabul edilir. Sabit metni çift tırnak içinde, nesne veya listeyi doğrudan JSON olarak yazın: `"Merhaba"`, `{"COMPANY": "01"}`, `["MATERIAL", "QUANTITY"]`. Sheets okuması satır matrisi döndürür; veritabanı okuması sütun adlarıyla erişilebilen kayıtlar üretir. İkisinin sonraki adımlarda aynı şekle sahip olduğunu varsaymayın.
