# Adım rehberi

Adım kütüphanesi 63 adımdır ve hareketleriniz kaydedilip adımlara çevrilebilir. Her adım macOS ve Windows'ta aynı biçimde çalışır; işletim sistemine özgü farklar tabloda belirtilmiştir. Kütüphanenin üstündeki **Adım ara** kutusuna "excel", "tıkla", "bekle" gibi bir kelime yazarak adımı bulabilirsiniz.

## Akışı düzenleme

- **Adım eklemek:** Kütüphanedeki adıma tıklayın veya adımı sürükleyip akıştaki istediğiniz yere bırakın.
- **Yer değiştirmek:** Kartı tutup sürükleyin. Kartın üst yarısına bırakırsanız önüne, alt yarısına bırakırsanız arkasına yerleşir. Bir döngünün, koşulun veya **Hata olursa** bloğunun kesikli alanına bırakırsanız o bloğun içine girer. Bir blok kendi içine taşınamaz. Yukarı/aşağı düğmeleri de çalışmaya devam eder.
- **Diyagram görünümü:** Akış alanının sağ üstündeki **Liste / Diyagram** düğmesiyle geçilir; seçim hatırlanır. Diyagramda adımlar soldan sağa düğümlerdir. **Koşul** düğümünden **Doğruysa** ve **Değilse**, **Hata olursa** düğümünden **Dene** ve **Hata olursa** dalları çıkar; dallar sağda birleşip akış devam eder. Döngünün iç adımları **Her öğe** çizgisiyle sağa uzanır, sondan kesikli **Sonraki tur** çizgisiyle döngüye döner; döngü bitince **Bitince** çizgisiyle sonraki adıma geçilir.
  - Çizgilerdeki **+** düğmesi o noktaya adım ekler: açılan kutuda adı yazıp Enter'a basın. Boş dallardaki kesikli kutular da aynı işi görür.
  - **Kutuyu taşımak:** Kutuyu tutup istediğiniz yere sürükleyin; bağlantı çizgileri kutuyu izler ve yeri akışla birlikte kaydedilir. Bu yalnız görünümü değiştirir, adımların çalışma sırasını değiştirmez. Alt + ok tuşları seçili kutuyu 10 piksel (Shift ile 40) kaydırır. Sağ alttaki **Kutuları otomatik diz** düğmesi tüm kutuları otomatik yerlerine döndürür.
  - **Sırayı değiştirmek:** Kutuyu bir **+** düğmesinin veya boş bir dalın üzerine bırakın; adım akışta o noktaya taşınır ve yeniden otomatik dizilir. Kütüphaneden sürüklemek için **Kütüphane** düğmesiyle kütüphaneyi açın.
  - Boş alanı sürükleyerek veya kaydırarak gezinin; Ctrl/⌘ + kaydırma veya sağ alttaki düğmeler yakınlaştırır, ⊞ tümünü sığdırır.
  - Düğümün üzerine gelince test ▶, çoğalt ve sil düğmeleri çıkar. Seçili düğümde Delete tuşu adımı siler.
  - Son çalışmada her düğümün sağ üstünde ✓ (birden çok çalıştıysa kaç kez) veya ✗ (hata verdi) görünür. Çalışma ayrıntısındaki **Diyagramda göster**, o çalışmanın sonuçlarını hatalı adım seçili olarak açar.
- **Bağlantı seçmek:** Google Sheets ve veritabanı adımlarının ilk alanı **Bağlantı**'dır. Listeden bir bağlantı seçin, **+ Yeni … bağlantısı** ile oluşturun veya kalemle düzenleyin. Boş bırakılan adım varsayılan bağlantıyı kullanır. Ayrıntılar: [Google Sheets bağlantısı](google-sheets.md).
- **Çalıştır:** Adımları gerçekten uygular. **Önizleme (ekranı kullanmadan)** işaretliyse fare, klavye, ekran, dosya, bağlantı ve mesaj adımları atlanır; yalnız veri, metin, hesap ve akış adımları çalışır.
- **Nasıl kullanılır? kutusu:** Bir adıma tıkladığınızda sağ panelin üstünde o adımın kısa kullanım özeti çıkar: sırayla ne yapılacağı, adımın ne ürettiği ve bir ipucu. Her alanın altında da ne yazılacağını anlatan bir açıklama vardır. Kutuyu **Gizle** ile kapatabilirsiniz; adım seçili değilken aynı yerde akışın nasıl kurulacağı özetlenir.
- **Bu adımı test et:** Adımı seçin, sağ paneldeki düğmeye basın. Sadece o adım, içinde başka adımlar varsa onlarla birlikte, gerçek olarak çalışır; akışın geri kalanı çalışmaz. Değer yazmanız gerekmez:
  - Adımın ihtiyaç duyduğu değerler önceki adımlardan kendiliğinden alınır. **Pencereyi tanı**, **Değişken ata**, Sheets/Excel/veritabanı okuma ve ekrandan okuma (OCR) gibi yalnız okuyan adımlar test başlarken çalıştırılır.
  - Döngü içindeki adımda `${row}` olarak listenin **ilk satırı** kullanılır. Pencerede hangi değerin nereden alındığı listelenir; sonuçta kullanılan değerler de gösterilir.
  - Farklı bir değerle denemek için **Başka bir değerle denemek istiyorum** bölümünü açıp yalnız o değeri yazın.
  - Yalnız tıklama yapan veya size soru soran bir adımın ürettiği değer otomatik alınamaz; pencere o değeri sorar.
  - **Yeri göster (tıklamadan):** Tıklama, alan doldurma ve görsele tıklama adımlarında pencereyi öne getirip fareyi hedefin üzerine götürür; tıklamaz ve yazmaz. Hedefin doğru seçildiğini böyle kontrol edin. **Gerçekten çalıştır** adımı uygular.
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
| Alanın değerini oku | Alandaki değeri okur. Alan kimliğinde doğrudan okunur. Konum ve görselde alan seçilip kopyalanır, pano eski haline döner. | `${field_value}` |
| Pencerede tuşa bas | Tanıtılan pencereye tuş veya kısayol gönderir. | — |
| Pencerede görseli bekle | Pencerede bir işaretin görünmesini veya kaybolmasını bekler. | — |
| Pencereyi öne getir | Pencereyi öne alır; küçültülmüşse açar. | — |
| Pencereyi büyüt / küçült | Büyütür, küçültür veya geri yükler. | — |
| Pencereyi taşı ve boyutlandır | Pencereyi sabit konum ve boyuta getirir. X/Y hedeflerini sabitlemek için akışın başında kullanın. | Güncel pencere |
| Pencereyi kapat | Kapat düğmesine basar; uygulama kaydetmek isterse sorar. | — |
| Pencerenin kapanmasını bekle | Kayıt, yazdırma veya yükleme penceresi kapanana kadar bekler. | — |

Alan kimliği, konum ve görsel yöntemleri [pencere tanıtma rehberinde](pencere-tanitma.md) anlatılır.

## Fare ve klavye

Bu adımlar ana ekranın koordinatlarını kullanır. **Fare konumunu al (3 sn)** düğmesine basıp 3 saniye içinde fareyi hedefe götürün; X/Y otomatik dolar. Masaüstü uygulamasında Studio bu sırada gizlenir. Pencereye bağlı işlerde **Pencere** adımları daha güvenlidir, çünkü pencere taşınsa da doğru yere tıklarlar.

| Adım | Ne yapar |
| --- | --- |
| Ekranda tıkla | Sol, sağ veya orta düğmeyle tek, çift veya üç tık yapar. |
| Fareyi taşı | İmleci götürür (menü açmak, üzerine gelince açılan listeler). |
| Sürükle ve bırak | Başlangıçtan bitişe basılı tutarak sürükler. İki konum ayrı ayrı alınır. |
| Fare tekerleğiyle kaydır | Dikey veya yatay kaydırır; eksi değer aşağı/sağa kaydırır. |
| Metin yaz | Odaktaki alana yazar. Türkçe karakterler Otomatik yöntemde panodan yapıştırılır; klavye düzeni farkı sorun olmaz. |
| Klavye kısayolu gönder | `mod+s`, `ctrl+shift+esc`, `alt+f4`, `alt+tab` gibi. `mod`, Windows'ta Ctrl, Mac'te Command'dır. |
| Tuşa bas | Enter, Tab, F5, ok tuşları; tekrar sayısı ve bekleme ile. |
| Tuşu basılı tut / bırak | Shift veya Ctrl basılıyken tıklama (çoklu seçim) için. Akış bittiğinde veya hata verdiğinde basılı kalan tuşlar otomatik bırakılır. |
| Fare konumunu oku | İmlecin konumunu `${mouse.x}`, `${mouse.y}` olarak kaydeder. |

## Ekran ve görsel

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Ekranda görsel ara / bekle | Görselin görünmesini veya kaybolmasını bekler. Süre dolunca akışı durdurur ya da "bulunamadı" sonucuyla devam eder. | `${image.found}`, `${image.center_x}`, `${image.center_y}` |
| Ekranda görsele tıkla | Görseli bulup tıklar; merkezden fark verilebilir. | Bulunan konum |
| Ekrandan metin oku (OCR) | Bölgedeki yazıyı okur. | `${screen_text}` |
| Ekranda metni bekle | "Kaydedildi" gibi bir yazı görünene kadar bekler. i/İ/ı/I ve büyük/küçük harf farkı gözetilmez. | `${text_found}` |
| Piksel rengini oku | Bir noktanın rengini `#RRGGBB` olarak okur. | `${pixel}` |
| Ekran görüntüsü al | Ekranı veya bölgeyi PNG olarak çalışma çıktılarına ve isterseniz bir klasöre kaydeder. | Dosya yolu |

- **Görsel:** **Ekrandan görsel seç** düğmesine basın. Geri sayımdan sonra ekran yakalanır; aranacak ikon veya düğmeyi fareyle çevreleyin. **Ekranda görsele tıkla** adımında ardından tıklanacak noktayı da seçebilirsiniz.
- **Bölge:** **Bölgeyi fareyle al** ile önce sol üst, sonra sağ alt köşeyi gösterin. **Bölge neye göre? = Tanıtılan pencere** seçerseniz bölge pencereye göre saklanır; ERP penceresi taşınsa da doğru yer okunur.
- **OCR:** Ek kurulum gerekmez. macOS'ta Apple Vision, Windows'ta Windows OCR kullanılır ve Türkçe desteklenir. Windows'ta Türkçe veya İngilizce dil paketinin yüklü olması gerekir; çoğu kurulumda zaten vardır. Tesseract kuruluysa yedek olarak kullanılır.

## Uygulama ve sistem

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Uygulama, dosya veya adres aç | Windows: `notepad.exe`, `excel.exe`, `C:\Rapor.xlsx` · Mac: `TextEdit`, `Microsoft Excel`, `~/Desktop/rapor.xlsx` · `https://…` | — |
| Uygulamayı kapat | Windows: `EXCEL.EXE` · Mac: `Microsoft Excel`. Zorla kapatma kaydedilmemiş işi kaybettirir. | Kapatıldı mı |
| Komut çalıştır | Windows'ta cmd, Mac'te terminal komutu. Çıktı `${command.output}`, kod `${command.code}`. | `${command}` |
| Panoya kopyala / Panodaki metni oku | Pano üzerinden veri aktarır. | `${clipboard}` |

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

## Akış

| Adım | Ne yapar |
| --- | --- |
| Koşul | Evet ve Değilse dalları. |
| Her satır için | Listedeki her öğe için iç adımlar (en fazla 100.000 öğe). |
| Tekrarla (N kez) | İç adımları N kez çalıştırır; `${loop_index}` 0'dan başlar. |
| Koşul sürdükçe tekrarla | Koşul doğru oldukça tekrarlar; tekrar ve süre sınırı vardır. |
| Döngüden çık / Sonraki tura geç | En içteki döngüyü bitirir veya turu atlar. Yalnız döngü içinde eklenebilir. |
| Hata olursa | **DENE** dalında hata olursa akışı durdurmak yerine **HATA OLURSA** dalını çalıştırır. Mesaj `${error_message}` içindedir. Örneğin hatalı satırı Excel'e "Hata" olarak işaretleyip sonraki satıra geçmek için kullanılır. |
| Başka akışı çalıştır | Kayıtlı bir akışı bu noktada çalıştırır; değişkenler ortaktır. ERP'ye giriş gibi ortak işleri tek yerde tutun. En fazla 5 seviye olabilir ve akış kendini çağıramaz. |
| Akışı bitir | Başarıyla veya hata mesajıyla sonlandırır. |
| Bekle / Çalışma notu | Sabit bekleme; günlüğe değer yazma. |

Bir akış en fazla 1.000 adım ve 12 seviye iç içe blok içerebilir. Bir çalışma en fazla 1.000.000 adım çalıştırır.

## Kullanıcı etkileşimi ve web

| Adım | Ne yapar | Sonuç |
| --- | --- | --- |
| Mesaj kutusu göster | Tamam, Tamam/İptal veya Evet/Hayır; yanıt beklenir. | `${answer}`: `ok`, `cancel`, `yes`, `no` |
| Kullanıcıdan değer iste | Çalışma sırasında tarih veya fatura no gibi bir değer sorar. | `${user_input}` |
| HTTP isteği gönder (API) | GET/POST/PUT/PATCH/DELETE; JSON gövde ve başlıklarla. | `${response.status}`, `${response.body}` |

## AutoHotkey karşılıkları

| AutoHotkey | RpaOrkestrAI |
| --- | --- |
| `Click`, `MouseMove`, `MouseClickDrag` | Ekranda tıkla, Fareyi taşı, Sürükle ve bırak |
| `Send`, `SendText`, `Send {Enter 3}` | Metin yaz, Klavye kısayolu gönder, Tuşa bas |
| `WinActivate`, `WinWait`, `WinWaitClose`, `WinMaximize`, `WinMove`, `WinClose` | Pencereyi tanı, Pencereyi öne getir, Pencerenin kapanmasını bekle, Pencereyi büyüt / küçült, Pencereyi taşı ve boyutlandır, Pencereyi kapat |
| `ControlSetText`, `ControlGetText`, `ControlClick` | Alanı doldur, Alanın değerini oku, Pencerede tıkla (alan kimliğiyle) |
| `ImageSearch`, `PixelGetColor` | Ekranda görsel ara / bekle, Ekranda görsele tıkla, Piksel rengini oku |
| `Run`, `RunWait`, `WinClose` / `ProcessClose` | Uygulama, dosya veya adres aç; Komut çalıştır; Uygulamayı kapat |
| `FileRead`, `FileAppend`, `Loop Files`, `FileCopy`, `FileMove`, `FileDelete` | Dosya ve Excel adımları |
| `A_Clipboard` | Panoya kopyala / Panodaki metni oku |
| `MsgBox`, `InputBox` | Mesaj kutusu göster, Kullanıcıdan değer iste |
| Macro Recorder | Hareketleri kaydet |
| `Loop`, `Loop Parse`, `while`, `break`, `continue`, `try/catch`, `Gosub` | Tekrarla, Her satır için, Koşul sürdükçe tekrarla, Döngüden çık, Sonraki tura geç, Hata olursa, Başka akışı çalıştır |
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
