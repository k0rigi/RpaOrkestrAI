"""The action catalog also drives the Studio's parameter forms."""

from __future__ import annotations

from typing import Any


def field(name: str, label: str, kind: str = "text", default: Any = "", **kwargs: Any) -> dict:
    return {"name": name, "label": label, "type": kind, "default": default, **kwargs}


def action(kind: str, label: str, category: str, description: str, fields: list, **kwargs: Any) -> dict:
    return {"type": kind, "label": label, "category": category, "description": description,
            "fields": fields, **kwargs}


OUTPUT = field("output", "Sonucu değişkene kaydet", default="result", required=True,
               help="Sonraki adımda ${result} ile kullanın.")
REGION = field("region", "Ekran bölgesi [x, y, genişlik, yükseklik]", "json", None,
               help="Boş/null: ana ekran. Mantıksal ekran koordinatları.")
OPERATORS = [
    {"value": "eq", "label": "Eşittir"}, {"value": "ne", "label": "Eşit değildir"},
    {"value": "contains", "label": "İçerir (harf duyarsız)"},
    {"value": "gt", "label": "Büyüktür"}, {"value": "gte", "label": "Büyük veya eşittir"},
    {"value": "lt", "label": "Küçüktür"}, {"value": "lte", "label": "Küçük veya eşittir"},
    {"value": "truthy", "label": "Dolu / doğru"},
    {"value": "empty", "label": "Boş"}, {"value": "not_empty", "label": "Boş değil"},
    {"value": "empty_or_eq", "label": "Boş veya eşittir"},
    {"value": "one_of", "label": "Listedeki değerlerden biri"},
]

WINDOW = field("window", "Pencere değişkeni", default="${erp_window}", required=True)
SHEET_ID = field("spreadsheet_id", "Google Sheets adresi veya kimliği", required=True,
                 help="Tablonun tam bağlantısını yapıştırabilirsiniz. Servis hesabıyla paylaşılmış olmalıdır.")


def image_fields() -> list[dict]:
    return [
        field("template", "Referans görsel", required=True, help="Ekrandan seçerek kaydedin veya şablon dosya adını yazın."),
        field("confidence", "Eşleşme eşiği", "number", 0.9, min=0.5, max=1, step=0.01),
        field("timeout", "En fazla bekle (saniye)", "number", 10, min=0.1, max=120, step=0.1),
    ]


def target_fields() -> list[dict]:
    # The wait applies to both searched targets; X/Y is used immediately.
    searched = {"target_mode": ["image", "element"]}
    return [
        field("target_mode", "Hedefi bulma yöntemi", "select", "coordinates", required=True,
              options=[{"value": "coordinates", "label": "Pencere içi X / Y"},
                       {"value": "image", "label": "Referans görsel"},
                       {"value": "element", "label": "Alan kimliği (uygulama yapısı)"}]),
        field("x", "Pencere içi X", "number", None, min=0, required=True,
              visible_when={"target_mode": "coordinates"}, help="Ekrandan hedef seç ile otomatik doldurabilirsiniz."),
        field("y", "Pencere içi Y", "number", None, min=0, required=True,
              visible_when={"target_mode": "coordinates"}),
        field("element", "Alan kimliği", "element", None, required=True, visible_when={"target_mode": "element"},
              help="Ekranda seç → Konum ile alınır. Alan, pencere boyutu veya ekran ölçeği değişse de "
                   "uygulamanın kimliğiyle bulunur."),
        *[{**f, "visible_when": searched if f["name"] == "timeout" else {"target_mode": "image"}}
          for f in image_fields()],
        field("offset_x", "Görsel merkezinden sağa / sola", "number", 0,
              visible_when={"target_mode": "image"}, help="FormID etiketi ile yazı alanı arasındaki yatay fark."),
        field("offset_y", "Görsel merkezinden aşağı / yukarı", "number", 0,
              visible_when={"target_mode": "image"}),
    ]

# Existing workflows still need these definitions for editing and execution.
# New library actions are introduced in CATALOG as requirements are agreed.
ACTION_DEFINITIONS = [
    action("sheets.read_column", "Sheets sütununu oku", "Google Sheets",
           "B2, B3, B4 gibi bir sütundaki değerleri satır bilgileriyle listeye alır. Ardından döngü ekleyin.",
           [SHEET_ID, field("worksheet", "Sayfa adı", default="Sayfa1", required=True),
            field("start_cell", "Başlangıç hücresi", default="B2", required=True),
            field("max_rows", "En fazla kaç satır okunsun?", "number", 100, min=1, max=1000, required=True),
            field("empty_policy", "Boş hücreyle karşılaşınca", "select", "stop", required=True,
                  options=[{"value": "stop", "label": "Okumayı bitir"}, {"value": "skip", "label": "Atla ve devam et"}]),
            field("output", "Satır listesi değişkeni", default="sheet_rows", required=True,
                  help="Her satır için adımına ${sheet_rows} verin. Liste bir kez okunur.")]),
    action("desktop.window_write", "Odaktaki alana yaz (eski)", "Pencere",
           "Eski akışlarla uyumluluk için odaktaki alana ekler. Hedef seçmek için Alanı doldur adımına geçin.",
           [WINDOW, field("text", "Yazılacak metin", default="${cell_value}", required=True)]),
    action("data.sample", "Örnek siparişler", "Veri", "Bağlantı gerektirmeyen örnek veri oluşturur.",
           [field("output", "Veri değişkeni", default="orders", required=True)]),
    action("core.set", "Değişken oluştur", "Veri", "Bir metin, sayı veya JSON değeri saklar.",
           [field("name", "Değişken adı", default="value", required=True),
            field("value", "Değer", "json", "")]),
    action("data.append", "Listeye ekle", "Veri", "Bir kaydı sonuç listesine ekler; liste yoksa oluşturur.",
           [field("name", "Liste değişkeni", default="results", required=True),
            field("value", "Eklenecek değer", "json", "${item}")]),
    action("data.export_csv", "Departman raporu", "Çıktı", "Kayıtları indirilebilir, Excel uyumlu CSV'ye yazar.",
           [field("rows", "Kayıtlar", "json", "${orders}", required=True),
            field("filename", "Dosya adı", default="rapor.csv", required=True)]),
    action("control.for_each", "Her kayıt için", "Akış", "Listedeki her değer için alt adımları çalıştırır.",
           [field("items", "Döngü listesi", "json", "${orders}", required=True),
            field("item_name", "Geçerli kayıt değişkeni", default="item", required=True)], container="loop"),
    action("control.if", "Koşul", "Akış", "Koşula göre Evet veya Değilse dalını çalıştırır.",
           [field("left", "Sol değer", "json", "${item.amount}"),
            field("operator", "Karşılaştırma", "select", "gte", options=OPERATORS),
            field("right", "Sağ değer", "json", 1000)], container="condition"),
    action("core.wait", "Bekle", "Akış", "İptal edilebilir süreli bekleme.",
           [field("seconds", "Saniye", "number", 1)]),
    action("core.log", "Çalışma notu", "Akış", "Çalışma günlüğüne bir not ekler.",
           [field("message", "Not", default="Adım tamamlandı.", required=True,
                  help="Günlüğe hassas iş verisi veya parola yazmayın.")]),
    action("database.read", "Tablo oku", "Veritabanı", "İzin verilen tablodan salt okunur veri alır.",
           [field("table", "Şema.Tablo", default="public.IASSALITEM", required=True),
            field("columns", "Sütun listesi (null: tümü)", "json", None),
            field("filters", "Eşitlik filtreleri", "json", {}),
            field("limit", "Azami satır", "number", 1000),
            field("output", "Veri değişkeni", default="orders", required=True)]),
    action("desktop.click", "Koordinata tıkla", "Masaüstü", "Ana ekrandaki mantıksal koordinata tıklar.",
           [field("x", "X", "number", 100), field("y", "Y", "number", 100)]),
    action("desktop.write", "Metin yaz", "Masaüstü", "Aktif alana metin yazar.",
           [field("text", "Metin", default="", required=True)]),
    action("desktop.hotkey", "Klavye kısayolu", "Masaüstü", "mod tuşu macOS'ta Command, Windows'ta Ctrl olur.",
           [field("keys", "Tuşlar", "json", ["mod", "a"], required=True)]),
    action("desktop.press", "Tuşa bas", "Masaüstü", "Enter, Tab, aşağı ok gibi bir tuşa basar.",
           [field("key", "Tuş", default="enter", required=True)]),
    action("desktop.click_template", "Görseli bul ve tıkla", "Masaüstü", "Şablonu bekler ve merkezine tıklar.",
           [field("template", "Şablon dosyası", default="buton.png", required=True), REGION,
            field("confidence", "Eşleşme eşiği", "number", 0.85)]),
    action("desktop.ocr", "Ekrandan metin oku", "Algılama", "OCR ile hata, onay veya ekran metnini okur.",
           [REGION, field("output", "Metin değişkeni", default="screen_text", required=True)]),
    action("desktop.scan_dropdown", "Liste seçeneklerini tara", "Algılama",
           "Açılmış listeyi OCR ile okuyup kaydırır; benzersiz satırları toplar.",
           [field("region", "Liste bölgesi [x, y, genişlik, yükseklik]", "json", [100, 100, 240, 300],
                  required=True), field("scroll_amount", "Kaydırma adımı", "number", -3),
            field("max_scrolls", "Azami kaydırma", "number", 20),
            field("output", "Seçenekler değişkeni", default="options", required=True)]),
    action("browser.open", "Web sayfası aç", "Web", "Arka planda Chromium oturumu açar.",
           [field("url", "Adres", default="https://example.com", required=True)]),
    action("browser.fill", "Web alanını doldur", "Web", "CSS veya Playwright seçicisiyle alan doldurur.",
           [field("selector", "Seçici", default='input[name="q"]', required=True),
            field("value", "Değer", required=True)]),
    action("browser.click", "Web öğesine tıkla", "Web", "Seçilen web öğesine tıklar.",
           [field("selector", "Seçici", default='button[type="submit"]', required=True)]),
    action("browser.text", "Web metnini al", "Web", "Seçilen öğenin metnini değişkene aktarır.",
           [field("selector", "Seçici", default="h1", required=True), OUTPUT]),
    action("sheets.read", "Sheets aralığını oku", "Google Sheets", "Bir hücre veya aralıktaki değerleri alır.",
           [field("spreadsheet_id", "Elektronik tablo kimliği", required=True),
            field("worksheet", "Sayfa adı", default="Sheet1", required=True),
            field("range", "Hücre / aralık", default="A1:C10", required=True), OUTPUT]),
    action("sheets.write", "Sheets aralığına yaz", "Google Sheets", "Hücre veya aralığa RAW değerleri yazar.",
           [field("spreadsheet_id", "Elektronik tablo kimliği", required=True),
            field("worksheet", "Sayfa adı", default="Sheet1", required=True),
            field("range", "Başlangıç hücresi / aralık", default="A1", required=True),
            field("values", "Satır matrisi", "json", [["Örnek", 1]], required=True)]),
]

CATALOG: list[dict[str, Any]] = [
    action("desktop.find_window", "Pencereyi tanı", "Pencere",
           "Açık masaüstü penceresini uygulama ve başlığıyla bulur. Sonucu diğer adımlarda kullanın.",
           [field("application", "Uygulama adı", help="Açık pencerelerden seçebilirsiniz. Boşsa tüm uygulamalarda arar."),
            field("title", "Pencere başlığı", required=True,
                  help="Değişen belge numaraları varsa sabit kısmı yazıp İçerir seçin."),
            field("match", "Başlık eşleşmesi", "select", "exact", required=True,
                  options=[{"value": "exact", "label": "Tam eşleşme"},
                           {"value": "contains", "label": "İçerir"}]),
            field("timeout", "En fazla bekle (saniye)", "number", 5, min=0, max=120),
            field("on_missing", "Pencere bulunamazsa", "select", "stop", required=True,
                  options=[{"value": "stop", "label": "Akışı durdur"},
                           {"value": "continue", "label": "Bulunamadı sonucu ile devam et"}]),
            field("output", "Pencere değişkeni", default="erp_window", required=True,
                  help="${erp_window.found}: açık mı? Diğer pencere adımlarına ${erp_window} verin.")]),
    action("desktop.window_click", "Pencerede tıkla", "Pencere",
           "Bir butonu veya alanı konumuyla ya da görseliyle bulup tıklar; metin yazmaz.",
           [WINDOW, *target_fields(),
            field("clicks", "Tıklama sayısı", "select", 1,
                  options=[{"value": 1, "label": "Tek tık"}, {"value": 2, "label": "Çift tık"}]),
            field("button", "Fare düğmesi", "select", "left",
                  options=[{"value": "left", "label": "Sol"}, {"value": "right", "label": "Sağ"}])]),
    action("desktop.window_fill", "Alanı doldur", "Pencere",
           "Hedef yazı alanını bulur, tıklar ve verilen değeri yazar. Ayrıca tıklama adımı eklemeniz gerekmez.",
           [WINDOW, *target_fields(),
            field("text", "Yazılacak değer", default="${row.value}", required=True,
                  help="Tablo satırında ${row.form_id}; eski sütun adımında ${row.value}; tek hücrede ${cell_value}."),
            field("clear", "Önce alandaki mevcut değeri temizle", "boolean", True)]),
    action("desktop.window_key", "Pencerede tuşa bas", "Pencere",
           "Tanıtılan pencerede Enter, Tab veya bir klavye kısayolu gönderir; alan aramaz.",
           [WINDOW, field("key", "Tuş", "select", "enter", required=True,
                          options=[{"value": key, "label": label} for key, label in [
                              ("enter", "Enter"), ("tab", "Tab"), ("esc", "Escape"),
                              ("down", "Aşağı ok"), ("up", "Yukarı ok"), ("left", "Sol ok"),
                              ("right", "Sağ ok"), ("space", "Boşluk"), ("backspace", "Backspace"),
                              ("delete", "Delete"), ("home", "Home"), ("end", "End"),
                              *[(f"f{i}", f"F{i}") for i in range(1, 13)],
                              ("a", "A"), ("c", "C"), ("v", "V"), ("s", "S")]]),
            field("modifier", "Birlikte basılacak tuş", "select", "none",
                  options=[{"value": value, "label": label} for value, label in [
                      ("none", "Yok"), ("mod", "Ctrl (Windows) / Command (Mac)"),
                      ("shift", "Shift"), ("alt", "Alt / Option"), ("ctrl", "Ctrl")]])]),
    action("desktop.window_wait_image", "Pencerede görseli bekle", "Pencere",
           "Sonraki işleme geçmeden önce bir işaretin görünmesini veya kaybolmasını bekler; tıklamaz.",
           [WINDOW, *image_fields(), field("state", "Beklenen durum", "select", "visible",
                                          options=[{"value": "visible", "label": "Görünsün"},
                                                   {"value": "hidden", "label": "Kaybolsun"}])]),
    action("sheets.read_cell", "Sheets hücresini oku", "Google Sheets",
           "Bir Google Sheets hücresinin değerini metin olarak alır; yazma adımına aktarabilirsiniz.",
           [SHEET_ID,
            field("worksheet", "Sayfa adı", default="Sheet1", required=True),
            field("cell", "Hücre", default="A2", required=True),
            field("allow_empty", "Boş hücreyi hata vermeden oku", "boolean", False,
                  help="Açıkken boş hücre boş metin olur; sonraki Koşul adımında kontrol edebilirsiniz."),
            field("output", "Değer değişkeni", default="cell_value", required=True)]),
    action("sheets.read_rows", "Sheets satırlarını oku", "Google Sheets",
           "FormID ve durum gibi sütunları aynı kayıtta okur. Durum boş olsa da satırı korur.",
           [SHEET_ID, field("worksheet", "Sayfa adı", default="Sayfa1", required=True),
            field("start_row", "Başlangıç satırı", "number", 2, min=1, max=1000000, required=True),
            field("max_rows", "En fazla kaç satır okunsun?", "number", 100, min=1, max=1000, required=True),
            field("columns", "Okunacak sütunlar", "columns", {"form_id": "B", "status": "C"}, required=True,
                  help="B → form_id, C → status. Döngüde ${row.form_id} ve ${row.status} kullanın."),
            field("key", "Kaydın ana alanı", default="form_id", required=True,
                  help="Satırın varlığını bu alan belirler; durum alanının boş olması kaydı elemez."),
            field("empty_policy", "Ana alan boşsa", "select", "stop", required=True,
                  options=[{"value": "stop", "label": "Okumayı bitir"},
                           {"value": "skip", "label": "Satırı atla, devam et"}]),
            field("output", "Satır listesi değişkeni", default="sheet_rows", required=True)]),
    action("sheets.write_cell", "Sheets hücresine yaz", "Google Sheets",
           "İşlem sonucunu tek hücreye kaydeder. Örneğin geçerli satırın C sütununa Tamamlandı yazın.",
           [SHEET_ID, field("worksheet", "Sayfa adı", default="Sayfa1", required=True),
            field("cell", "Yazılacak hücre", default="C${row.row_number}", required=True),
            field("value", "Yazılacak değer", default="Tamamlandı", required=True,
                  help="Formül çalıştırmadan metin olarak kaydedilir. Başarıyı doğrulayan adımlardan sonra ekleyin.")]),
    action("control.for_each", "Her satır için", "Akış",
           "Listedeki her satır için içine eklediğiniz adımları sırayla çalıştırır; liste bitince sona erer.",
           [field("items", "Satır listesi", "json", "${sheet_rows}", required=True),
            field("item_name", "Geçerli satır değişkeni", default="row", required=True,
                  help="Tablo satırında ${row.form_id} ve ${row.status}; ${row.row_number} gerçek satır numarasıdır.")], container="loop"),
    action("control.while", "Koşul sürdükçe tekrarla", "Akış",
           "Koşulu her turda yeniden değerlendirir. Koşul yanlışsa çıkar; sınıra ulaşırsa hata ile durur.",
           [field("left", "Sol değer", "json", "${status}"),
            field("operator", "Karşılaştırma", "select", "ne", options=OPERATORS, required=True),
            field("right", "Sağ değer", "json", "Tamamlandı"),
            field("max_iterations", "En fazla tekrar", "number", 10, min=1, max=1000, required=True),
            field("max_seconds", "Toplam süre sınırı (saniye)", "number", 120, min=1, max=3600, required=True,
                  help="Sınır adımlar arasında kontrol edilir. İç adımların kendi zaman aşımını da ayarlayın.")],
           container="loop"),
    action("core.wait", "Bekle", "Akış", "Adımlar arasında belirli bir süre bekler; ekranı kontrol etmez.",
           [field("seconds", "Saniye", "number", 1, min=0, max=300)]),
    action("control.if", "Koşul", "Akış", "Koşula göre Evet veya Değilse dalını çalıştırır.",
           [field("left", "Sol değer", "json", "${erp_window.found}"),
            field("operator", "Karşılaştırma", "select", "truthy", options=OPERATORS, required=True),
            field("right", "Sağ değer", "json", True)], container="condition"),
]
BY_TYPE = {entry["type"]: entry for entry in ACTION_DEFINITIONS + CATALOG}
EXTERNAL_PREFIXES = ("database.", "desktop.", "browser.", "sheets.")


def library_catalog() -> list[dict[str, Any]]:
    return CATALOG


def defaults(action_type: str) -> dict[str, Any]:
    return {f["name"]: f["default"] for f in BY_TYPE[action_type]["fields"]}
