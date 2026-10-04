"""The action catalog also drives the Studio's parameter forms."""

from __future__ import annotations

import re
from typing import Any

from .guide import apply as apply_guides
from .models import NAME_PARAMETERS, NAMING_ACTIONS


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

WINDOW = field("window", "Pencere", default="${erp_window}", required=True)
SHEETS_CONNECTION = field("connection", "Google Sheets bağlantısı", "connection", "", connection_type="google_sheets",
                          help="Boş bırakılırsa varsayılan Google Sheets bağlantısı kullanılır.")
DATABASE_CONNECTION = field("connection", "Veritabanı bağlantısı", "connection", "", connection_type="database",
                            help="Boş bırakılırsa varsayılan veritabanı bağlantısı kullanılır.")
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
           [SHEETS_CONNECTION, SHEET_ID, field("worksheet", "Sayfa adı", default="Sayfa1", required=True),
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
           [DATABASE_CONNECTION, field("table", "Şema.Tablo", default="public.IASSALITEM", required=True),
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
           [SHEETS_CONNECTION, field("spreadsheet_id", "Elektronik tablo kimliği", required=True),
            field("worksheet", "Sayfa adı", default="Sheet1", required=True),
            field("range", "Hücre / aralık", default="A1:C10", required=True), OUTPUT]),
    action("sheets.write", "Sheets aralığına yaz", "Google Sheets", "Hücre veya aralığa RAW değerleri yazar.",
           [SHEETS_CONNECTION, field("spreadsheet_id", "Elektronik tablo kimliği", required=True),
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
            field("output", "Pencereye verilecek ad", default="erp_window", required=True,
                  help="Yalnız adı yazın (ör. erp_window). Sonraki pencere adımlarının Pencere alanında bu adla "
                       "seçilir.")]),
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
    action("desktop.window_wait_image", "Pencerede görseli bekle / ara", "Pencere",
           "Bir işaretin (düğme, başlık, hata kutusu) pencerede görünmesini veya kaybolmasını bekler; tıklamaz. "
           "Bulunup bulunmadığını Koşul adımında kullanmak için sonucu kaydeder.",
           [WINDOW, *image_fields(), field("state", "Beklenen durum", "select", "visible",
                                          options=[{"value": "visible", "label": "Görünsün"},
                                                   {"value": "hidden", "label": "Kaybolsun"}]),
            field("on_missing", "Süre dolarsa", "select", "stop", required=True,
                  options=[{"value": "stop", "label": "Akışı durdur"},
                           {"value": "continue", "label": "Devam et (sonuç: bulunamadı)"}]),
            field("output", "Sonucu değişkene kaydet", default="image", required=True)]),
    action("sheets.read_cell", "Sheets hücresini oku", "Google Sheets",
           "Bir Google Sheets hücresinin değerini metin olarak alır; yazma adımına aktarabilirsiniz.",
           [SHEETS_CONNECTION, SHEET_ID,
            field("worksheet", "Sayfa adı", default="Sheet1", required=True),
            field("cell", "Hücre", default="A2", required=True),
            field("allow_empty", "Boş hücreyi hata vermeden oku", "boolean", False,
                  help="Açıkken boş hücre boş metin olur; sonraki Koşul adımında kontrol edebilirsiniz."),
            field("output", "Değer değişkeni", default="cell_value", required=True)]),
    action("sheets.read_rows", "Sheets satırlarını oku", "Google Sheets",
           "FormID ve durum gibi sütunları aynı kayıtta okur. Durum boş olsa da satırı korur.",
           [SHEETS_CONNECTION, SHEET_ID, field("worksheet", "Sayfa adı", default="Sayfa1", required=True),
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
           [SHEETS_CONNECTION, SHEET_ID, field("worksheet", "Sayfa adı", default="Sayfa1", required=True),
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
MOUSE_BUTTONS = [{"value": "left", "label": "Sol"}, {"value": "right", "label": "Sağ"},
                 {"value": "middle", "label": "Orta"}]
CLICKS = [{"value": 1, "label": "Tek tık"}, {"value": 2, "label": "Çift tık"}, {"value": 3, "label": "Üç tık"}]
KEYS = [{"value": key, "label": label} for key, label in [
    ("enter", "Enter"), ("tab", "Tab"), ("esc", "Escape"), ("space", "Boşluk"), ("backspace", "Backspace"),
    ("delete", "Delete"), ("insert", "Insert"), ("up", "Yukarı ok"), ("down", "Aşağı ok"), ("left", "Sol ok"),
    ("right", "Sağ ok"), ("home", "Home"), ("end", "End"), ("pageup", "Page Up"), ("pagedown", "Page Down"),
    *[(f"f{i}", f"F{i}") for i in range(1, 13)], ("shift", "Shift"), ("ctrl", "Ctrl"), ("alt", "Alt / Option"),
    ("mod", "Ctrl (Windows) / Command (Mac)"), ("win", "Windows tuşu"), ("command", "Command (Mac)"),
    ("capslock", "Caps Lock"), ("printscreen", "Print Screen"),
    *[(c, c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"]]]


def output(default: str, help_text: str = "") -> dict:
    return field("output", "Sonucu değişkene kaydet", default=default, required=True,
                 help=help_text or f"Sonraki adımlarda ${{{default}}} ile kullanın.")


def point_fields(prefix: str = "", label: str = "", required: bool = True) -> list[dict]:
    return [field(f"{prefix}x", f"{label}X (ekran)", "number", None, min=0, required=required,
                  help="Fare konumunu al ile otomatik doldurabilirsiniz."),
            field(f"{prefix}y", f"{label}Y (ekran)", "number", None, min=0, required=required)]


def area_fields(required: bool = False) -> list[dict]:
    return [
        field("relative_to", "Bölge neye göre?", "select", "screen", required=True,
              options=[{"value": "screen", "label": "Ana ekran"},
                       {"value": "window", "label": "Tanıtılan pencere (pencere taşınsa da doğru kalır)"}]),
        field("window", "Pencere", default="${erp_window}", required=True,
              visible_when={"relative_to": "window"}),
        field("region", "Bölge [x, y, genişlik, yükseklik]", "json", None, required=required,
              help="Boş bırakılırsa tüm ekran/pencere kullanılır. Bölgeyi fareyle al düğmesiyle seçebilirsiniz."),
    ]


FILE_HELP = "Tam yol: C:\\Raporlar\\liste.xlsx veya ~/Desktop/liste.xlsx. %USERPROFILE% ve ~ kullanılabilir."
LIBRARY = [
    # ----- Pencere -------------------------------------------------------------------
    action("window.activate", "Pencereyi öne getir", "Pencere",
           "Tanıtılan pencereyi öne alır; küçültülmüşse geri açar. Klavye adımlarından önce kullanın.", [WINDOW]),
    action("window.read_field", "Alanın değerini oku", "Pencere",
           "Bir yazı alanındaki değeri okur. Alan kimliğinde doğrudan okunur; konum/görselde alan seçilip kopyalanır "
           "(pano eski haline döner).", [WINDOW, *target_fields(), output("field_value")]),
    action("window.read_table", "Tablodan değer oku", "Pencere",
           "ERP listesindeki (tablodaki) bir hücreyi sütun adıyla okur; kaç satır bulunduğunu da verir. "
           "Tabloya tıklayıp tamamını kopyalar ve ayrıştırır; pano eski haline döner.",
           [WINDOW, *target_fields(),
            field("mode", "Ne okunacak", "select", "value", required=True,
                  options=[{"value": "value", "label": "Bir hücrenin değeri"},
                           {"value": "count", "label": "Kaç satır var?"}]),
            field("column", "Sütun", required=True, visible_when={"mode": "value"}),
            field("row", "Satır", "number", 1, min=1, max=10000, required=True, visible_when={"mode": "value"}),
            field("header", "İlk satır sütun başlıklarıdır", "boolean", True),
            output("table_value")]),
    action("window.state", "Pencereyi büyüt / küçült", "Pencere",
           "Pencereyi tam ekran yapar, simge durumuna küçültür veya geri yükler.",
           [WINDOW, field("state", "İşlem", "select", "maximize", required=True,
                          options=[{"value": "maximize", "label": "Büyüt (ekranı kapla)"},
                                   {"value": "minimize", "label": "Küçült"},
                                   {"value": "restore", "label": "Geri yükle"}])]),
    action("window.move", "Pencereyi taşı ve boyutlandır", "Pencere",
           "Pencereyi ana ekranda sabit bir konuma ve boyuta getirir; X/Y hedeflerini sabitlemek için kullanışlıdır.",
           [WINDOW, field("x", "Sol (X)", "number", 0, required=True), field("y", "Üst (Y)", "number", 0, required=True),
            field("width", "Genişlik", "number", 1280, min=100, required=True),
            field("height", "Yükseklik", "number", 800, min=60, required=True),
            output("erp_window", "Güncel pencere bilgisi; çoğunlukla aynı pencere değişkenine yazılır.")]),
    action("window.close", "Pencereyi kapat", "Pencere",
           "Pencerenin kapat düğmesine basar; uygulama kaydetmek isterse sorusu görünür.", [WINDOW]),
    action("window.wait_close", "Pencerenin kapanmasını bekle", "Pencere",
           "Kayıt, yazdırma veya yükleme penceresi kapanana kadar bekler.",
           [WINDOW, field("timeout", "En fazla bekle (saniye)", "number", 30, min=0, max=3600)]),
    # ----- Fare ve klavye --------------------------------------------------------------
    action("input.mouse_click", "Ekranda tıkla", "Fare ve klavye",
           "Ana ekrandaki bir noktaya tıklar. Pencereye bağlı hedeflerde Pencerede tıkla daha güvenlidir.",
           [*point_fields(), field("button", "Fare düğmesi", "select", "left", options=MOUSE_BUTTONS),
            field("clicks", "Tıklama", "select", 1, options=CLICKS)], pointer=[["x", "y"]]),
    action("input.mouse_move", "Fareyi taşı", "Fare ve klavye", "Fare imlecini bir noktaya götürür; menüleri açmak için.",
           [*point_fields(), field("duration", "Hareket süresi (saniye)", "number", 0.2, min=0, max=10)],
           pointer=[["x", "y"]]),
    action("input.drag", "Sürükle ve bırak", "Fare ve klavye",
           "Bir noktadan basılı tutup diğerine sürükler: dosya taşıma, kaydırma çubuğu, seçim.",
           [*point_fields("from_", "Başlangıç "), *point_fields("to_", "Bitiş "),
            field("button", "Fare düğmesi", "select", "left", options=MOUSE_BUTTONS),
            field("duration", "Sürükleme süresi (saniye)", "number", 0.5, min=0, max=10)],
           pointer=[["from_x", "from_y"], ["to_x", "to_y"]]),
    action("input.scroll", "Fare tekerleğiyle kaydır", "Fare ve klavye",
           "Dikeyde pozitif yukarı, negatif aşağı; yatayda pozitif sağa, negatif sola kaydırır. Konum boşsa imlecin olduğu yerde.",
           [field("amount", "Kaydırma miktarı", "number", -5, min=-100, max=100, required=True),
            field("direction", "Yön", "select", "vertical", options=[{"value": "vertical", "label": "Dikey"},
                                                                     {"value": "horizontal", "label": "Yatay"}]),
            *point_fields(required=False)], pointer=[["x", "y"]]),
    action("input.type", "Metin yaz", "Fare ve klavye",
           "Metni yazar. Yazılacak yeri göstermek için önce tıklanacak noktayı ekrandan alın; boş bırakılırsa imlecin "
           "o an bulunduğu yere yazar. Türkçe karakterler Otomatik yöntemde panoyla yapıştırılır.",
           [field("text", "Yazılacak metin", default="", required=True, help="Değişken kullanabilirsiniz: ${row.form_id}"),
            *point_fields(label="Önce tıklanacak ", required=False),
            field("method", "Yazma yöntemi", "select", "auto",
                  options=[{"value": "auto", "label": "Otomatik"}, {"value": "type", "label": "Tuş tuş yaz"},
                           {"value": "paste", "label": "Panodan yapıştır"}]),
            field("interval", "Harfler arası bekleme (saniye)", "number", 0.02, min=0, max=1)],
           pointer=[["x", "y"]]),
    action("input.hotkey", "Klavye kısayolu gönder", "Fare ve klavye",
           "Kısayol tuşlarına birlikte basar: kaydet, kopyala, pencere değiştir, uygulama menüleri.",
           [field("keys", "Kısayol", "keys", "mod+s", required=True,
                  help="Tuşları + ile ayırın: mod+c, ctrl+shift+esc, alt+f4, alt+tab. mod: Windows'ta Ctrl, Mac'te Command.")]),
    action("input.press", "Tuşa bas", "Fare ve klavye", "Bir tuşa bir veya birkaç kez basar (Enter, Tab, ok tuşları…).",
           [field("key", "Tuş", "select", "enter", required=True, options=KEYS),
            field("presses", "Kaç kez?", "number", 1, min=1, max=500),
            field("interval", "Basışlar arası bekleme (saniye)", "number", 0.05, min=0, max=5)]),
    action("input.key_state", "Tuşu basılı tut / bırak", "Fare ve klavye",
           "Shift/Ctrl gibi bir tuşu basılı tutar veya bırakır; çoklu seçim için. Akış bitince basılı tuşlar bırakılır.",
           [field("key", "Tuş", "select", "shift", required=True, options=KEYS),
            field("state", "Durum", "select", "down", options=[{"value": "down", "label": "Basılı tut"},
                                                             {"value": "up", "label": "Bırak"}])]),
    action("input.mouse_position", "Fare konumunu oku", "Fare ve klavye",
           "İmlecin ekrandaki konumunu {x, y} olarak kaydeder.", [output("mouse")]),
    # ----- Ekran ve görsel -------------------------------------------------------------
    action("screen.find_image", "Ekranda görsel ara / bekle", "Ekran ve görsel",
           "Bir görselin ekranda görünmesini veya kaybolmasını bekler. Sonuç: ${image.found}, ${image.center_x}.",
           [field("template", "Referans görsel", required=True, help="Ekrandan görsel seç ile kaydedin."),
            field("state", "Beklenen durum", "select", "visible", options=[
                {"value": "visible", "label": "Görünsün"}, {"value": "hidden", "label": "Kaybolsun"}]),
            field("timeout", "En fazla bekle (saniye)", "number", 5, min=0, max=600),
            field("confidence", "Eşleşme eşiği", "number", 0.9, min=0.5, max=1, step=0.01),
            field("on_missing", "Süre dolarsa", "select", "continue", required=True, options=[
                {"value": "continue", "label": "Bulunamadı sonucuyla devam et"},
                {"value": "stop", "label": "Akışı durdur"}]),
            *area_fields(), output("image")], template=True),
    action("screen.click_image", "Ekranda görsele tıkla", "Ekran ve görsel",
           "Görseli ekranda bekleyip tıklar; ikon ve düğmeler için. Görselin merkezinden fark verilebilir.",
           [field("template", "Referans görsel", required=True, help="Ekrandan görsel seç ile kaydedin."),
            field("timeout", "En fazla bekle (saniye)", "number", 10, min=0, max=600),
            field("confidence", "Eşleşme eşiği", "number", 0.9, min=0.5, max=1, step=0.01),
            field("offset_x", "Merkezden sağa / sola", "number", 0),
            field("offset_y", "Merkezden aşağı / yukarı", "number", 0),
            field("button", "Fare düğmesi", "select", "left", options=MOUSE_BUTTONS),
            field("clicks", "Tıklama", "select", 1, options=CLICKS), *area_fields()], template=True, region=True),
    action("screen.read_text", "Ekrandan metin oku (OCR)", "Ekran ve görsel",
           "Ekrandaki yazıyı okur: hata mesajları, fatura numaraları, onay metinleri. Kurulum gerektirmez.",
           [*area_fields(), output("screen_text")], region=True),
    action("screen.wait_text", "Ekranda metni bekle", "Ekran ve görsel",
           "Belirli bir yazı (ör. Kaydedildi) ekranda görünene kadar OCR ile bekler.",
           [field("text", "Aranacak metin", required=True), field("timeout", "En fazla bekle (saniye)", "number", 10,
                                                                   min=0, max=600),
            field("on_missing", "Süre dolarsa", "select", "stop", required=True, options=[
                {"value": "stop", "label": "Akışı durdur"}, {"value": "continue", "label": "Yanlış sonucuyla devam et"}]),
            *area_fields(), output("text_found")], region=True),
    action("screen.pixel", "Piksel rengini oku", "Ekran ve görsel",
           "Bir noktanın rengini #RRGGBB olarak okur; durum lambası veya seçili satır kontrolü için.",
           [*point_fields(), output("pixel")], pointer=[["x", "y"]]),
    action("screen.screenshot", "Ekran görüntüsü al", "Ekran ve görsel",
           "Ekranın veya bir bölgenin görüntüsünü çalışma çıktılarına ve isterseniz bir klasöre kaydeder.",
           [*area_fields(), field("filename", "Dosya adı", default="ekran.png", required=True),
            field("folder", "Ayrıca bu klasöre kaydet", "path", "", help="Boş: yalnız çalışma çıktılarına."),
            output("screenshot_path")], region=True),
    # ----- Uygulama ve sistem ----------------------------------------------------------
    action("system.open", "Uygulama, dosya veya adres aç", "Uygulama ve sistem",
           "Programı, belgeyi, klasörü veya web adresini varsayılan uygulamayla açar.",
           [field("target", "Ne açılsın?", "path", "", required=True,
                  help="Windows: notepad.exe, C:\\Raporlar\\rapor.xlsx · Mac: TextEdit, ~/Desktop/rapor.xlsx · https://…"),
            field("arguments", "Parametreler", help="İsteğe bağlı komut satırı parametreleri."),
            field("wait", "Açıldıktan sonra bekle (saniye)", "number", 2, min=0, max=120)]),
    action("system.run_file", "Dosya / script çalıştır", "Uygulama ve sistem",
           "Klasördeki bir script'i veya programı türüne göre çalıştırır (.py, .ps1, .bat, .cmd, .vbs, .exe, .sh, "
           ".scpt, .jar); diğer dosyaları varsayılan programıyla açar.",
           [field("path", "Dosya", "path", "", required=True,
                  help="Windows: C:\\Scriptler\\aktar.py · Mac: ~/Desktop/rapor.sh. Excel, PDF gibi belgeler "
                       "kendi programıyla açılır."),
            field("arguments", "Parametreler", help="Script'e verilecek değerler, boşlukla ayrılır; ${değişken} kullanılabilir."),
            field("folder", "Çalışma klasörü", "path", "", help="Boşsa dosyanın bulunduğu klasör."),
            field("wait_finish", "Bitmesini bekle", "boolean", True,
                  help="Açıksa akış script bitene kadar bekler ve çıktısını alır; kapalıysa başlatıp devam eder."),
            field("timeout", "Zaman aşımı (saniye)", "number", 600, min=1, max=86400,
                  visible_when={"wait_finish": True}),
            field("fail_on_error", "Hata koduyla biterse akışı durdur", "boolean", True,
                  visible_when={"wait_finish": True}),
            output("script")]),
    action("system.close_app", "Uygulamayı kapat", "Uygulama ve sistem",
           "Çalışan bir uygulamayı kapatır; zorla kapatma kaydedilmemiş verileri kaybettirir.",
           [field("application", "Uygulama adı", required=True, help="Windows: EXCEL.EXE · Mac: Microsoft Excel"),
            field("force", "Zorla kapat", "boolean", False)]),
    action("system.command", "Komut çalıştır", "Uygulama ve sistem",
           "Windows'ta cmd, Mac'te terminal komutu çalıştırır; çıktıyı ${command.output} olarak verir.",
           [field("command", "Komut", required=True), field("folder", "Çalışma klasörü", "path", ""),
            field("timeout", "Zaman aşımı (saniye)", "number", 60, min=1, max=3600),
            field("fail_on_error", "Hata koduyla biterse akışı durdur", "boolean", True), output("command")]),
    action("clipboard.set", "Panoya kopyala", "Uygulama ve sistem", "Bir metni panoya koyar; ardından mod+v ile yapıştırın.",
           [field("value", "Değer", default="", required=True)]),
    action("clipboard.get", "Panodaki metni oku", "Uygulama ve sistem", "Panodaki metni değişkene alır.",
           [output("clipboard")]),
    # ----- Dosya ve Excel --------------------------------------------------------------
    action("file.read_table", "Excel / CSV oku", "Dosya ve Excel",
           "Excel (.xlsx) veya CSV tablosunu satır listesine çevirir. Başlıklar alan adı olur: ${row.Tutar}.",
           [field("path", "Dosya", "path", "", required=True, help=FILE_HELP),
            field("sheet", "Sayfa adı", help="Boş: ilk/aktif sayfa."),
            field("header_row", "Başlık satırı", "number", 1, min=0, max=1000, help="0: başlık yok (sutun_1, sutun_2…)."),
            field("max_rows", "En fazla satır", "number", 10000, min=1, max=100000), output("rows")]),
    action("file.write_table", "Excel / CSV'ye yaz", "Dosya ve Excel",
           "Kayıt listesini .xlsx veya .csv dosyasına yazar ya da mevcut dosyanın sonuna ekler.",
           [field("rows", "Kayıtlar", "json", "${rows}", required=True),
            field("path", "Dosya", "path", "", required=True, help=FILE_HELP),
            field("sheet", "Sayfa adı (Excel)", default="Sayfa1"),
            field("mode", "Yazma biçimi", "select", "overwrite", options=[
                {"value": "overwrite", "label": "Yeni dosya / üzerine yaz"}, {"value": "append", "label": "Sonuna ekle"}])]),
    action("file.read_text", "Metin dosyası oku", "Dosya ve Excel", "Bir .txt, .json veya log dosyasının içeriğini okur.",
           [field("path", "Dosya", "path", "", required=True, help=FILE_HELP), output("file_text")]),
    action("file.write_text", "Metin dosyasına yaz", "Dosya ve Excel", "Metni dosyaya yazar veya sonuna ekler (günlük tutma).",
           [field("path", "Dosya", "path", "", required=True, help=FILE_HELP),
            field("text", "Metin", default="", required=True),
            field("mode", "Yazma biçimi", "select", "append", options=[
                {"value": "append", "label": "Sonuna ekle"}, {"value": "overwrite", "label": "Üzerine yaz"}])]),
    action("file.exists", "Dosya / klasör var mı?", "Dosya ve Excel", "Sonucu Koşul adımında kullanın: ${file_exists}.",
           [field("path", "Yol", "path", "", required=True, help=FILE_HELP),
            field("kind", "Tür", "select", "any", options=[{"value": "any", "label": "Dosya veya klasör"},
                                                         {"value": "file", "label": "Dosya"},
                                                         {"value": "folder", "label": "Klasör"}]),
            output("file_exists")]),
    action("file.list", "Klasördeki dosyaları listele", "Dosya ve Excel",
           "Klasördeki dosyaları listeler; Her satır için döngüsüyle tek tek işleyin (${row.path}).",
           [field("folder", "Klasör", "path", "", required=True), field("pattern", "Dosya deseni", default="*",
                                                                          help="Ör. *.xlsx, fatura_*.pdf"),
            field("recursive", "Alt klasörler dahil", "boolean", False),
            field("sort", "Sıralama", "select", "name", options=[{"value": "name", "label": "Ada göre"},
                                                                {"value": "newest", "label": "En yeni önce"},
                                                                {"value": "oldest", "label": "En eski önce"}]),
            output("files")]),
    action("file.operation", "Dosya kopyala / taşı / sil", "Dosya ve Excel", "Dosya veya klasörle işlem yapar.",
           [field("operation", "İşlem", "select", "copy", required=True, options=[
                {"value": "copy", "label": "Kopyala"}, {"value": "move", "label": "Taşı / yeniden adlandır"},
                {"value": "delete", "label": "Sil"}, {"value": "create_folder", "label": "Klasör oluştur"}]),
            field("source", "Kaynak", "path", "", required=True),
            field("destination", "Hedef", "path", "", required=True, visible_when={"operation": ["copy", "move"]}),
            field("overwrite", "Varsa üzerine yaz", "boolean", False, visible_when={"operation": ["copy", "move"]})]),
    action("file.wait", "Dosyanın oluşmasını bekle", "Dosya ve Excel",
           "İndirilen veya dışa aktarılan dosya hazır olana kadar bekler; yolunu kaydeder.",
           [field("path", "Dosya yolu / deseni", "path", "", required=True, help="Ör. ~/Downloads/rapor*.xlsx"),
            field("timeout", "En fazla bekle (saniye)", "number", 60, min=0, max=3600), output("file_path")]),
    action("data.export_csv", "Departman raporu (CSV)", "Dosya ve Excel",
           "Kayıtları çalışma çıktılarına indirilebilir, Excel uyumlu CSV olarak yazar.",
           [field("rows", "Kayıtlar", "json", "${results}", required=True),
            field("filename", "Dosya adı", default="rapor.csv", required=True)]),
    # ----- Veri ve metin ---------------------------------------------------------------
    action("core.set", "Değişken ata", "Veri ve metin",
           "Bir değişkene metin, sayı, liste veya başka bir değişkenin değerini atar; sayaç başlatmak için.",
           [field("name", "Değişken adı", default="sayac", required=True), field("value", "Değer", "json", 0)]),
    action("data.calculate", "Hesapla", "Veri ve metin",
           "Matematik ve mantık ifadesi hesaplar: sayac + 1, round(tutar * 1.2, 2), adet > 0 and durum == 'Bekliyor'.",
           [field("expression", "İfade", default="${sayac} + 1", required=True, raw=True,
                  help="Değişkenleri adıyla veya ${ad} ile yazın. 1.234,56 gibi metin sayılar otomatik çevrilir."),
            output("result")]),
    action("text.transform", "Metin işlemi", "Veri ve metin",
           "Metni temizler, dönüştürür, parçalar veya içinden bilgi çıkarır.",
           [field("text", "Metin", default="${text}", required=True),
            field("operation", "İşlem", "select", "trim", required=True, options=[
                {"value": v, "label": label} for v, label in [
                    ("trim", "Baştaki/sondaki boşlukları sil"), ("remove_spaces", "Tüm boşlukları sil"),
                    ("upper", "BÜYÜK HARF"), ("lower", "küçük harf"), ("title", "Baş Harfler Büyük"),
                    ("replace", "Bul ve değiştir"), ("split", "Ayraçla böl (liste)"), ("lines", "Satırlara böl (liste)"),
                    ("substring", "Parça al"), ("regex_extract", "Desenle bilgi çıkar (regex)"),
                    ("regex_replace", "Desenle değiştir (regex)"), ("number", "Sayıya çevir (1.234,56)"),
                    ("length", "Uzunluk"), ("pad_left", "Soldan doldur (00042)"), ("contains", "İçeriyor mu?"),
                    ("starts_with", "Şununla başlıyor mu?"), ("ends_with", "Şununla bitiyor mu?")]]),
            field("find", "Aranan / ayraç / dolgu karakteri",
                  visible_when={"operation": ["replace", "split", "contains", "starts_with", "ends_with", "pad_left"]}),
            field("replace_with", "Yerine yazılacak", visible_when={"operation": ["replace", "regex_replace"]}),
            field("pattern", "Desen (regex)", default=r"\d+", visible_when={"operation": ["regex_extract", "regex_replace"]},
                  help="Ör. INV-\\d+ veya Fatura No: (\\S+) (parantez içi alınır)."),
            field("all_matches", "Tüm eşleşmeleri liste olarak al", "boolean", False,
                  visible_when={"operation": "regex_extract"}),
            field("start", "Başlangıç (0'dan)", "number", 0, visible_when={"operation": "substring"}),
            field("length", "Uzunluk", "number", None, visible_when={"operation": ["substring", "pad_left"]}),
            field("turkish", "Türkçe harf kuralları (i/İ, ı/I)", "boolean", True,
                  visible_when={"operation": ["upper", "lower", "title"]}), output("text_result")]),
    action("data.date", "Tarih ve saat", "Veri ve metin",
           "Bugünün tarihini alır, tarih biçimler, gün/ay ekler veya iki tarih arasındaki farkı hesaplar.",
           [field("operation", "İşlem", "select", "now", required=True, options=[
                {"value": "now", "label": "Şimdi (biçimli)"}, {"value": "format", "label": "Tarihi biçimlendir"},
                {"value": "add", "label": "Ekle / çıkar"}, {"value": "difference", "label": "İki tarih arası fark"},
                {"value": "weekday", "label": "Haftanın günü"}]),
            field("value", "Tarih", default="şimdi", visible_when={"operation": ["format", "add", "difference", "weekday"]},
                  help="28.09.2026, 2026-09-28 14:30 veya şimdi."),
            field("other", "İkinci tarih", default="şimdi", visible_when={"operation": "difference"}),
            field("amount", "Miktar (eksi: geri)", "number", 1, visible_when={"operation": "add"}),
            field("unit", "Birim", "select", "days", visible_when={"operation": ["add", "difference"]}, options=[
                {"value": "minutes", "label": "Dakika"}, {"value": "hours", "label": "Saat"},
                {"value": "days", "label": "Gün"}, {"value": "weeks", "label": "Hafta"},
                {"value": "months", "label": "Ay (yalnız ekle)"}, {"value": "years", "label": "Yıl (yalnız ekle)"}]),
            field("format", "Çıktı biçimi", default="%d.%m.%Y", visible_when={"operation": ["now", "format", "add"]},
                  help="%d.%m.%Y → 28.09.2026 · %Y-%m-%d · %d.%m.%Y %H:%M · %H:%M:%S"),
            field("input_format", "Giriş biçimi", help="Boş: otomatik tanınır.",
                  visible_when={"operation": ["format", "add", "difference", "weekday"]}), output("date")]),
    action("data.list", "Liste işlemi", "Veri ve metin",
           "Listelerde sayma, öğe alma, filtreleme, sıralama, toplama ve birleştirme.",
           [field("list", "Liste", "json", "${rows}", required=True),
            field("operation", "İşlem", "select", "length", required=True, options=[
                {"value": v, "label": label} for v, label in [
                    ("length", "Kaç öğe var?"), ("first", "İlk öğe"), ("last", "Son öğe"), ("item", "Sıradaki öğe"),
                    ("filter", "Filtrele"), ("sort", "Sırala"), ("unique", "Tekrarları kaldır"), ("sum", "Topla"),
                    ("pluck", "Tek alanın değerleri"), ("join", "Metne birleştir"), ("contains", "İçeriyor mu?"),
                    ("index_of", "Sırasını bul"), ("slice", "Parça al"), ("reverse", "Ters çevir")]]),
            field("field", "Alan adı", help="Satır listelerinde alan: Tutar, form_id. Basit listelerde boş bırakın.",
                  visible_when={"operation": ["filter", "sort", "unique", "sum", "pluck", "join", "contains", "index_of"]}),
            field("operator", "Karşılaştırma", "select", "eq", options=OPERATORS, visible_when={"operation": "filter"}),
            field("value", "Değer", "json", "", visible_when={"operation": ["filter", "contains", "index_of"]}),
            field("index", "Sıra (0'dan; -1 son)", "number", 0, visible_when={"operation": ["item", "slice"]}),
            field("count", "Adet", "number", None, visible_when={"operation": "slice"}),
            field("separator", "Ayraç", default=", ", visible_when={"operation": "join"}),
            field("descending", "Büyükten küçüğe", "boolean", False, visible_when={"operation": "sort"}),
            output("list_result")]),
    action("data.append", "Listeye ekle", "Veri ve metin",
           "Bir değeri veya kaydı listeye ekler; liste yoksa oluşturur. Sonuçları toplayıp rapora yazmak için.",
           [field("name", "Liste değişkeni", default="results", required=True),
            field("value", "Eklenecek değer", "json", "${row}")]),
    # ----- Akış ------------------------------------------------------------------------
    action("control.repeat", "Tekrarla (N kez)", "Akış",
           "İç adımları belirtilen sayıda çalıştırır; ${loop_index} 0'dan başlar.",
           [field("count", "Tekrar sayısı", "number", 3, min=1, max=10000, required=True)],
           container="loop", branches={"children": "TEKRARLA · İÇ ADIMLAR"}),
    action("control.try", "Hata olursa", "Akış",
           "İç adımlarda hata olursa akışı durdurmak yerine Hata olursa dalını çalıştırır; mesaj ${error_message}.",
           [field("error_name", "Hata mesajı değişkeni", default="error_message", required=True)],
           container="try", branches={"children": "DENE", "otherwise": "HATA OLURSA"}),
    action("control.break", "Döngüden çık", "Akış", "İçinde bulunduğu döngüyü hemen bitirir.", []),
    action("control.continue", "Sonraki tura geç", "Akış", "Döngünün bu turunu atlayıp sonrakine geçer.", []),
    action("control.goto", "Adıma git", "Akış",
           "Akışı seçilen adımdan sürdürür: geri dönüp adımları tekrarlamak veya bir yolu başka bir adıma "
           "bağlamak için; adımları kopyalamanız gerekmez.",
           [field("target", "Gidilecek adım", "step", "", required=True),
            field("max_jumps", "Her turda en fazla", "number", 10, min=1, max=100000, required=True)]),
    action("control.run_workflow", "Başka akışı çalıştır", "Akış",
           "Kayıtlı başka bir akışı bu noktada çalıştırır; değişkenleri paylaşır. Ortak giriş/çıkış işlemleri için.",
           [field("workflow", "Akış", "workflow", "", required=True)]),
    action("control.stop", "Akışı bitir", "Akış", "Akışı bu noktada başarıyla veya hata ile sonlandırır.",
           [field("status", "Sonuç", "select", "success", options=[{"value": "success", "label": "Başarılı"},
                                                                   {"value": "failure", "label": "Hata"}]),
            field("message", "Mesaj", default="Akış tamamlandı.")]),
    action("core.log", "Çalışma notu", "Akış", "Çalışma günlüğüne not yazar; değişken değerlerini izlemek için.",
           [field("message", "Not", default="Değer: ${result}", required=True)]),
    # ----- Kullanıcı etkileşimi ----------------------------------------------------------
    action("ui.message", "Mesaj kutusu göster", "Kullanıcı etkileşimi",
           "Ekranda mesaj gösterir ve yanıtı bekler; ${answer}: ok, cancel, yes, no (süre dolarsa timeout).",
           [field("title", "Başlık", default="RpaOrkestrAI"), field("text", "Mesaj", default="", required=True),
            field("buttons", "Düğmeler", "select", "ok", options=[
                {"value": "ok", "label": "Tamam"}, {"value": "ok_cancel", "label": "Tamam / İptal"},
                {"value": "yes_no", "label": "Evet / Hayır"}]),
            field("timeout", "Otomatik kapanma (saniye, 0: kapanmaz)", "number", 0, min=0, max=86400),
            output("answer")]),
    action("ui.input", "Kullanıcıdan değer iste", "Kullanıcı etkileşimi",
           "Çalışma sırasında bir değer sorar (ör. tarih, fatura no) ve değişkene kaydeder.",
           [field("title", "Başlık", default="RpaOrkestrAI"), field("prompt", "Soru", default="", required=True),
            field("default", "Varsayılan değer"),
            field("on_cancel", "İptal edilirse", "select", "stop", options=[
                {"value": "stop", "label": "Akışı durdur"}, {"value": "continue", "label": "Boş değerle devam et"}]),
            output("user_input")]),
    # ----- Web ve API --------------------------------------------------------------------
    action("http.request", "HTTP isteği gönder (API)", "Web ve API",
           "Bir web servisine istek gönderir; JSON yanıt ${response.body} içinde gelir.",
           [field("method", "Yöntem", "select", "GET", options=[{"value": m, "label": m} for m in
                                                               ["GET", "POST", "PUT", "PATCH", "DELETE"]]),
            field("url", "Adres", default="https://", required=True), field("headers", "Başlıklar", "json", {}),
            field("body", "Gövde", "json", None, help="JSON nesnesi veya metin; GET'te gönderilmez."),
            field("timeout", "Zaman aşımı (saniye)", "number", 30, min=1, max=300),
            field("fail_on_error", "4xx/5xx yanıtında akışı durdur", "boolean", True), output("response")]),
]
CATEGORY_ORDER = ["Pencere", "Fare ve klavye", "Ekran ve görsel", "Uygulama ve sistem", "Dosya ve Excel",
                  "Veri ve metin", "Google Sheets", "Akış", "Kullanıcı etkileşimi", "Web ve API"]
BRANCHES = {"control.for_each": {"children": "HER SATIR İÇİN · İÇ ADIMLAR"},
            "control.while": {"children": "KOŞUL SÜRDÜKÇE · İÇ ADIMLAR"},
            "control.if": {"children": "KOŞUL DOĞRUYSA", "otherwise": "DEĞİLSE"}}
for entry in CATALOG:
    if entry["type"] in BRANCHES:
        entry["branches"] = BRANCHES[entry["type"]]
CATALOG = sorted(CATALOG + LIBRARY, key=lambda entry: CATEGORY_ORDER.index(entry["category"]))
# Every step can pause before the flow moves on, instead of a separate Bekle step after it. Steps that
# end a path never hand over to a next step, and Bekle is itself a pause.
WAIT_AFTER = field("wait_after", "Sonraki adıma geçmeden bekle (saniye)", "number", 0, min=0, max=3600, step=0.1,
                   help="Adım bitince akış bu kadar bekler, sonra sonraki adıma geçer; 0 beklemez. Döngü, koşul ve "
                        "Hata olursa bloklarında blok bütünüyle bittikten sonra beklenir. Ekranın hazır olmasını "
                        "beklemek için Pencerede görseli bekle / ara daha güvenlidir.")
NO_WAIT_AFTER = {"control.goto", "control.continue", "control.break", "control.stop", "core.wait"}
for entry in ACTION_DEFINITIONS + CATALOG:
    # Field definitions are shared between steps; each step gets its own copy before help is filled in.
    entry["fields"] = [dict(item) for item in entry["fields"]]
    if entry["type"] not in NO_WAIT_AFTER and all(item["name"] != "wait_after" for item in entry["fields"]):
        entry["fields"].append(dict(WAIT_AFTER))
    for item in entry["fields"]:
        if item["name"] in NAME_PARAMETERS or (item["name"] == "name" and entry["type"] in NAMING_ACTIONS):
            # The name a step gives to its result: the form takes only the name and shows how it is used.
            item["variable"] = True
            if re.fullmatch(r"Sonraki adım(lar)?da \$\{\w+\} ile kullanın\.", item.get("help", "")):
                del item["help"]
        elif item["name"] == "window":
            # Chosen from the windows that earlier steps named.
            item["reference"] = "window"
apply_guides(ACTION_DEFINITIONS + CATALOG)
BY_TYPE = {entry["type"]: entry for entry in ACTION_DEFINITIONS + CATALOG}
# No longer offered in the library, still run in saved flows: retired step → the step that replaces it.
RETIRED = {"screen.find_image": "desktop.window_wait_image"}
for entry in CATALOG:
    if entry["type"] in RETIRED:
        entry["retired"] = RETIRED[entry["type"]]
ACTION_DEFINITIONS = ACTION_DEFINITIONS + [entry for entry in CATALOG if entry["type"] in RETIRED]
CATALOG = [entry for entry in CATALOG if entry["type"] not in RETIRED]
# Preview runs skip these (they touch the screen, files, network or other programs).
EXTERNAL_PREFIXES = ("database.", "desktop.", "browser.", "sheets.", "input.", "window.", "screen.", "system.",
                     "clipboard.", "file.", "ui.", "http.")
CONTAINERS = {"control.for_each": ("children",), "control.while": ("children",), "control.repeat": ("children",),
              "control.if": ("children", "otherwise"), "control.try": ("children", "otherwise")}
LOOPS = {"control.for_each", "control.while", "control.repeat"}
# Nothing follows these on the same path; a step after one is reached only through Adıma git.
ENDINGS = {"control.goto", "control.continue", "control.break", "control.stop"}
# A single-step test may run these earlier steps by itself to get the values the tested step needs:
# they only compute or read, and never click, type or write.
TEST_PREPARE = {"core.set", "data.append", "data.calculate", "text.transform", "data.date", "data.list", "data.sample",
                "desktop.find_window", "desktop.window_wait_image", "screen.find_image", "screen.read_text", "screen.wait_text", "screen.pixel",
                "input.mouse_position", "clipboard.get", "file.read_table", "file.read_text", "file.exists",
                "file.list", "sheets.read_cell", "sheets.read_rows", "sheets.read_column", "sheets.read",
                "database.read"}
# A test can show where these steps point (the mouse moves there) without clicking or typing.
LOCATABLE = {"desktop.window_click", "desktop.window_fill", "window.read_field", "window.read_table",
             "input.mouse_click",
             "input.mouse_move", "screen.click_image"}


def library_catalog() -> list[dict[str, Any]]:
    return CATALOG


def defaults(action_type: str) -> dict[str, Any]:
    return {f["name"]: f["default"] for f in BY_TYPE[action_type]["fields"]}
