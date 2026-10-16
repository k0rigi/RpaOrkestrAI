"""Short usage notes shown in the step inspector: a guide per step and a help line per field.

A guide has ``how`` (what to do, in order), and optionally ``result`` (what the step
leaves behind) and ``tip``. Field help written in the catalog wins; the tables here
fill every field that has none, first by (step, field) and then by field name.
"""

from __future__ import annotations

WINDOW_FIRST = "Önce akışın başına Pencereyi tanı ekleyin; bu adımın Pencere alanından o pencereyi seçin."
PICK_TARGET = ("Ekranda seç'e basın, geri sayım bitmeden fareyi hedefin üzerine götürün. Uygulama destekliyorsa "
               "Alan kimliği seçeneğini kullanın.")
TEST_HINT = "Bu adımı test et → Yeri göster, tıklamadan fareyi hedefe götürür."

FIELD_HELP = {
    "window": "Bu adımın çalışacağı pencere. Listede, önceki Pencereyi tanı adımlarında ad verdiğiniz pencereler "
              "görünür.",
    "target_mode": "X / Y: Ekranda seç ile alınan nokta. Referans görsel: düğme yer değiştirse de bulunur. "
                   "Alan kimliği: uygulama destekliyorsa en sağlam yöntem.",
    "x": "Ekranın sol kenarından piksel. Fare konumunu al düğmesiyle doldurun.",
    "y": "X ile birlikte, hedefi ekrandan seçtiğinizde otomatik dolar.",
    "confidence": "Görselin ne kadar benzemesi gerektiği (0,5–1). Bulunamıyorsa 0,8'e indirin; yanlış yeri "
                  "buluyorsa yükseltin.",
    "timeout": "Bu süre içinde gerçekleşmezse adım durur.",
    "offset_x": "Görselin merkezinden kaç piksel sağa (+) veya sola (−) tıklanacağı.",
    "offset_y": "Görselin merkezinden kaç piksel aşağı (+) veya yukarı (−) tıklanacağı.",
    "clicks": "Kayıt açmak gibi işlemler için Çift tık seçin.",
    "button": "Sağ tık menüsünü açmak için Sağ seçin.",
    "relative_to": "Tanıtılan pencere seçilirse bölge pencerenin sol üst köşesine göre ölçülür; pencere taşınsa "
                   "da doğru kalır.",
    "worksheet": "Tablonun altındaki sekmenin adı; birebir aynı yazın (ör. Sayfa1).",
    "output": "Sonuca vereceğiniz ad. Yalnız adı yazın; ${ } işaretleri burada yazılmaz.",
    "left": "Karşılaştırılacak değer; genellikle bir değişken (ör. ${row.durum}).",
    "operator": "Sol değerin sağ değerle nasıl karşılaştırılacağı. Eşittir büyük/küçük harfe duyarlıdır; "
                "İçerir duyarlı değildir.",
    "right": "Karşılaştırılacak sabit değer veya başka bir değişken.",
    "state": "Görsel görünene kadar mı, kaybolana kadar mı bekleneceği.",
    "on_missing": "Akışı durdur: adım hata verir. Devam et: sonuç 'bulunamadı' olur; ardından Koşul ile kontrol edin.",
    "key": "Basılacak tuş.",
    "duration": "0 anında yapar; daha yüksek değer hareketi yavaşlatır (bazı uygulamalar yavaş hareket ister).",
    "interval": "Uygulama harfleri kaçırıyorsa artırın (ör. 0,05).",
    "mode": "Üzerine yaz mevcut dosyayı siler; Sonuna ekle korur.",
    "rows": "Yazılacak kayıt listesi; genellikle Listeye ekle ile toplanan ${results}.",
    "filename": "Dosya adı; uzantısıyla birlikte yazın.",
    "folder": "Seç… ile klasörü gösterin. ${sistem.masaustu} gibi hazır değişkenler de kullanılabilir.",
    "title": "Pencerenin üstünde görünen başlık.",
    "text": "Sabit metin veya ${değişken}; ikisi birlikte de yazılabilir.",
    "value": "Sabit bir değer veya ${değişken}.",
    "name": "Harfle başlayan, boşluksuz bir ad (ör. sayac). Yalnız adı yazın; ${ } işaretleri burada yazılmaz.",
    "spreadsheet_id": "Google Sheets tablosunun tarayıcıdaki adresinin tamamını yapıştırabilirsiniz.",
    "cell": "Hücre adresi (ör. C5). Döngüde geçerli satır için C${row.row_number} yazın.",
    "max_rows": "Okunacak en fazla satır sayısı. İlk denemede 1–2 yapın.",
    "fail_on_error": "Kapalıysa hata olsa da akış sürer; sonucu Koşul ile kontrol edin.",
}

STEP_FIELD_HELP = {
    ("web.wait", "condition"): "Sabit Bekle yerine: sayfa hazır olunca hemen devam edilir.",
    ("web.wait", "by"): "Görünen metin, alan etiketi veya düğme adı çoğu sitede yeterlidir; CSS yalnız gerekirse.",
    ("web.wait", "wait"): "Bu süre içinde koşul gerçekleşmezse Süre dolarsa seçimine göre davranılır.",
    ("web.press", "modifier"): "Ör. Ctrl/Command + Enter ile gönderilen formlar için; çoğu durumda Yok kalır.",
    ("web.press", "by"): "Hedef boşsa tuş, sayfada o an odaktaki öğeye gönderilir.",
    ("web.navigate", "action"): "Yenile, sayfayı yeniden yükler; doldurulmuş ama gönderilmemiş alanlar silinebilir.",
    ("web.tab", "action"): "Sekmeler soldan sağa sıralıdır; kapatılan sekmeden sonra son sekmeye geçilir.",
    ("web.read_table", "by"): "Görünen metin, alan etiketi veya düğme adı çoğu sitede yeterlidir; CSS yalnız gerekirse.",
    ("web.download", "by"): "Görünen metin, alan etiketi veya düğme adı çoğu sitede yeterlidir; CSS yalnız gerekirse.",
    ("web.upload", "by"): "Dosya alanları çoğunlukla gizlidir; Alan etiketi veya CSS seçici kullanın.",
    ("window.checkbox", "operation"): "Durumunu oku hiçbir şeyi değiştirmez; sonucu Koşul'da kullanın.",
    ("file.zip", "operation"): "Aç: zip'teki dosyalar klasöre çıkarılır. Oluştur: dosya ve klasörler tek zip olur.",
    ("web.open", "browser"): "Seçilen tarayıcı bilgisayarda kurulu olmalıdır; ayrıca tarayıcı indirilmez.",
    ("mail.send", "cc"): "Alıcıların göreceği ek adresler; virgülle ayırın.",
    ("mail.send", "bcc"): "Diğer alıcıların görmeyeceği adresler; virgülle ayırın.",
    ("web.click", "by"): "Görünen metin, alan etiketi veya düğme adı çoğu sitede yeterlidir; CSS yalnız gerekirse.",
    ("web.fill", "by"): "Görünen metin, alan etiketi veya düğme adı çoğu sitede yeterlidir; CSS yalnız gerekirse.",
    ("web.read", "by"): "Görünen metin, alan etiketi veya düğme adı çoğu sitede yeterlidir; CSS yalnız gerekirse.",
    ("web.select", "by"): "Görünen metin, alan etiketi veya düğme adı çoğu sitede yeterlidir; CSS yalnız gerekirse.",
    ("window.text_write", "after"): "Tab sonraki alana geçer, Enter değeri onaylar. Uygulamanız hücreyi nasıl "
                                    "onaylıyorsa onu seçin.",
    ("desktop.find_window", "match"): "Başlık her açılışta aynıysa Tam eşleşme; içinde değişen numara, tarih veya "
                                      "ekran adı varsa İçerir.",
    ("desktop.find_window", "timeout"): "Pencere henüz açılmadıysa bu kadar saniye beklenir.",
    ("desktop.find_window", "on_missing"): "Devam et seçerseniz sonraki adımları ${erp_window.found} koşuluna bağlayın.",
    ("desktop.window_click", "y"): "Pencerenin üst kenarından piksel. Ekranda seç ile X ile birlikte dolar.",
    ("desktop.window_fill", "y"): "Pencerenin üst kenarından piksel. Ekranda seç ile X ile birlikte dolar.",
    ("window.read_field", "y"): "Pencerenin üst kenarından piksel. Ekranda seç ile X ile birlikte dolar.",
    ("window.read_table", "column"): "Tablodaki sütun başlığı (ör. Kod) veya sütun numarası. Büyük/küçük harf "
                                      "farkı önemsizdir.",
    ("window.read_table", "row"): "1: tablodaki ilk veri satırı. Başlık satırı sayılmaz.",
    ("window.read_table", "header"): "Çoğu uygulama tablosu kopyalanırken ilk satıra sütun adlarını koyar. Kopyalanan "
                                     "metinde başlık yoksa kapatın; sütunlar sutun_1, sutun_2… olur.",
    ("window.read_table", "mode"): "Hücre değeri okumak için Bir hücrenin değeri; aramanın sonuç verip vermediğini "
                                   "anlamak için Kaç satır var?.",
    ("desktop.window_click", "timeout"): "Görsel veya alan bu süre içinde bulunamazsa tıklama yapılmaz, adım durur.",
    ("desktop.window_wait_image", "on_missing"): "Akışı durdur: görsel gelmezse akış hata ile biter. Devam et: akış "
                                                 "sürer, ${image.found} yanlış olur; Koşul ile karar verin.",
    ("input.type", "x"): "Yazmadan önce tıklanacak noktanın ekrandaki yeri. Fare konumunu al ile doldurun; boş "
                         "bırakılırsa imlecin bulunduğu yere yazılır.",
    ("input.type", "y"): "X ile birlikte doldurulur.",
    ("desktop.window_fill", "timeout"): "Görsel veya alan bu süre içinde bulunamazsa yazma yapılmaz, adım durur.",
    ("desktop.window_fill", "clear"): "Açıkken alan seçilip silinir, sonra değer yazılır. Mevcut değerin sonuna "
                                      "eklemek için kapatın.",
    ("desktop.window_key", "key"): "Enter onaylar, Tab sonraki alana geçer, Escape pencereyi/mesajı kapatır.",
    ("desktop.window_key", "modifier"): "Kısayol için birlikte basılacak tuş (ör. Ctrl + Enter). Tek tuş için Yok.",
    ("desktop.window_click_key", "y"): "Pencerenin üst kenarından piksel. Ekranda seç ile X ile birlikte dolar.",
    ("desktop.window_click_key", "timeout"): "Görsel veya alan bu süre içinde bulunamazsa tıklama ve tuş "
                                             "gönderilmez, adım durur.",
    ("desktop.window_click_key", "key"): "Tıklamadan sonra gönderilecek tuş: Enter onaylar, Tab sonraki alana geçer, "
                                         "Aşağı ok listeyi açar.",
    ("desktop.window_click_key", "modifier"): "Kısayol için birlikte basılacak tuş (ör. Ctrl + Enter). Tek tuş için Yok.",
    ("desktop.window_click_key", "delay"): "Tıklanan alanın odağı alması için kısa bekleme. Tuş, uygulama hazır "
                                           "olmadan gidiyorsa artırın.",
    ("desktop.window_wait_image", "timeout"): "Görsel bu süre içinde görünmezse (veya kaybolmazsa) adım durur.",
    ("window.state", "state"): "Büyüt, koordinatla çalışan adımların her seferinde aynı yere denk gelmesini sağlar.",
    ("window.move", "x"): "Pencerenin sol kenarının ekrandaki konumu (piksel).",
    ("window.move", "y"): "Pencerenin üst kenarının ekrandaki konumu (piksel).",
    ("window.move", "width"): "Pencere genişliği (piksel).",
    ("window.move", "height"): "Pencere yüksekliği (piksel).",
    ("window.wait_close", "timeout"): "Pencere bu süre içinde kapanmazsa adım durur.",
    ("input.mouse_click", "y"): "Ekranın üst kenarından piksel. Fare konumunu al ile X ile birlikte dolar.",
    ("input.mouse_move", "y"): "Ekranın üst kenarından piksel. Fare konumunu al ile X ile birlikte dolar.",
    ("input.drag", "from_y"): "Başlangıç konumunu al ile X ile birlikte dolar.",
    ("input.drag", "to_y"): "Bitiş konumunu al ile X ile birlikte dolar.",
    ("input.drag", "button"): "Sürükleme sırasında basılı tutulacak düğme; genellikle Sol.",
    ("input.scroll", "amount"): "Eksi değer aşağı (veya sola), artı değer yukarı (veya sağa) kaydırır. Büyük sayı "
                                "daha çok kaydırır.",
    ("input.scroll", "direction"): "Liste ve sayfalar için Dikey; geniş tablolar için Yatay.",
    ("input.scroll", "y"): "Boş bırakılırsa fare neredeyse orada kaydırır.",
    ("input.type", "method"): "Otomatik çoğu uygulamada doğru çalışır. Yapıştırmayı engelleyen alanlarda Tuş tuş "
                              "yaz seçin.",
    ("input.press", "presses"): "Aynı tuşa art arda kaç kez basılacağı (ör. 3 kez Tab).",
    ("input.press", "interval"): "Uygulama basışları kaçırıyorsa artırın.",
    ("input.key_state", "key"): "Basılı tutulacak veya bırakılacak tuş.",
    ("input.key_state", "state"): "Basılı tut ile başlayın, işlem bitince aynı tuş için Bırak adımı ekleyin.",
    ("screen.find_image", "timeout"): "0 yazarsanız beklemeden yalnız o anki ekrana bakar.",
    ("screen.find_image", "window"): "Yalnız 'Tanıtılan pencere' seçiliyken kullanılır.",
    ("screen.click_image", "window"): "Yalnız 'Tanıtılan pencere' seçiliyken kullanılır.",
    ("screen.read_text", "window"): "Yalnız 'Tanıtılan pencere' seçiliyken kullanılır.",
    ("screen.wait_text", "window"): "Yalnız 'Tanıtılan pencere' seçiliyken kullanılır.",
    ("screen.screenshot", "window"): "Yalnız 'Tanıtılan pencere' seçiliyken kullanılır.",
    ("screen.wait_text", "text"): "Ekranda geçmesi beklenen kelime; büyük/küçük harf fark etmez (ör. kaydedildi).",
    ("screen.wait_text", "on_missing"): "Devam et seçerseniz sonuç ${text_found} yanlış olur; Koşul ile kontrol edin.",
    ("screen.pixel", "y"): "Ekranın üst kenarından piksel. Fare konumunu al ile X ile birlikte dolar.",
    ("screen.screenshot", "filename"): "Çalışma çıktılarında görünecek ad (ör. hata-ekrani.png).",
    ("system.open", "wait"): "Uygulamanın açılması için beklenecek süre; ağır programlarda artırın.",
    ("system.close_app", "force"): "Yalnız uygulama yanıt vermiyorsa açın; kaydedilmemiş veriler kaybolur.",
    ("system.command", "run"): "Komut yaz: terminale yazacağınız satırı girersiniz. Script dosyası seç: .py, .ps1, "
                               ".bat, .vbs, .sh gibi bir dosyayı türüne uygun programla çalıştırır.",
    ("system.command", "shell"): "Komut İstemi Windows'ta cmd, Mac'te Terminal'dir. PowerShell komutları (Get-…) "
                                 "için PowerShell seçin; Mac'te PowerShell (pwsh) kurulu olmalıdır.",
    ("system.command", "command"): "Terminale yazacağınız komutun aynısı (ör. dir, ipconfig); ${değişken} "
                                   "kullanılabilir.",
    ("system.command", "folder"): "Komutun çalışacağı klasör. Boşsa komut kullanıcı klasöründe, script kendi "
                                  "klasöründe çalışır.",
    ("system.command", "timeout"): "Bu sürede bitmezse durdurulur ve akış hata verir.",
    ("system.command", "fail_on_error"): "Kapalıysa hata kodu olsa da akış devam eder; ${command.code} ile kontrol "
                                         "edin.",
    ("system.run_file", "timeout"): "Script bu sürede bitmezse kapatılır ve akış hata verir.",
    ("system.run_file", "fail_on_error"): "Kapalıysa script hata verse de akış devam eder; ${script.code} ile kontrol edin.",
    ("clipboard.set", "value"): "Panoya konacak metin veya ${değişken}.",
    ("file.write_table", "sheet"): "Excel dosyasında yazılacak sayfanın adı; CSV'de kullanılmaz.",
    ("file.write_table", "last_row_column"): "Yeni kayıtlar bu sütundaki son dolu satırın altına yazılır (ör. A). "
                                             "Boşsa herhangi bir sütunda değer olan son satır esas alınır; yalnız "
                                             "biçimlendirilmiş boş satırlar sayılmaz.",
    ("file.write_table", "formulas"): "Açıkken = ile başlayan değerler formül olarak yazılır. Kapalıyken metin "
                                      "olarak saklanır; dışarıdan gelen veri formüle dönüşmez.",
    ("file.write_cell", "sheet"): "Mevcut dosyada bu sayfa yoksa yazma yapılmaz. Boş: dosyanın etkin sayfası.",
    ("file.write_cell", "column"): "Değerin yazılacağı sütun harfi (ör. A, D, AB).",
    ("file.write_cell", "row_mode"): "Belirli satır: satır numarasını siz verirsiniz. Son dolu satırın altına: listeye "
                                     "yeni satır ekler. Son dolu satıra: son kaydın yanına değer yazar.",
    ("file.write_cell", "row"): "1: ilk satır. Döngüde okunan satırın kendisine yazmak için ${row.row_number}.",
    ("file.write_cell", "last_row_column"): "Son satırı hangi sütunun belirleyeceği (ör. kayıt numarasının olduğu "
                                            "A sütunu). Boşsa yazılan sütun esas alınır.",
    ("file.write_cell", "value_type"): "Metin / değer olduğu gibi yazar; = ile başlayan metin formüle dönüşmez. Sayı, "
                                       "1250,50 gibi değerleri Excel'de sayı olarak saklar. Formül, değeri Excel "
                                       "formülü olarak yazar.",
    ("file.write_cell", "value"): "Sabit değer veya ${değişken}. Formülde İngilizce işlev adı ve virgül kullanın "
                                  "(ör. =SUM(B2:B{satir})); {satir} yazılan satırın numarası olur.",
    ("file.write_text", "text"): "Dosyaya yazılacak metin; ${değişken} kullanılabilir.",
    ("file.exists", "kind"): "Yalnız dosya veya yalnız klasör aranacaksa seçin.",
    ("file.list", "recursive"): "Açıksa alt klasörlerdeki dosyalar da listelenir.",
    ("file.list", "sort"): "En yeni önce: son indirilen dosyayı bulmak için.",
    ("file.operation", "operation"): "Sil geri alınamaz; dosya çöp kutusuna gitmez.",
    ("file.operation", "source"): "İşlem yapılacak dosya veya klasör.",
    ("file.operation", "destination"): "Kopyalama ve taşımada yeni yol; Sil'de kullanılmaz.",
    ("file.operation", "overwrite"): "Kapalıyken hedef zaten varsa adım durur.",
    ("file.wait", "timeout"): "Dosya bu süre içinde oluşmazsa adım durur.",
    ("data.export_csv", "filename"): "Çalışma çıktılarında görünecek ad; .csv ile bitmeli.",
    ("core.set", "value"): "Metin, sayı, liste veya başka bir değişken (${row.form_id}). Türünü üstteki "
                           "listeden seçin.",
    ("text.transform", "text"): "İşlenecek metin; genellikle bir değişken (ör. ${mesaj}).",
    ("text.transform", "operation"): "Aşağıdaki alanlar seçtiğiniz işleme göre değişir.",
    ("text.transform", "find"): "Değiştir'de aranan metin, Böl'de ayraç (ör. virgül), Soldan doldur'da dolgu karakteri.",
    ("text.transform", "replace_with"): "Bulunan metnin yerine yazılacak değer; silmek için boş bırakın.",
    ("text.transform", "all_matches"): "Kapalıyken yalnız ilk eşleşme alınır.",
    ("text.transform", "start"): "İlk karakter 0'dır. 2 yazarsanız üçüncü karakterden başlar.",
    ("text.transform", "length"): "Alınacak karakter sayısı (Soldan doldur'da toplam uzunluk).",
    ("text.transform", "turkish"): "Açıkken i → İ ve ı → I olarak çevrilir.",
    ("data.date", "operation"): "Aşağıdaki alanlar seçtiğiniz işleme göre değişir.",
    ("data.date", "other"): "Farkı alınacak ikinci tarih; 'şimdi' yazılabilir.",
    ("data.date", "amount"): "Eklenecek miktar; geçmişe gitmek için eksi yazın (ör. -7).",
    ("data.date", "unit"): "Miktarın birimi.",
    ("data.list", "list"): "İşlenecek liste; genellikle okuma adımının çıktısı (ör. ${sheet_rows}).",
    ("data.list", "operation"): "Aşağıdaki alanlar seçtiğiniz işleme göre değişir.",
    ("data.list", "operator"): "Filtrede alanın değerle nasıl karşılaştırılacağı.",
    ("data.list", "value"): "Filtrede aranacak değer.",
    ("data.list", "index"): "0 ilk öğe, 1 ikinci öğe, -1 son öğe.",
    ("data.list", "count"): "Alınacak öğe sayısı; boşsa tümü.",
    ("data.list", "separator"): "Birleştir'de öğelerin arasına konacak metin.",
    ("data.list", "descending"): "Açıkken büyükten küçüğe (Z → A) sıralar.",
    ("data.append", "name"): "Listenin adı. Liste yoksa ilk eklemede oluşturulur.",
    ("data.append", "value"): "Eklenecek değer; satırın tamamı için ${row}.",
    ("sheets.read_cell", "cell"): "Okunacak hücre (ör. B2). Döngüde B${row.row_number} yazılabilir.",
    ("sheets.read_rows", "start_row"): "1. satır başlıksa 2 yazın.",
    ("sheets.read_rows", "max_rows"): "Tablonun sonuna kadar okumak için 1000 yazın (en fazla 1000).",
    ("sheets.read_rows", "empty_policy"): "Okumayı bitir: ana alanı boş ilk satırda durur. Satırı atla: boş satırı "
                                          "geçip okumaya devam eder.",
    ("sheets.read_rows", "output"): "Satır listesinin adı. Her satır için adımında ${sheet_rows} olarak verin.",
    ("sheets.read_column", "start_cell"): "Okumanın başlayacağı hücre; aşağı doğru devam eder.",
    ("sheets.read_column", "empty_policy"): "Okumayı bitir: ilk boş hücrede durur. Atla: boş hücreyi geçer.",
    ("sheets.write", "range"): "Yazmanın başlayacağı hücre (ör. L5). Değerler sağa ve aşağı doğru yerleşir.",
    ("sheets.write", "values"): "Satır listesi: [[\"a\", \"b\"]] bir satırda yan yana iki hücreye yazar.",
    ("sheets.write", "spreadsheet_id"): "Google Sheets tablosunun tarayıcıdaki adresinin tamamını yapıştırabilirsiniz.",
    ("control.for_each", "items"): "Üzerinde dönülecek liste; genellikle okuma adımının çıktısı (${sheet_rows}).",
    ("control.for_each", "start"): "Boş: ilk satırdan başlar. 1 listenin ilk kaydıdır; başlık satırını okuma adımı "
                                   "zaten atlar. Ör. 50 yazarsanız ilk 49 kayıt atlanır (yarıda kalan işi "
                                   "sürdürmek için).",
    ("control.while", "max_iterations"): "Koşul hiç değişmezse sonsuz döngüyü önler; sınıra ulaşılırsa akış hata ile durur.",
    ("core.wait", "seconds"): "Ondalık yazılabilir (0,5). Mümkünse sabit bekleme yerine Pencerede görseli bekle kullanın.",
    ("control.repeat", "count"): "İç adımların kaç kez çalışacağı.",
    ("control.try", "error_name"): "Hata mesajının saklanacağı değişken; Hata olursa dalında ${error_message} olarak kullanın.",
    ("control.run_workflow", "workflow"): "Çalıştırılacak kayıtlı akış. Bir akış kendisini çağıramaz.",
    ("control.goto", "target"): "Akışın bu adımdan sonra devam edeceği adım. Gerideki bir adımı seçerseniz "
                                 "o adımdan itibaren tekrar çalışılır.",
    ("control.goto", "max_jumps"): "Bu bağlantı bir döngü turunda (döngü dışındaysa çalışma boyunca) en fazla bu "
                                   "kadar kullanılır; aşılırsa akış sonsuz döngüye girmeden durur.",
    ("control.stop", "status"): "Hata seçilirse çalışma 'Hata' olarak işaretlenir.",
    ("control.stop", "message"): "Çalışma geçmişinde görünecek açıklama.",
    ("core.log", "message"): "Çalışma günlüğüne yazılacak metin; değişken değerlerini görmek için ${ad} ekleyin.",
    ("ui.message", "title"): "Mesaj kutusunun başlığı.",
    ("ui.message", "text"): "Gösterilecek mesaj; ${değişken} kullanılabilir.",
    ("ui.message", "buttons"): "Evet / Hayır seçerseniz yanıtı ${answer} ile Koşul adımında kontrol edin.",
    ("ui.message", "timeout"): "Yanıt verilmezse kutunun kendiliğinden kapanacağı süre; kapanınca ${answer} timeout "
                               "olur.",
    ("ui.input", "title"): "Soru kutusunun başlığı.",
    ("ui.input", "prompt"): "Kullanıcıya sorulacak soru (ör. Fatura tarihini girin).",
    ("ui.input", "default"): "Kutuda hazır gelecek değer.",
    ("ui.input", "on_cancel"): "Kullanıcı İptal'e basarsa ne olacağı.",
    ("http.request", "method"): "Veri almak için GET, göndermek için POST.",
    ("http.request", "url"): "API bağlantısı seçiliyse yol (ör. /v1/siparisler/${row.no}); değilse https:// ile "
                             "başlayan tam adres.",
    ("http.request", "headers"): "Ek başlıklar (ör. {\"Accept\": \"application/json\"}). Kimlik bilgisini buraya değil, "
                                 "API bağlantısına yazın; orada korunur ve günlükte gizlenir.",
    ("http.request", "timeout"): "Yanıt bu sürede gelmezse istek durdurulur.",
    ("database.read", "table"): "Bağlantıda izin verilen bir tablo: şema.tablo biçiminde.",
    ("database.query", "query"): "Tek bir SELECT (veya WITH) sorgusu. Değerleri ${row.kod} ile yazın; tırnak "
                                 "koymanıza gerek yok, güvenli parametre olarak gönderilir. Liste için "
                                 "IN (${kodlar}), metin araması için LIKE '%${ad}%' yazabilirsiniz.",
    ("database.query", "max_rows"): "Sorgu daha fazla satır döndürürse ilk bu kadar satır alınır ve günlükte "
                                    "uyarı görünür.",
    ("database.query", "output"): "Satır listesinin adı. Her satır için adımında ${rows} olarak verin; "
                                  "${row.SUTUN_ADI} ile alanlara ulaşın.",
    ("mail.read", "unread_only"): "Açıkken yalnız henüz okunmamış iletiler gelir; işlediklerinizi okundu işaretleyerek "
                                  "aynı iletiyi iki kez işlemezsiniz.",
    ("mail.read", "from_contains"): "Gönderen adresinde veya adında geçen metin (ör. @tedarikci.com). Boş: herkes.",
    ("mail.read", "subject_contains"): "Konuda geçen metin (ör. Fatura). Büyük/küçük harf fark etmez.",
    ("mail.read", "since_days"): "Yalnız son bu kadar gündeki iletiler; 0 tarih sınırı koymaz.",
    ("mail.read", "max_messages"): "Bundan fazla ileti varsa en eskileri önce gelir, kalanlar sonraki çalışmada okunur.",
    ("mail.read", "mark_read"): "İşaretlenen iletiler Yalnız okunmamışlar açıkken bir daha gelmez.",
    ("mail.read", "attachment_folder"): "Her ekin kaydedildiği yol ${email.attachments[0].path} gibi listede yer alır. Aynı "
                                        "adda dosya varsa yeni dosyaya numara eklenir.",
    ("ftp.transfer", "operation"): "İndir: sunucudan bu bilgisayara; Yükle: bu bilgisayardan sunucuya; Listele: uzak "
                                   "klasördeki dosyalar.",
    ("ftp.transfer", "local_path"): "Bu bilgisayardaki dosyanın tam yolu (ör. C:\\Aktarim\\fatura.xml).",
    ("ftp.transfer", "overwrite"): "Kapalıyken hedefte aynı adlı dosya varsa aktarım yapılmaz ve akış durur.",
    ("notify.send", "title"): "Mesajın üstünde kalın görünen kısa başlık (isteğe bağlı).",
    ("database.execute", "query"): "Tek bir komut: INSERT INTO tablo (...) VALUES (...), UPDATE tablo SET ... WHERE ..., "
                                   "DELETE FROM tablo WHERE ..., MERGE veya EXEC dbo.yordam @p = ${deger}. Değerleri "
                                   "${row.no} ile yazın; tırnak gerekmez, güvenli parametre olarak gönderilir.",
    ("database.execute", "max_rows"): "Komut bundan fazla satırı değiştirecekse hiçbir şey kaydedilmez ve akış durur. "
                                      "Tek kaydı güncelleyen adımda 1 bırakın.",
    ("database.execute", "on_zero"): "Koşula uyan kayıt yoksa: Akışı durdur, kaydın bulunamadığını gösterir. Devam et "
                                     "seçilirse ${db_result.affected} 0 olur.",
    ("database.execute", "output"): "${db_result.affected}: değişen satır sayısı (saklı yordamda bilinmeyebilir), "
                                    "${db_result.rows}: OUTPUT / RETURNING veya yordamın döndürdüğü satırlar.",
}


def guide(how: list[str], result: str = "", tip: str = "") -> dict:
    return {"how": how, "result": result, "tip": tip}


GUIDES = {
    # ----- Pencere -------------------------------------------------------------------
    "desktop.find_window": guide(
        ["Otomasyon yapılacak uygulamayı açın.",
         "Açık pencerelerden seç ile pencereyi seçin; başlık değişiyorsa sabit kısmını yazıp İçerir seçin.",
         "Şimdi kontrol et ile bulunduğunu doğrulayın.",
         "Pencereye verilecek ad alanına kısa bir ad yazın (ör. erp_window). Yalnız ad; ${ } işaretleri olmadan."],
        "Pencere bu adla saklanır. Sonraki pencere adımlarının Pencere alanında listeden seçilir. "
        "${erp_window.found}, pencerenin açık olup olmadığını verir.",
        "Akışın ilk adımlarından biri olmalı. Her pencere adımı bu çıktıyı kullanır."),
    "desktop.window_click": guide(
        [WINDOW_FIRST, PICK_TARGET, "Kayıt açmak için Tıklama sayısını Çift tık yapın."],
        "", TEST_HINT),
    "desktop.window_fill": guide(
        [WINDOW_FIRST, PICK_TARGET,
         "Yazılacak değere sabit metin veya tablodan gelen değeri yazın (ör. ${row.form_id})."],
        "", "Alana tıklamayı kendisi yapar; önüne ayrı bir tıklama adımı eklemeyin. " + TEST_HINT),
    "desktop.window_key": guide(
        [WINDOW_FIRST, "Tuşu seçin: Enter onaylar, Tab sonraki alana geçer, Escape kapatır.",
         "Kısayol gerekiyorsa Birlikte basılacak tuşu seçin."],
        "", "Tuş, pencerede o an seçili olan alana gider. Önce Alanı doldur veya Pencerede tıkla ile doğru alanı seçin."),
    "desktop.window_click_key": guide(
        [WINDOW_FIRST, PICK_TARGET, "Tıklamadan sonra gönderilecek tuşu ve gerekiyorsa birlikte basılacak tuşu seçin."],
        "", "Tıklama ile tuş aynı adımda gider; pencere arada değişir veya odağı kaybederse tuş gönderilmez. "
            + TEST_HINT),
    "desktop.window_wait_image": guide(
        [WINDOW_FIRST, "Ekranda seç ile beklenecek işareti (düğme, başlık, hata kutusu) görsel olarak kaydedin.",
         "Görünsün veya Kaybolsun seçin ve en fazla bekleme süresini yazın.",
         "Görsel çıkmazsa akış dursun mu, devam mı etsin seçin."],
        "${image.found}: görsel bulundu mu (doğru/yanlış). ${image.center_x}, ${image.center_y}: ekrandaki yeri.",
        "Sabit Bekle yerine bunu kullanın: ekran hazır olur olmaz devam eder. Bir hata kutusu çıktı mı diye bakmak "
        "için Süre dolarsa: Devam et seçin, ardından Koşul ile ${image.found} değerini kontrol edin."),
    "window.activate": guide(
        [WINDOW_FIRST, "Klavye adımlarından (Metin yaz, Tuşa bas, Kısayol) hemen önce ekleyin."],
        "", "Pencerede tıkla ve Alanı doldur pencereyi kendileri öne getirir; onlardan önce gerekmez."),
    "window.read_field": guide(
        [WINDOW_FIRST, PICK_TARGET, "Çıktı değişkenine bir ad verin."],
        "Alandaki metin. Koşul adımında veya Sheets'e yazarken kullanın.",
        "Alan kimliği dışındaki yöntemlerde alana tıklanıp içerik kopyalanır; pano sonra eski haline döner. "
        "Hedef bir tablo/liste ise tablonun tamamı başlıklarıyla gelir; tek bir hücre için "
        "Tablodan değer oku adımını kullanın."),
    "window.write_table": guide(
        ["Pencereyi seçin; Tabloyu seç düğmesine basıp görüntüde tablonun herhangi bir hücresine tıklayın.",
         "Satır 1, Yazılacak sütun Durum, Yazılacak değer Tamamlandı: ilk veri satırının Durum hücresini değiştirir.",
         "Bu adımı test et → Yeri göster ile hücrenin güncel yerini kontrol edin; Gerçekten çalıştır ile yazın."],
        "Seçilen hücreye yazılan değer kontrol edilir.",
        "Seçilen nokta tabloyu tanıtır; hedef hücrenin konumu değildir. Satır ve sütunlar seçimde okunur, "
        "çalışırken yeniden bulunur. Sütunu listeden seçebilir, adını, sutun_2 veya 2 yazabilirsiniz. "
        "Doğrudan hücre erişimi yoksa tablo kopyalanır ve görünür hücre doğrulanır. Boş hücre, sütun başlığı ile "
        "aynı satırdaki tek olan dolu bir değerin kesişiminden bulunur; ikisi de ekranda görünmelidir. "
        "Önizlemede başlık satırında Başlık yap seçin; başlık yoksa Başlık yok seçin. Veri 1, Satır 1’dir. Hücre otomatik düzenlemeye açılır; değişkenin değeri yazılıp tüm tablo yeniden okunarak doğrulanır. Kaydetme/onayı ayrıca ekleyin."),
    "window.checkbox": guide(
        [WINDOW_FIRST,
         "İşlemi seçin: İşaretle, İşaretini kaldır veya Durumunu oku.",
         "Ekranda seç ile onay kutusunu seçin. Uygulama alan kimliği veriyorsa durum doğrudan uygulamadan okunur.",
         "Java veya özel çizilmiş ekranlarda Konum ya da Referans görsel ile seçin; ardından kutu işaretliyken ve "
         "işaretsizken birer küçük görüntüsünü seçin.",
         "Bu adımı test et → Yeri göster ile kutuyu kontrol edin."],
        "${checkbox_state}: işaretliyse doğru, değilse yanlış.",
        "Kutu zaten istenen durumdaysa tıklanmaz. Değiştirince yeni durum doğrulanır; değişmezse yeniden tıklanmaz. "
        "Durum kesin anlaşılamazsa adım durur."),
    "window.text_write": guide(
        [WINDOW_FIRST,
         "Bölge çiz ile pencere görüntüsünde aranacak alanı seçin (ör. yalnız tablo).",
         "Nereye tıklansın? Dolu bir alan için Bulunan metnin üzerine; boş hücre için Sütun ve satır kesişimi.",
         "Kesişimde Sütun metni başlık (ör. Miktar), Satır metni o satırdaki başka bir değerdir (ör. A125).",
         "Bu adımı test et → Yeri göster ile noktayı kontrol edin; Gerçekten çalıştır ile yazın."],
        "Tıklanan nokta ve yazılan değer test günlüğünde görünür.",
        "Metnin bir parçasını yazmak yeterlidir (İad → İade); tıklama o yazının ortasına yapılır. "
        "Konum her çalışmada ekrandaki metinden ölçülür; ekran ölçeği veya sütun genişliği değişse de "
        "kaydedilmiş koordinat kullanılmaz. Metin bulunamazsa veya alanda birden fazla yerde görünürse tıklanmaz; "
        "alanı daraltın. Satır kaydırılıp görünmez olduysa önce kaydırın. Kaydetme/onayı ayrıca ekleyin."),
    "file.zip": guide(
        ["İşlemi seçin: Zip'i klasöre aç veya Zip oluştur.",
         "Açarken zip dosyasını ve açılacak klasörü; oluştururken her satıra bir dosya/klasör ve zip dosyasının adını yazın."],
        "${zip_result.files}: açılan veya eklenen dosyalar; ${zip_result.count}: sayısı.",
        "Aynı adlı dosya varsa, üzerine yazma açık değilse hiçbir dosya yazılmaz. Klasör dışına yazmaya çalışan "
        "zip'ler açılmaz. Windows'ta oluşturulmuş zip'lerdeki Türkçe adlar korunur."),
    "file.read_pdf": guide(
        ["PDF dosyasını seçin.",
         "Metin için Ne okunsun: Metin; çizgili bir tablo için Tablo seçin.",
         "Gerekirse sayfaları yazın (ör. 1-2). Metinden fatura no veya tutar almak için ardından Metin işlemi → "
         "Desenle bilgi çıkar ekleyin."],
        "Metin modunda ${pdf_text} metindir; tablo modunda Her satır için ile kullanılacak satır listesidir.",
        "Taranmış sayfalar sistem OCR'ıyla okunur; kalite taramaya bağlıdır. Şifreli PDF okunmaz."),
    "web.wait": guide(
        ["Ne beklensin? seçin: öğe görünsün, kaybolsun veya adres bir metni içersin.",
         "Öğe için hedefi yazın (ör. Kaydedildi yazısı) ve en fazla bekleme süresini girin."],
        "${web_waited}: koşul gerçekleştiyse doğru.",
        "Yükleniyor yazısının kaybolmasını beklemek, sabit beklemeden hem hızlı hem güvenlidir."),
    "web.press": guide(
        ["Tuşu seçin (ör. Enter).", "Belirli bir alana basmak için hedefi yazın; boşsa odaktaki öğeye basılır."],
        "", "Arama kutusuna yazdıktan sonra Enter ile aramayı başlatmak için kullanın."),
    "web.navigate": guide(["Geri, İleri veya Yenile seçin."], "${web_url}: gidilen sayfanın adresi."),
    "web.tab": guide(
        ["Geçilecek sekmeyi seçin veya etkin sekmeyi kapatın.",
         "Başlık veya adrese göre seçmek için aranacak metni yazın."],
        "${web_url}: etkin sekmenin adresi.",
        "Bir bağlantı yeni sekme açarsa sonraki adımlar o sekmede çalışır; bu adım yalnız başka sekmeye dönmek içindir."),
    "web.read_table": guide(
        ["Tablonun içindeki bir yazıyı (ör. sütun başlığı) veya tablonun CSS seçicisini hedef olarak yazın.",
         "Ardından Her satır için ekleyip ${row.Sütun_adı} ile kullanın."],
        "${web_rows}: satır listesi.", "Birleştirilmiş hücreler tek hücre olarak okunur."),
    "web.download": guide(
        ["İndirmeyi başlatan bağlantıyı veya düğmeyi hedef olarak yazın (ör. Excel'e aktar).",
         "Kaydedilecek klasörü seçin."],
        "${web_file}: indirilen dosyanın tam yolu; ardından Excel / CSV oku ile açabilirsiniz.",
        "Tıklamadan sonra süre içinde indirme başlamazsa adım durur."),
    "web.upload": guide(
        ["Dosya seçme alanını etiketiyle veya CSS ile belirtin.", "Her satıra bir dosya yolu yazın."],
        "", "Gözat penceresi açılmaz; dosya doğrudan alana verilir. Ardından Yükle düğmesine tıklayın."),
    "web.screenshot": guide(
        ["Dosya adını yazın; sayfanın tamamı veya yalnız görünen kısmı seçin."],
        "${web_image}: görüntünün yolu; çalışmanın çıktılarında da görünür.",
        "Hata olursa dalında kullanarak hata anındaki sayfayı saklayabilirsiniz."),
    "web.script": guide(
        ["JavaScript kodunu async bir fonksiyonun gövdesi olarak yazın; sonucu return ile verin.",
         "Akış değişkenlerini Girdi alanından verin; kodda girdi adıyla kullanılır.",
         "Örnek: return [...document.querySelectorAll('h2')].map(h => h.innerText);"],
        "${web_result}: return ile döndürülen değer.",
        "Kod sayfanın içinde, oturum açmış kullanıcı yetkisiyle çalışır; güvenmediğiniz kodu yapıştırmayın. "
        "Kodun içindeki ${...} JavaScript'e aittir; akış değişkeni olarak doldurulmaz."),
    "mail.send": guide(
        ["E-posta (SMTP) bağlantısı seçin veya yeni oluşturun; Bağlantıyı test et ile deneyin (posta gönderilmez).",
         "Kime, Konu ve İleti yazın; ek için her satıra bir dosya yolu yazın.",
         "Değişken kullanabilirsiniz: Konu: Fatura ${row.no} işlendi."],
        "${mail_result.to}: gönderilen adresler.",
        "Gmail ve Microsoft 365'te uygulama şifresi gerekebilir. Hata olursa posta yeniden gönderilmez; iki kez "
        "gitmesin diye. Akışın sonunda özet göndermek için Hata olursa bloğuyla birlikte kullanın."),
    "web.open": guide(
        ["Adresi yazın (https://…).",
         "Tarayıcıyı seçin; Otomatik Windows'ta Edge, Mac'te Chrome kullanır.",
         "Sonra Web alanını doldur, Web öğesine tıkla ve Web'den metin oku adımlarını ekleyin."],
        "${web_url}: açılan sayfanın adresi.",
        "Tarayıcı çalışma bitince kapanır. Girişler RpaOrkestrAI'nin ayrı profilinde hatırlanır; kendi "
        "tarayıcınızın profili kullanılmaz."),
    "web.click": guide(
        ["Hedefi bulma yöntemini seçin; düğmeler için Düğme veya bağlantı adı.",
         "Hedef'e sayfada görünen yazıyı yazın (ör. Kaydet)."],
        "",
        "Hedef birden fazla öğeyle eşleşirse tıklanmaz; Tam eşleşmeyi açın veya daha ayırt edici bir yazı kullanın. "
        "Tıklama tekrarlanmaz."),
    "web.fill": guide(
        ["Hedefi bulma yöntemi olarak Alan etiketi veya Alandaki silik yazı seçin.",
         "Hedef'e alanın yanındaki etiketi yazın (ör. Fatura No); Yazılacak değeri girin."],
        "",
        "Alandaki eski değer silinip yenisi yazılır. Şifre için ${sifre.ad} kullanın; günlükte gizlenir."),
    "web.read": guide(
        ["Okunacak öğeyi görünen metniyle, etiketiyle veya CSS ile belirtin."],
        "${web_text}: öğenin metni; yazı alanlarında alanın değeri.",
        "Boş bir sonuç alanı da okunabilir; değer boş metin olur."),
    "web.select": guide(
        ["Açılır listeyi etiketiyle veya CSS ile belirtin.",
         "Seçilecek seçeneğin listede görünen adını yazın."],
        "${web_option}: seçilen seçeneğin tam adı.",
        "Tam eşleşme kapalıyken adın içinde geçmesi yeterlidir; birden fazla seçenek eşleşirse seçilmez."),
    "window.read_table": guide(
        [WINDOW_FIRST,
         "Ekranda seç ile tablonun herhangi bir satırına tıklayın; hücreyi tek tek göstermeniz gerekmez.",
         "Sütun alanına tablodaki başlığı yazın (ör. Kod) ya da sütun numarasını (1, 2, …).",
         "Satır 1, tablodaki ilk veri satırıdır."],
        "Seçilen hücrenin metni, ekranda göründüğü gibi. “Kaç satır var?” seçilirse bulunan satır sayısı.",
        "Arama sonuç vermediyse satır sayısı 0 olur; önce bunu Koşul ile kontrol edin. Tablodaki 540.767 gibi "
        "bir numarayı Sheets'teki 540767 ile karşılaştırmadan önce Metin işlemi → Bul ve değiştir ile noktayı silin."),
    "window.state": guide(
        [WINDOW_FIRST, "Büyüt, Küçült veya Geri yükle seçin."],
        "", "Koordinatla çalışan akışlarda başa Büyüt ekleyin; pencere her seferinde aynı boyutta olur."),
    "window.move": guide(
        [WINDOW_FIRST, "Sol, üst, genişlik ve yükseklik değerlerini piksel olarak yazın."],
        "", "Pencere büyütülemiyorsa X/Y hedeflerini sabitlemek için kullanın."),
    "window.close": guide(
        [WINDOW_FIRST, "Kapatılacak pencerenin değişkenini seçin."],
        "", "Uygulama 'kaydedilsin mi?' diye sorarsa ardından Pencerede tuşa bas ekleyin."),
    "window.wait_close": guide(
        [WINDOW_FIRST, "Kapanması beklenen pencereyi ve en fazla süreyi yazın."],
        "", "Yazdırma, kayıt veya yükleme penceresi kapanmadan sonraki adıma geçmemek için."),
    # ----- Fare ve klavye ------------------------------------------------------------
    "input.mouse_click": guide(
        ["Fare konumunu al'a basın, 3 saniye içinde fareyi hedefin üzerine götürün.",
         "Gerekirse düğmeyi (sol/sağ) ve tıklama sayısını seçin."],
        "", "Pencere taşınırsa nokta kayar. Bir uygulamanın içindeki hedefler için Pencerede tıkla daha güvenlidir."),
    "input.mouse_move": guide(
        ["Fare konumunu al ile hedef noktayı alın."],
        "", "Üzerine gelince açılan menüler için; tıklama yapmaz."),
    "input.drag": guide(
        ["Başlangıç konumunu al ile tutulacak noktayı, Bitiş konumunu al ile bırakılacak noktayı alın.",
         "Uygulama hızlı sürüklemeyi algılamıyorsa süreyi artırın."]),
    "input.scroll": guide(
        ["Miktarı yazın: eksi aşağı, artı yukarı kaydırır.",
         "Belirli bir listenin üzerinde kaydırmak için Fare konumunu al ile noktayı alın."]),
    "input.type": guide(
        ["Metni yazın; ${değişken} kullanılabilir.",
         "Yazılacak yeri göstermek için Fare konumunu al'a basın ve 3 saniye içinde fareyi o alanın üzerine götürün. "
         "Adım önce oraya tıklar, sonra yazar.",
         "X ve Y boş kalırsa metin imlecin o an bulunduğu yere yazılır (ör. Tab ile geçilen alan)."],
        "", "uygulama alanları için Alanı doldur daha güvenlidir: pencereyi izler, pencere kayınca da alanı bulur, "
            "eski değeri temizler ve odak değişirse yazmaz. Metin yaz ekran koordinatı kullanır."),
    "input.hotkey": guide(
        ["Kısayolu + ile yazın: mod+s, alt+f4, ctrl+shift+n.",
         "mod, Windows'ta Ctrl, Mac'te Command tuşudur; iki sistemde de çalışır."],
        "", "Kısayol o an öndeki pencereye gider. Önüne Pencereyi öne getir ekleyin."),
    "input.press": guide(
        ["Tuşu seçin ve kaç kez basılacağını yazın."],
        "", "Tuş o an öndeki pencereye gider. Belirli bir pencere için Pencerede tuşa bas kullanın."),
    "input.key_state": guide(
        ["Tuşu seçip Basılı tut deyin.", "Tıklamaları yapın, ardından aynı tuş için Bırak adımı ekleyin."],
        "", "Shift veya Ctrl ile çoklu seçim için. Akış bitince basılı kalan tuşlar kendiliğinden bırakılır."),
    "input.mouse_position": guide(
        ["Çıktı değişkenine ad verin."], "${mouse.x} ve ${mouse.y}: farenin o anki konumu."),
    # ----- Ekran ve görsel -----------------------------------------------------------
    "screen.find_image": guide(
        ["Ekrandan görsel seç ile aranacak işareti kaydedin.",
         "Bir uygulamanın içindeyse Bölge neye göre? alanında Tanıtılan pencere seçin.",
         "Süre dolarsa ne olacağını seçin."],
        "${image.found}: bulundu mu? ${image.center_x}, ${image.center_y}: yeri. Koşul adımında kullanın.",
        "Bir mesaj kutusu çıktı mı diye bakmak için: Devam et seçin, ardından Koşul ile ${image.found} kontrol edin."),
    "screen.click_image": guide(
        ["Ekrandan görsel seç ile tıklanacak düğmeyi veya simgeyi kaydedin.",
         "Görselin yanındaki bir yere tıklanacaksa merkezden farkı yazın."],
        "", "Görsel bulunamazsa tıklama yapılmaz, adım durur. " + TEST_HINT),
    "screen.read_text": guide(
        ["Bölge neye göre? alanında Tanıtılan pencere seçin.",
         "Bölge çiz ile görüntüyü alın; fareyi basılı tutup okunacak alanı dikdörtgen çizerek seçin ve kaydedin.",
         "Çıktı değişkenine ad verin (ör. mesaj)."],
        "Okunan metin. Koşul adımında İçerir ile kontrol edin veya Sheets'e yazın.",
        "Bölgeyi dar tutun: yalnız okunacak yazı kalsın. Sayı okurken Metin işlemi ile gereksiz karakterleri temizleyin."),
    "screen.wait_text": guide(
        ["Beklenen kelimeyi yazın (ör. kaydedildi).", "Bölge çiz ile yazının çıkacağı alanı seçin."],
        "${text_found}: metin göründü mü?"),
    "screen.pixel": guide(
        ["Fare konumunu al ile noktayı alın."],
        "${pixel}: #RRGGBB rengi. Durum lambası veya seçili satır kontrolü için Koşul'da kullanın."),
    "screen.screenshot": guide(
        ["Tüm ekran için bölgeyi boş bırakın veya Bölge çiz ile seçin.", "Dosya adını yazın."],
        "Görüntü çalışma ayrıntısındaki çıktılara eklenir.",
        "Hata olursa dalına ekleyin: hata anında ekranın nasıl göründüğünü sonradan görürsünüz."),
    # ----- Uygulama ve sistem --------------------------------------------------------
    "system.open": guide(
        ["Seç… ile programı, masaüstü kısayolunu (.lnk) veya belgeyi gösterin; klasör yolunu ya da web adresini yazın.",
         "Programı normalde açtığınız kısayolu seçebilirsiniz; kısayolun başlatma ayarları korunur.",
         "Açılması uzun sürüyorsa bekleme süresini artırın."],
        "", "Masaüstünde çift tıklamak gibidir; akış programın kapanmasını beklemez. Ardından Pencereyi tanı "
            "ekleyip açılan pencereyi akışa tanıtın. Script çalıştırıp çıktısını almak için Komut / script "
            "çalıştır adımını kullanın."),
    "system.run_file": guide(
        ["Seç… ile çalıştırılacak dosyayı gösterin (ör. Masaüstündeki aktar.py).",
         "Gerekiyorsa parametreleri yazın.",
         "Akış script'in sonucunu kullanacaksa Bitmesini bekle açık kalsın."],
        "${script.output}: script'in yazdığı çıktı, ${script.code}: bitiş kodu (0 başarılı).",
        "Python için bilgisayarda Python kurulu olmalıdır. Excel makrosu için makroyu çağıran bir .vbs veya "
        ".py dosyasını da bu adımla çalıştırabilirsiniz."),
    "system.close_app": guide(
        ["Uygulamanın adını yazın (ör. notepad.exe veya TextEdit)."],
        "", "Zorla kapat kaydedilmemiş verileri kaybettirir; yalnız uygulama yanıt vermiyorsa açın."),
    "system.command": guide(
        ["Ne çalıştırılsın? alanında Komut yaz veya Script dosyası seç'i seçin.",
         "Komutu terminale yazacağınız gibi girin (PowerShell komutu için PowerShell'i seçin) ya da Seç… ile "
         "script dosyasını gösterin.",
         "Gerekiyorsa çalışma klasörünü ve zaman aşımını ayarlayın."],
        "${command.output}: çıktı, ${command.error}: hata çıktısı, ${command.code}: bitiş kodu (0 başarılı).",
        "Terminale veya PowerShell'e komut yazmak gibidir; akış komut bitene kadar bekler. Program açmak için "
        "Uygulama, dosya veya adres aç adımını kullanın. Python script'leri için bilgisayarda Python kurulu "
        "olmalıdır."),
    "clipboard.set": guide(
        ["Panoya konacak metni yazın.", "Ardından Klavye kısayolu gönder ile mod+v yapıştırın."]),
    "clipboard.get": guide(
        ["Önce mod+c ile kopyalayın, sonra bu adımı ekleyin."], "Panodaki metin değişkene alınır."),
    # ----- Dosya ve Excel ------------------------------------------------------------
    "file.read_table": guide(
        ["Seç… ile .xlsx veya .csv dosyasını gösterin.", "Ardından Her satır için ekleyip listeyi verin."],
        "${rows}: satır listesi. İlk satırdaki başlıklar alan adı olur: ${row.Tutar}.",
        "Excel'de yaptığınız değişiklikler kaydedilmeden okunmaz."),
    "file.write_table": guide(
        ["Kayıtlar alanına listeyi verin (ör. Listeye ekle ile toplanan ${results}).",
         "Seç… ile kaydedilecek dosyayı belirleyin; Sonuna ekle mevcut satırları korur.",
         "Sonuna eklerken son satırı belirleyen sütunu yazın (ör. A); kayıtlar o sütundaki son dolu satırın altına "
         "gelir."],
        "", "Her alan başlık satırında aynı adı taşıyan sütuna yazılır; yeni alanlar sona eklenir. Tek hücreye veya "
            "formül yazmak için Excel hücresine yaz adımını kullanın. Windows'ta dosya Excel'de açıksa yazılamaz; "
            "önce kapatın."),
    "file.write_cell": guide(
        ["Seç… ile .xlsx dosyasını gösterin ve sayfa adını yazın.",
         "Yazılacak sütunun harfini girin (ör. D).",
         "Satırı seçin: belirli satır numarası, son dolu satır veya son dolu satırın altı. Son satır için hangi "
         "sütunun esas alınacağını yazın (ör. kayıt numarasının olduğu A).",
         "Değeri yazın; formül için Değer türünü Formül yapın."],
        "${excel_cell.cell}: yazılan hücre (ör. D15). ${excel_cell.row}: satır numarası.",
        "Formüller İngilizce işlev adı ve virgülle yazılır: TOPLA yerine SUM, ; yerine virgül. Türkçe Excel dosyayı "
        "açınca kendi dilinde gösterir. Formülün sonucu dosya Excel'de açılıp kaydedilince hesaplanır; Excel / CSV "
        "oku o zamana kadar formül hücresini boş okur. Windows'ta dosya Excel'de açıksa yazılamaz."),
    "file.read_text": guide(["Seç… ile dosyayı gösterin."], "Dosyanın içeriği metin olarak değişkene alınır."),
    "file.write_text": guide(
        ["Dosyayı ve yazılacak metni girin.", "Günlük tutmak için Sonuna ekle seçin."]),
    "file.exists": guide(
        ["Kontrol edilecek yolu yazın veya seçin."],
        "${file_exists}: var mı? Koşul adımında Dolu / doğru ile kontrol edin."),
    "file.list": guide(
        ["Klasörü seçin; gerekiyorsa *.pdf gibi bir desen yazın.", "Ardından Her satır için ile dosyaları tek tek işleyin."],
        "${files}: dosya listesi. Döngüde ${row.path} tam yol, ${row.name} dosya adıdır."),
    "file.operation": guide(
        ["İşlemi seçin: kopyala, taşı / yeniden adlandır, sil veya klasör oluştur.", "Kaynağı ve gerekiyorsa hedefi girin."],
        "", "Sil geri alınamaz. Önce Dosya / klasör var mı? ile kontrol etmek güvenlidir."),
    "file.wait": guide(
        ["Dosyanın oluşacağı klasörü ve adını (veya *.xlsx gibi deseni) yazın.",
         "İndirmeyi veya dışa aktarmayı başlatan adımdan hemen sonra ekleyin."],
        "Hazır olan dosyanın tam yolu."),
    "data.export_csv": guide(
        ["Kayıtlar alanına listeyi verin.", "Dosya adını .csv ile bitirin."],
        "Dosya, çalışma ayrıntısından indirilebilir."),
    # ----- Veri ve metin -------------------------------------------------------------
    "ai.ask": guide(
        ["Ajanlar bölümünde bir sağlayıcı bağlantısı oluşturun; bu adımda bağlantıyı seçin.",
         "Talimatı ve gönderilecek girdiyi yazın. Yapılandırılmış karar gerekiyorsa JSON şemasını girin.",
         "Sonucu kaydeden değişkeni Koşul adımında kullanın; örneğin ${ai_result.karar}."],
        "Şema yoksa metin, şema varsa doğrulanmış JSON döner. Geçersiz yanıt sonuç değişkenine yazılmaz.",
        "Ajan lisansı gerekir. Bulut bağlantısında girdi sağlayıcıya gönderilir; hassas veri için yerel model "
        "seçin. Önizleme dış çağrı yapmaz; sonuç bilinmeyen kalır. Bu adım yalnız elle çalıştırılan akışlarda "
        "kullanılır ve ajanların araç olarak çalıştırdığı akışlara eklenemez."),
    "core.set": guide(
        ["Değişkene bir ad verin (ör. sonuc).", "Değeri yazın: metin, sayı veya başka bir değişken."],
        "${ad}: verdiğiniz değer. Sonraki adımlarda kullanılır.",
        "Tablo adresi gibi birçok adımda geçen değerleri akışın başında bir kez tanımlayın; değişince tek yerden düzeltirsiniz."),
    "data.calculate": guide(
        ["İfadeyi yazın: sayac + 1, round(tutar * 1.2, 2), adet > 0 and durum == 'Bekliyor'.",
         "Değişkenleri adıyla veya ${row.tutar} biçiminde kullanın."],
        "Hesabın sonucu: sayı, metin veya doğru/yanlış.",
        "Sayaç artırmak için çıktı adına aynı değişkeni yazın: sayac = sayac + 1."),
    "text.transform": guide(
        ["Metin alanına işlenecek değeri verin (ör. ${mesaj}).", "İşlemi seçin; altındaki alanlar buna göre değişir."],
        "İşlenmiş metin (bölme işlemlerinde liste, 'İçeriyor mu?' gibi sorularda doğru/yanlış).",
        "OCR ile okunan sayıyı temizlemek için: Desenle değiştir (regex), desen [^0-9], yerine boş."),
    "data.date": guide(
        ["İşlemi seçin: şimdi, biçimlendir, ekle/çıkar, fark veya haftanın günü.",
         "Biçimi yazın: %d.%m.%Y → 02.10.2026, %H:%M → 14:30."],
        "Biçimlenmiş tarih metni (farkta sayı)."),
    "data.list": guide(
        ["Listeyi verin (ör. ${sheet_rows}).", "İşlemi seçin: say, ilk/son öğe, filtrele, sırala, topla, birleştir."],
        "İşleme göre sayı, tek öğe veya yeni liste.",
        "Yalnız BEKLIYOR satırlarını almak için: Filtrele, alan adı durum, Eşittir, BEKLIYOR."),
    "data.append": guide(
        ["Liste adını yazın (ör. results).", "Döngünün içinde her turda eklenecek değeri verin."],
        "", "Döngü bitince listeyi Excel / CSV'ye yaz veya Departman raporu ile dosyaya dökün."),
    # ----- Google Sheets -------------------------------------------------------------
    "sheets.read_cell": guide(
        ["Bağlantıyı seçin, tablo adresini yapıştırın, sayfa adını ve hücreyi yazın."],
        "Hücrenin değeri metin olarak."),
    "sheets.read_rows": guide(
        ["Bağlantıyı seçin (yoksa oluşturun) ve tablo adresini yapıştırın.",
         "Sütunlar bölümünde okunacak sütunları ve akışta kullanacağınız adlarını belirleyin.",
         "Ana alan olarak bir kaydın varlığını belirleyen, dolu olmasını beklediğiniz sütunu seçin.",
         "Ardından Her satır için ekleyin."],
        "${sheet_rows}: satır listesi. Döngüde ${row.alan_adi}; ${row.row_number} gerçek satır numarasıdır.",
        "Sütun adlarında Türkçe harf ve boşluk kullanmayın (fatura_no gibi)."),
    "sheets.read_column": guide(
        ["Bağlantıyı seçin, tablo adresini ve başlangıç hücresini yazın (ör. B2).", "Ardından Her satır için ekleyin."],
        "Satır listesi; döngüde ${row.value} hücrenin değeridir.",
        "Birden fazla sütun gerekiyorsa Sheets satırlarını oku adımını kullanın."),
    "sheets.write_cell": guide(
        ["Bağlantıyı seçin, tablo adresini ve sayfa adını yazın.",
         "Hücreyi yazın; döngüde geçerli satır için C${row.row_number}.",
         "Yazılacak değeri girin (ör. TAMAMLANDI veya ${mesaj})."],
        "", "İşlenen satırın durumunu yazarsanız akış tekrar çalıştığında o satır yeniden işlenmez."),
    "sheets.write": guide(
        ["Bağlantıyı seçin, tablo adresini ve sayfa adını yazın.",
         "Başlangıç hücresini yazın (ör. L${row.row_number}).",
         "Değerleri satır listesi olarak verin: [[\"${baslama}\", \"${bitis}\"]] yan yana iki hücreye yazar."]),
    "mail.read": guide(
        ["Ayarlar → Bağlantılar'da Gelen e-posta (IMAP) bağlantısı oluşturun ve test edin.",
         "Gerekirse gönderen veya konuya göre süzün (ör. Konu içeriyorsa: Fatura).",
         "Sonucu Her satır için döngüsüne verin; içinde ${email.subject}, ${email.from}, ${email.text} ve "
         "${email.attachments} kullanın."],
        "${emails}: e-posta listesi (en eski önce).",
        "Okumak iletiyi okundu yapmaz. Her çalışmada aynı iletileri işlememek için Okunanları okundu olarak işaretle'yi "
        "açın veya Otomasyonlar'daki Yeni e-posta geldiğinde tetikleyicisini kullanın. Gmail'de uygulama şifresi gerekir."),
    "ftp.transfer": guide(
        ["Ayarlar → Bağlantılar'da FTP bağlantısı oluşturun (FTPS önerilir).",
         "İşlemi seçin; uzak yolu başlangıç klasörüne göre, yerel dosyayı tam yol olarak yazın."],
        "${ftp_result}: indirme/yüklemede dosya boyutu, listelemede ${ftp_result.items}.",
        "SFTP (SSH) farklı bir protokoldür ve bu adımla kullanılamaz. Yarım kalan indirme hedef dosyayı bozmaz."),
    "notify.send": guide(
        ["Ayarlar → Bağlantılar'da Mesajlaşma bağlantısı oluşturun: Teams'te kanalın İş Akışları (Workflows) "
         "webhook'u, Slack'te Incoming Webhook adresi.",
         "Mesajı yazın; değişken kullanabilirsiniz."],
        "${message_result.sent}: gönderildi.",
        "Hata olursa mesaj yeniden gönderilmez (iki kez gitmesin diye). Akış hatalarını bildirmek için Hata olursa "
        "bloğunun içinde kullanın."),
    "database.execute": guide(
        ["Ayarlar → Bağlantılar'da veritabanı bağlantısını açın; Kayıt değiştirmeye izin ver'i işaretleyip "
         "değiştirilecek tabloları ve saklı yordamları yazın.",
         "Adımda tek bir komut yazın (ör. UPDATE dbo.siparisler SET durum = ${yeni_durum} WHERE no = ${row.no}).",
         "En fazla değişecek satır sayısını belirleyin; tek kayıt için 1."],
        "${db_result.affected}: değişen satır sayısı; ${db_result.rows}: dönen satırlar.",
        "Komut kendi işleminde çalışır: sınırdan fazla satır değişecekse veya bir hata olursa tamamı geri alınır. "
        "WHERE'siz UPDATE / DELETE, tablo yapısını değiştiren komutlar ve dinamik SQL çalıştırılmaz. Veritabanı "
        "kullanıcısına yalnız gereken tablolarda yazma yetkisi verin."),
    "database.query": guide(
        ["Bağlantı alanından veritabanını seçin; yoksa Yeni bağlantı ile sunucu, kullanıcı ve şifreyi girin.",
         "SQL sorgusunu yazın (ör. SELECT FATURANO, TUTAR FROM FATURALAR WHERE DURUM = ${durum}).",
         "Bu adımı test et ile sonucu kontrol edin."],
        "Satır listesi: her satır sütun adlarıyla gelir. Her satır için ile döngüye verin.",
        "Yalnız okuma yapılır; kayıt ekleyen, değiştiren veya silen sorgular reddedilir. Veritabanında yalnız "
        "okuma yetkisi olan bir kullanıcı kullanın."),
    "database.read": guide(
        ["Bağlantıyı seçin (yoksa oluşturun) ve tabloyu şema.tablo biçiminde yazın.",
         "Gerekiyorsa sütunları ve eşitlik filtrelerini girin."],
        "Kayıt listesi. Her satır için ile döngüye verin.",
        "Yalnız okuma yapılır; veritabanına yazılmaz."),
    # ----- Akış ----------------------------------------------------------------------
    "control.for_each": guide(
        ["Satır listesine okuma adımının çıktısını verin (ör. ${sheet_rows}).",
         "Her satırda yapılacak adımları bu adımın içine ekleyin veya sürükleyin."],
        "İç adımlarda ${row}: geçerli satır, ${row.form_id}: satırın alanı, ${loop_index}: 0'dan başlayan sıra.",
        "Yarıda kalan işi sürdürmek için Kaçıncı satırdan başlasın alanını kullanın. Bazı satırları atlamak "
        "için içine Koşul + Sonraki tura geç ekleyin."),
    "control.while": guide(
        ["Koşulu yazın: sol değer, karşılaştırma, sağ değer.",
         "İç adımlarda koşuldaki değeri değiştiren veya yeniden okuyan bir adım olmalı.",
         "En fazla tekrar ve süre sınırını girin."],
        "", "Koşul hiç değişmezse sınıra ulaşıldığında akış hata ile durur."),
    "core.wait": guide(
        ["Beklenecek süreyi saniye olarak yazın."],
        "", "Ekranın hazır olmasını beklemek için Pencerede görseli bekle daha güvenlidir."),
    "control.if": guide(
        ["Sol değere kontrol edilecek değişkeni yazın (ör. ${row.durum}).",
         "Karşılaştırmayı ve sağ değeri seçin (ör. Eşittir, BEKLIYOR).",
         "Koşul doğruysa ve Değilse dallarına adım ekleyin; bir dal boş kalabilir."],
        "", "Eşittir büyük/küçük harfe ve boşluğa duyarlıdır. OCR metninde İçerir kullanın."),
    "control.repeat": guide(
        ["Tekrar sayısını yazın.", "Tekrarlanacak adımları içine ekleyin."],
        "İç adımlarda ${loop_index}: 0'dan başlayan tur sayısı.",
        "Erken bitirmek için içine Koşul + Döngüden çık ekleyin."),
    "control.try": guide(
        ["Hata verebilecek adımları Dene dalına ekleyin.",
         "Hata olduğunda yapılacakları Hata olursa dalına ekleyin (ör. Sheets'e HATA yaz, mesajı kapat)."],
        "Hata olursa dalında ${error_message}: hatanın açıklaması.",
        "Döngünün içinde kullanın: bir satır hata verse de akış sonraki satırla devam eder."),
    "control.break": guide(
        ["Bir döngünün içine, genellikle bir Koşul dalına ekleyin."],
        "", "Aranan şey bulununca döngüyü bitirmek için. Döngüden sonraki adımla devam edilir."),
    "control.continue": guide(
        ["Bir döngünün içine, genellikle bir Koşul dalına ekleyin."],
        "", "Bu satırın kalan adımları atlanır, sonraki satıra geçilir (ör. durumu BEKLIYOR olmayanları atla)."),
    "control.goto": guide(
        ["Gidilecek adımı listeden seçin; gerideki bir adım da olabilir.",
         "Diyagramda bir kutunun sağındaki çıkış noktasını başka bir kutuya sürükleyerek de bağlayabilirsiniz."],
        "Akış seçilen adımdan devam eder; bu adımla hedef arasındaki adımlar atlanır.",
        "Geri dönüşler Her turda en fazla sayısıyla sınırlıdır; sınıra ulaşılırsa akış sonsuz döngüye girmeden "
        "durur. Bir döngünün içindeki adıma ancak aynı döngünün içinden gidilebilir; dışarıdan döngü kutusuna "
        "bağlayın."),
    "control.run_workflow": guide(
        ["Çalıştırılacak akışı seçin."],
        "", "Değişkenler ortaktır: çağrılan akış bu akışın değişkenlerini görür ve değiştirebilir. "
            "Giriş yapma gibi ortak işleri ayrı bir akışta tutun."),
    "control.stop": guide(
        ["Sonucu (Başarılı / Hata) ve mesajı yazın.", "Genellikle bir Koşul dalına ekleyin."],
        "", "Kalan adımlar çalışmaz. Mesaj çalışma geçmişinde görünür."),
    "core.log": guide(
        ["Notu yazın; değişken değerlerini görmek için ${ad} ekleyin."],
        "", "Akış beklediğiniz gibi çalışmıyorsa değerleri görmek için araya ekleyin."),
    # ----- Kullanıcı etkileşimi ve web -----------------------------------------------
    "ui.message": guide(
        ["Başlığı ve mesajı yazın.", "Onay istenecekse Evet / Hayır seçin."],
        "${answer}: ok, cancel, yes veya no; Otomatik kapanma süresi dolarsa timeout.",
        "Akış, kutu kapatılana kadar bekler. Gözetimsiz çalışacak akışlarda kullanmayın."),
    "ui.input": guide(
        ["Soruyu ve varsa varsayılan değeri yazın.", "Çıktı değişkenine ad verin."],
        "Kullanıcının yazdığı değer.",
        "Her çalıştırmada değişen değerler (tarih, dönem) için akışın başına ekleyin."),
    "http.request": guide(
        ["Firmanızın veya bir hizmetin API'si için API bağlantısı seçin (ana adres ve kimlik doğrulama bir kez "
         "Ayarlar → Bağlantılar'da girilir); yoksa tam adresi yazın.",
         "Yöntemi ve yolu girin (ör. GET /v1/siparisler/${row.no}).",
         "Veri gönderilecekse gövdeyi JSON olarak yazın; değişken kullanabilirsiniz: {\"no\": \"${row.no}\"}."],
        "${response.status}: durum kodu, ${response.body}: yanıt (JSON ise alanlarıyla).",
        "Ekranda yapılan bir işin API'si varsa ekran otomasyonu yerine bu adımı tercih edin: daha hızlıdır ve "
        "pencere değişikliğinden etkilenmez. Kimlik bilgileri yalnız bağlantının kendi sunucusuna gönderilir."),
}

# How a flow is built; shown in the inspector while no step is selected.
QUICK_GUIDE = [
    ["Adım ekleyin", "Kütüphaneden adıma tıklayın veya diyagramdaki + düğmesine basıp adını yazın."],
    ["Adımı ayarlayın", "Adıma tıklayın. Sağda nasıl kullanılacağı ve her alanın açıklaması görünür."],
    ["Hedefi ekrandan seçin", "Tıklama ve yazma adımlarında Ekranda seç ile hedefi gösterin; elle koordinat yazmayın."],
    ["Değerleri bağlayın", "Bir adımın çıktısı sonraki adımda ${ad} olarak kullanılır. Alttaki değişken "
                           "etiketine tıklayınca kopyalanır."],
    ["Yolları bağlayın", "Diyagramda bir kutunun sağındaki noktayı başka bir kutuya sürükleyin: akış oradan devam "
                         "eder, gerideki bir adıma da dönebilir. Çizginin üzerindeki × bağlantıyı kaldırır ve yol "
                         "orada biter. Aynısını adımın Bu adımdan sonra seçimiyle de yapabilirsiniz."],
    ["Adımı test edin", "Bu adımı test et, yalnız o adımı çalıştırır. Pencereyi ve tablodaki ilk satırı kendisi bulur."],
    ["Çalıştırın", "Çalıştır tüm akışı uygular. Diyagramda her adımın üzerinde ✓ veya ✗ görünür."],
    ["Not bırakın", "Shift veya Ctrl/⌘ ile adımları seçin (diyagramda Shift ile sürükleyin) ve Not ekle'ye "
                    "basın. Not, akışın o bölümünü açıklar; çalışmayı etkilemez."],
    ["Zamanlayın", "Zamanla, akışı seçtiğiniz gün ve saatlerde kendiliğinden çalıştırır; Studio açık kalmalıdır."],
]


def apply(entries: list[dict]) -> None:
    """Attach the guide and fill every missing field help."""
    for entry in entries:
        if entry["type"] in GUIDES:
            entry["guide"] = GUIDES[entry["type"]]
        for field in entry["fields"]:
            if not field.get("help"):
                text = STEP_FIELD_HELP.get((entry["type"], field["name"])) or FIELD_HELP.get(field["name"])
                if text:
                    field["help"] = text
