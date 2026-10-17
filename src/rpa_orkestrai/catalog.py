"""The action catalog also drives the Studio's parameter forms."""

from __future__ import annotations

import re
from typing import Any

from .guide import apply as apply_guides
from .models import NAME_PARAMETERS, NAMING_ACTIONS
from .step_numbers import STEP_NUMBERS


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


def window_key_fields() -> list[dict]:
    # Fresh dicts: guide.apply() fills each step's own field help in place.
    return [field("key", "Tuş", "select", "enter", required=True,
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
                      ("shift", "Shift"), ("alt", "Alt / Option"), ("ctrl", "Ctrl")]])]


SHEETS_CONNECTION = field("connection", "Google Sheets bağlantısı", "connection", "", connection_type="google_sheets",
                          help="Boş bırakılırsa varsayılan Google Sheets bağlantısı kullanılır.")
WEB_TARGET = [
    field("by", "Hedefi bulma yöntemi", "select", "text", required=True, options=[
        {"value": "text", "label": "Görünen metin"}, {"value": "label", "label": "Alan etiketi"},
        {"value": "placeholder", "label": "Alandaki silik yazı (yer tutucu)"},
        {"value": "button", "label": "Düğme veya bağlantı adı"}, {"value": "css", "label": "CSS seçici (gelişmiş)"}]),
    field("target", "Hedef", required=True,
          help="Sayfada görünen yazı (ör. Giriş yap, Fatura No) veya CSS seçici (ör. #kullanici)."),
    field("exact", "Tam eşleşme", "boolean", False, omit_default=True,
          help="Kapalıyken yazdığınız metnin içinde geçmesi yeterlidir; büyük/küçük harf fark etmez."),
    field("timeout", "En fazla bekle (saniye)", "number", 15, min=0.5, max=300, omit_default=True,
          help="Hedef görünene kadar bekler; süre dolarsa adım durur."),
    field("frame", "Çerçeve (iframe)", default="", omit_default=True,
          help="Hedef sayfanın içindeki bir çerçevedeyse çerçevenin CSS seçicisi (ör. iframe#icerik). Boş: sayfanın kendisi."),
]
MAIL_CONNECTION = field("connection", "E-posta (SMTP) bağlantısı", "connection", "", connection_type="smtp",
                        help="Gönderen hesap ve sunucu. Şifre yalnız bu bilgisayarda saklanır.")
DATABASE_CONNECTION = field("connection", "Veritabanı bağlantısı", "connection", "", connection_type="database",
                            help="Boş bırakılırsa varsayılan veritabanı bağlantısı kullanılır.")
API_CONNECTION = field("connection", "API bağlantısı", "connection", "", connection_type="api", optional=True,
                       omit_default=True,
                       help="Seçilirse adres bağlantının ana adresine göre bir yol olur (ör. /v1/siparisler) ve kimlik "
                            "bilgileri otomatik eklenir. Boş: tam adres yazın, kimlik bilgisi eklenmez.")
IMAP_CONNECTION = field("connection", "Gelen e-posta (IMAP) bağlantısı", "connection", "", connection_type="imap",
                        help="Okunacak posta kutusu. Şifre yalnız bu bilgisayarda saklanır.")
FTP_CONNECTION = field("connection", "FTP bağlantısı", "connection", "", connection_type="ftp",
                       help="Sunucu, kullanıcı ve başlangıç klasörü bağlantıda tanımlanır.")
WEBHOOK_CONNECTION = field("connection", "Mesajlaşma bağlantısı", "connection", "", connection_type="webhook",
                           help="Teams, Slack, Google Chat veya Discord kanalının webhook adresi bağlantıda saklanır.")
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
              visible_when={"target_mode": "image"}, help="Referans görselin merkezi ile hedef nokta arasındaki yatay fark."),
        field("offset_y", "Görsel merkezinden aşağı / yukarı", "number", 0,
              visible_when={"target_mode": "image"}),
    ]

def table_target_fields() -> list[dict]:
    fields = target_fields()
    fields[0] = {**fields[0], "default": "auto", "omit_default": True, "new_default": "coordinates",
                 "label": "Tabloyu bulma yöntemi", "help": "Uygulamanın tablo yapısında hangi tablonun "
                 "kullanılacağını seçin. Referans verirseniz nokta tablonun içinde olmalıdır.",
                 "options": [*fields[0]["options"], {"value": "auto", "label": "Penceredeki tek tablo"}]}
    return [{**f, "visible_when": {**f.get("visible_when", {}), "write_method": ["native", "point"]}} for f in fields]


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
           [WINDOW, *window_key_fields()]),
    action("desktop.window_click_key", "Tıkla ve tuşa bas", "Pencere",
           "Hedefi konumuyla, görseliyle veya alan kimliğiyle bulup tıklar, ardından seçilen tuşu veya kısayolu "
           "gönderir. Hedef bulunamazsa tıklamaz ve tuşa basmaz.",
           [WINDOW, *target_fields(),
            field("clicks", "Tıklama sayısı", "select", 1,
                  options=[{"value": 1, "label": "Tek tık"}, {"value": 2, "label": "Çift tık"}]),
            *window_key_fields(),
            field("delay", "Tıklama ile tuş arasında bekle (saniye)", "number", 0.2, min=0, max=5, step=0.1)]),
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
           "Seçtiğiniz sütunları aynı kayıtta okur. Ana alanı dolu olan satırları korur.",
           [SHEETS_CONNECTION, SHEET_ID, field("worksheet", "Sayfa adı", default="Sayfa1", required=True),
            field("start_row", "Başlangıç satırı", "number", 2, min=1, max=1000000, required=True),
            field("max_rows", "En fazla kaç satır okunsun?", "number", 100, min=1, max=1000, required=True),
            field("columns", "Okunacak sütunlar", "columns", {"form_id": "B", "status": "C"}, required=True,
                  help="Her sütuna akışınıza uygun bir ad verin. Döngüde ${row.alan_adi} biçiminde kullanın."),
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
                  help="Satırın alanına ${row.alan_adi} ile erişin. Sheets satırlarında ${row.row_number} gerçek satır numarasıdır."),
            field("start", "Kaçıncı satırdan başlasın?", "number", None, min=1, max=100000)], container="loop"),
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
              help="Boş bırakılırsa tüm ekran/pencere kullanılır. Bölge çiz düğmesiyle seçebilirsiniz."),
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
           "Uygulamadaki tabloda bir hücreyi sütun adıyla okur; kaç satır bulunduğunu da verir. "
           "Tabloya tıklayıp tamamını kopyalar ve ayrıştırır; pano eski haline döner.",
           [WINDOW, *target_fields(),
            field("mode", "Ne okunacak", "select", "value", required=True,
                  options=[{"value": "value", "label": "Bir hücrenin değeri"},
                           {"value": "count", "label": "Kaç satır var?"}]),
            field("column", "Sütun", required=True, visible_when={"mode": "value"}),
            field("row", "Satır", "number", 1, min=1, max=10000, required=True, visible_when={"mode": "value"}),
            field("header", "İlk satır sütun başlıklarıdır", "boolean", True),
            field("header_row", "Başlık satırı", "number", 1, min=1, max=10000, omit_default=True,
                  visible_when={"header": True}, help="Kopyalanan tablodaki başlık satırı. Öncesinde boş satır varsa 2 seçin; veri bu satırdan sonra başlar."),
            output("table_value")]),
    action("window.write_table", "Tabloya değer yaz", "Pencere",
           "Tablonun herhangi bir yerine tıklayarak seçin. Satır, sütun ve yeni değeri girin; hücreyi güncel tablo yapısından bulup yazar.",
           [WINDOW,
            field("write_method", "Yazma yöntemi", "select", "native", required=True,
                  new_default="point", omit_default=True,
                  options=[{"value": "point", "label": "Seçilen tabloyu otomatik tanı"},
                           {"value": "screen", "label": "Kaydedilmiş tablo alanını kullan"},
                           {"value": "native", "label": "Uygulamanın tablo yapısını kullan"}],
                  help="Otomatik: seçilen noktadaki tablo yapısını kullanır; doğrudan hücre erişimi yoksa tablonun tamamını kopyalayıp hücreyi bulur. "
                       "Uygulamanın tablo yapısı: düzenlenebilir hücre erişimi gerektirir; eski adımlar bu yöntemi korur."),
            *table_target_fields(),
            field("region", "Tablo alanı", "json", None, required=True, visible_when={"write_method": "screen"},
                  help="Tablo alanını çiz ile yalnız bir tabloyu, başlıkları ve veri satırlarıyla birlikte seçin. "
                       "Alan pencereye göre saklanır; hücrelerin güncel yeri bu alan içinde bulunur."),
            field("header", "İlk satır sütun başlıklarıdır", "boolean", True, omit_default=True,
                  visible_when={"write_method": ["screen", "point"]},
                  help="Başlık varsa açık, kopya yalnız veri içeriyorsa kapalı olmalıdır. "
                       "Önizlemede Başlık yap veya Başlık yok ile düzeltebilirsiniz."),
            field("header_row", "Başlık satırı", "number", 1, min=1, max=10000, omit_default=True,
                  visible_when={"write_method": ["screen", "point"], "header": True},
                  help="Tablo önizlemesinde Başlık yap ile seçilir. Başlık ve öncesindeki satırlar veri sayılmaz; Satır 1 ilk veri kaydıdır."),
            field("edit_mode", "Hücreyi düzenlemeye aç", "select", "double_click", required=True,
                  new_default="auto", omit_default=True, visible_when={"write_method": ["screen", "point"]},
                  options=[{"value": "auto", "label": "Otomatik doğrula"},
                           {"value": "double_click", "label": "Çift tıklama"},
                           {"value": "single_click", "label": "Tek tıklama"},
                           {"value": "f2", "label": "Hücreyi seçip F2"}],
                  help="Hücreyi elle nasıl düzenlemeye açıyorsanız onu seçin. "
                       "Eski metin doğrulanmadan yeni değer yazılmaz."),
            field("table", "Tablo adı veya kimliği", default="",
                  visible_when={"write_method": "native", "target_mode": "auto"},
                  help="Pencerede tek tablo varsa boş bırakın. Birden fazlaysa uygulamanın erişilebilir tablo adı veya kimliğini yazın."),
            field("row_mode", "Satır seçimi", "select", "index", options=[
                {"value": "index", "label": "Satır numarası"}, {"value": "match", "label": "Benzersiz değeri bul"}],
                  help="Değeri bul yöntemi, kayıtların sırası değişse de doğru satırı seçer."),
            field("row", "Satır", "number", 1, min=1, max=10000, required=True, visible_when={"row_mode": "index"},
                  help="1: ilk veri satırı. Başlık sayılmaz; sıralama değişiyorsa benzersiz değerle arayın."),
            field("match_column", "Aranacak sütun", required=True, visible_when={"row_mode": "match"},
                  help="Kaydı ayırt eden benzersiz değerin sütun başlığı veya 1'den başlayan sütun numarası."),
            field("match_value", "Aranacak değer", required=True, visible_when={"row_mode": "match"},
                  help="Tam eşleşme aranır; birden fazla satır eşleşirse yazılmaz. Değişken kullanılabilir: ${row.kod}."),
            field("column", "Yazılacak sütun", required=True,
                  help="Okumadaki gibi sütun adı (Durum), sutun_2 veya 2 yazın. Numara kopyalanan tablonun "
                       "soldan başlayan sütun sırasıdır; kutucuk/boş sütunları da sayar. Genişlik değişse de hücre yeniden bulunur."),
            field("value", "Yazılacak değer", required=True,
                  help="Hücrenin yeni değeri; değişken kullanılabilir: ${row.deger}. Boş değer, Tab ve satır sonu kabul edilmez."),
            output("table_write", "Doğrulanan hücre: ${table_write.row}, ${table_write.column}, ${table_write.value}.")]),
    action("window.text_write", "Metni bul, tıkla ve yaz", "Pencere",
           "Çizdiğiniz alanda, yazdığınız metni içeren yazıyı her çalışmada OCR ile yeniden bulur, ortasına tıklar ve "
           "değeri yazar. Metin bulunamazsa veya birden fazla yerde görünürse tıklamaz.",
           [WINDOW,
            field("region", "Arama alanı", "json", None,
                  help="Bölge çiz ile pencerenin görüntüsünde aranacak alanı seçin. Boşsa pencerenin tamamında aranır. "
                       "Alan pencereye göre saklanır."),
            field("position", "Nereye tıklansın?", "select", "text", required=True,
                  options=[{"value": "text", "label": "Bulunan metnin üzerine"},
                           {"value": "cross", "label": "Sütun ve satır kesişimine (boş hücre için)"}],
                  help="Kesişim: sütun başlığının altına, satırdaki metnin hizasına tıklar; hücre boş olabilir."),
            field("text", "Aranacak metin", required=True, visible_when={"position": "text"},
                  help="Ekranda görünen metnin bir parçası yeterlidir (ör. İad → İade); büyük/küçük harf fark etmez. "
                       "Bu parça alanda tek bir yerde geçmelidir. Değişken kullanılabilir: ${row.kod}."),
            field("column_text", "Sütun metni", required=True, visible_when={"position": "cross"},
                  help="Yazılacak sütunun ekrandaki başlığı veya bir parçası (ör. Miktar; kısaltılmış başlıkta İade Sonr)."),
            field("row_text", "Satır metni", required=True, visible_when={"position": "cross"},
                  help="Aynı satırda başka bir sütunda görünen, satırı ayırt eden değer veya bir parçası (ör. kayıt kodu)."),
            field("value", "Yazılacak değer", required=True,
                  help="Değişken kullanılabilir: ${row.deger}. Enter veya Tab için aşağıdaki seçeneği kullanın."),
            field("clicks", "Tıklama", "select", 1,
                  options=[{"value": 1, "label": "Tek tık"}, {"value": 2, "label": "Çift tık (hücreyi düzenlemeye açar)"}]),
            field("clear", "Önce mevcut değeri temizle", "boolean", False,
                  help="Tümünü seçip siler. Yalnız tıklama yazı alanını veya hücre düzenlemesini açıyorsa kullanın; "
                       "aksi halde tablodaki tüm satırlar seçilebilir."),
            field("after", "Yazdıktan sonra", "select", "none",
                  options=[{"value": "none", "label": "Hiçbir şey"}, {"value": "tab", "label": "Tab'a bas"},
                           {"value": "enter", "label": "Enter'a bas"}])],
           region=True),
    action("window.checkbox", "Onay kutusu", "Pencere",
           "Bir onay kutusunu işaretler, işaretini kaldırır veya durumunu okur. Zaten istenen durumdaysa tıklamaz; "
           "değiştirdikten sonra yeni durumu doğrular.",
           [WINDOW,
            field("operation", "İşlem", "select", "check", required=True, options=[
                {"value": "check", "label": "İşaretle"}, {"value": "uncheck", "label": "İşaretini kaldır"},
                {"value": "read", "label": "Durumunu oku"}]),
            *target_fields(),
            field("checked_template", "İşaretliyken görüntüsü", required=True,
                  visible_when={"target_mode": ["coordinates", "image"]},
                  help="Kutu işaretliyken yalnız kutuyu kapsayan küçük bir görüntü. Uygulama yapısından durum "
                       "okunamayan (ör. Java) uygulamalar için."),
            field("unchecked_template", "İşaretsizken görüntüsü", required=True,
                  visible_when={"target_mode": ["coordinates", "image"]},
                  help="Aynı kutunun işaretsiz hali; iki görüntü yalnız hedefin çevresinde karşılaştırılır."),
            output("checkbox_state", "İşaretliyse doğru, değilse yanlış: Koşul → Dolu / doğru ile kullanın.")]),
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
           "Masaüstünde çift tıklamak gibi: programı, belgeyi, klasörü veya web adresini açar; akış "
           "programın kapanmasını beklemez.",
           [field("target", "Ne açılsın?", "path", "", required=True,
                  help="Programın çalışan kısayolunu, dosyasını veya adresini seçin. "
                       "Windows: C:\\Program Files\\Uygulama\\app.exe, C:\\Raporlar\\rapor.xlsx · Mac: TextEdit, "
                       "~/Desktop/rapor.xlsx · https://…"),
            field("arguments", "Parametreler", help="Kısayol seçtiyseniz genellikle boş bırakın; kısayolun kendi "
                  "parametreleri kullanılır. javaws.exe için JNLP dosyası veya adresi gerekir."),
            field("wait", "Açıldıktan sonra bekle (saniye)", "number", 2, min=0, max=120)]),
    action("system.run_file", "Dosya / script çalıştır", "Uygulama ve sistem",
           "Klasördeki bir script'i veya programı türüne göre çalıştırır (.py, .ps1, .bat, .cmd, .vbs, .exe, .sh, "
           ".scpt, .jar); diğer dosyaları varsayılan programıyla açar.",
           [field("path", "Dosya", "path", "", required=True,
                  help="Windows: C:\\Scriptler\\aktar.py · Mac: ~/Desktop/rapor.sh. Excel, PDF gibi belgeler "
                       "kendi programıyla açılır."),
            field("arguments", "Parametreler", help="Script'e verilecek değerler, boşlukla ayrılır; ${değişken} kullanılabilir."),
            field("folder", "Çalışma klasörü", "path", "", help="Boşsa dosyanın bulunduğu klasör."),
            field("wait_finish", "Bitmesini bekle", "select", "auto", required=True,
                  options=[{"value": "auto", "label": "Otomatik: script'i bekle, programı (.exe) bekleme"},
                           {"value": "wait", "label": "Bitmesini bekle"},
                           {"value": "no", "label": "Bekleme, akış devam etsin"}],
                  help="Script bitene kadar beklenir ve çıktısı alınır. Açık kalan programlar "
                       "beklenmez; açılınca akış devam eder."),
            field("timeout", "Zaman aşımı (saniye)", "number", 600, min=1, max=86400,
                  visible_when={"wait_finish": ["auto", "wait"]}),
            field("fail_on_error", "Hata koduyla biterse akışı durdur", "boolean", True,
                  visible_when={"wait_finish": ["auto", "wait"]}),
            output("script")]),
    action("system.close_app", "Uygulamayı kapat", "Uygulama ve sistem",
           "Çalışan bir uygulamayı kapatır; zorla kapatma kaydedilmemiş verileri kaybettirir.",
           [field("application", "Uygulama adı", required=True, help="Windows: EXCEL.EXE · Mac: Microsoft Excel"),
            field("force", "Zorla kapat", "boolean", False)]),
    action("system.command", "Komut / script çalıştır", "Uygulama ve sistem",
           "Terminale veya PowerShell'e komut yazmak gibi: komutu ya da seçtiğiniz script dosyasını (.py, .ps1, "
           ".bat, .vbs, .sh…) çalıştırır, bitmesini bekler ve çıktısını ${command.output} olarak verir.",
           [field("run", "Ne çalıştırılsın?", "select", "command", required=True, omit_default=True,
                  options=[{"value": "command", "label": "Komut yaz"},
                           {"value": "file", "label": "Script dosyası seç (.py, .ps1, .bat, .vbs, .sh…)"}]),
            field("shell", "Komut nerede çalışsın?", "select", "system", required=True, omit_default=True,
                  options=[{"value": "system", "label": "Komut İstemi (Windows) / Terminal (Mac)"},
                           {"value": "powershell", "label": "PowerShell"}],
                  visible_when={"run": "command"}),
            field("command", "Komut", required=True, visible_when={"run": "command"}),
            field("path", "Script dosyası", "path", "", required=True, omit_default=True, visible_when={"run": "file"},
                  help="Windows: C:\\Scriptler\\aktar.py · Mac: ~/Desktop/rapor.sh"),
            field("arguments", "Parametreler", omit_default=True, visible_when={"run": "file"},
                  help="Script'e verilecek değerler, boşlukla ayrılır; ${değişken} kullanılabilir."),
            field("folder", "Çalışma klasörü", "path", ""),
            field("timeout", "Zaman aşımı (saniye)", "number", 300, min=1, max=86400),
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
                {"value": "overwrite", "label": "Yeni dosya / üzerine yaz"}, {"value": "append", "label": "Sonuna ekle"}]),
            field("last_row_column", "Son satırı belirleyen sütun (Excel)", default="", omit_default=True,
                  visible_when={"mode": "append"}),
            field("formulas", "= ile başlayan değerleri formül olarak yaz (Excel)", "boolean", False,
                  omit_default=True)]),
    action("file.write_cell", "Excel hücresine yaz", "Dosya ve Excel",
           "Bir değeri veya formülü seçtiğiniz sütuna yazar: belirli bir satıra, son dolu satıra ya da son dolu "
           "satırın altına. Son satırı hangi sütunun belirleyeceğini siz seçersiniz.",
           [field("path", "Dosya", "path", "", required=True, help=FILE_HELP),
            field("sheet", "Sayfa adı", default="Sayfa1"),
            field("column", "Sütun", default="A", required=True),
            field("row_mode", "Satır", "select", "number", required=True, options=[
                {"value": "number", "label": "Belirli satır numarası"},
                {"value": "next", "label": "Son dolu satırın altına (yeni satır)"},
                {"value": "last", "label": "Son dolu satıra"}]),
            field("row", "Satır numarası", default="2", required=True, visible_when={"row_mode": "number"}),
            field("last_row_column", "Son satırı belirleyen sütun", default="",
                  visible_when={"row_mode": ["next", "last"]}),
            field("value_type", "Değer türü", "select", "value", required=True, options=[
                {"value": "value", "label": "Metin / değer"}, {"value": "number", "label": "Sayı"},
                {"value": "formula", "label": "Formül"}]),
            field("value", "Yazılacak değer", default="${result}"),
            output("excel_cell")]),
    action("file.zip", "Zip aç / oluştur", "Dosya ve Excel",
           "Bir zip dosyasını klasöre açar veya dosya ve klasörlerden zip oluşturur. Türkçe dosya adları korunur.",
           [field("operation", "İşlem", "select", "extract", required=True, options=[
                {"value": "extract", "label": "Zip'i klasöre aç"}, {"value": "create", "label": "Zip oluştur"}]),
            field("source", "Zip dosyası", "path", "", required=True, visible_when={"operation": "extract"},
                  help=FILE_HELP),
            field("folder", "Açılacak klasör", "path", "", required=True, visible_when={"operation": "extract"},
                  help="Klasör yoksa oluşturulur. Zip'teki klasör yapısı korunur."),
            field("items", "Eklenecek dosya ve klasörler", "code", "", required=True,
                  visible_when={"operation": "create"},
                  help="Her satıra bir dosya veya klasör yolu yazın; klasörler içindekilerle eklenir."),
            field("destination", "Oluşturulacak zip dosyası", "path", "", required=True, path_kind="save",
                  visible_when={"operation": "create"}, help="Ör. C:\\Raporlar\\gunluk.zip"),
            field("overwrite", "Aynı adlı dosyaların üzerine yaz", "boolean", False,
                  help="Kapalıyken aynı adlı dosya varsa hiçbir dosya yazılmaz."),
            output("zip_result", "Dosya listesi: ${zip_result.files}, sayısı: ${zip_result.count}.")]),
    action("file.read_pdf", "PDF'ten oku", "Dosya ve Excel",
           "PDF'in metnini veya içindeki bir tabloyu okur. Taranmış (metni olmayan) sayfalar sistem OCR'ıyla okunur.",
           [field("path", "PDF dosyası", "path", "", required=True, help=FILE_HELP),
            field("mode", "Ne okunsun?", "select", "text", required=True, options=[
                {"value": "text", "label": "Metin"}, {"value": "table", "label": "Tablo (satır listesi)"}]),
            field("pages", "Sayfalar", default="", help="Boş: tüm sayfalar. Ör. 1 veya 1-3, 5."),
            field("ocr", "Metni olmayan sayfaları OCR ile oku", "boolean", True, visible_when={"mode": "text"},
                  help="Taranmış belge ve fotoğraf sayfaları için. Kapalıyken bu sayfalar boş gelir."),
            field("table", "Kaçıncı tablo", "number", 1, min=1, max=1000, visible_when={"mode": "table"},
                  help="Seçilen sayfalardaki tabloların sırası; 1 ilk tablodur. Tablolar çizgileriyle tanınır."),
            field("header", "İlk satır sütun başlıklarıdır", "boolean", True, visible_when={"mode": "table"},
                  help="Açıkken başlıklar alan adı olur: ${row.Tutar}. Kapalıyken sutun_1, sutun_2…"),
            output("pdf_text", "Metin modunda okunan metin; tablo modunda Her satır için ile kullanılacak satır listesi.")]),
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
    action("ai.ask", "Yapay zekâya sor", "Veri ve metin",
           "Seçilen modele sınırlı veri gönderir; araç çalıştırmadan metin veya şemayla doğrulanan JSON döndürür.",
           [field("connection", "Yapay zekâ bağlantısı", "agent_connection", "", required=True,
                  help="Ajanlar bölümündeki sağlayıcı bağlantısını seçin; model adı o bağlantıdan alınır."),
            field("instructions", "Talimat", "textarea", "", required=True,
                  help="İstenen kararı veya analizi açıkça yazın; en fazla 8.000 karakter."),
            field("input", "Girdi", "json", "${veri}", required=True,
                  help="Metin, liste, nesne veya ${değişken}; en fazla 32.000 bayt. Kayıtlı sırlar maskelenir."),
            field("schema", "Sonuç JSON şeması (isteğe bağlı)", "json", None,
                  help="Boşsa metin döner. Draft 2020-12 şeması verilirse yalnız geçerli JSON kabul edilir; "
                       "uzak başvuru ve düzenli ifade kuralları desteklenmez."),
            field("timeout", "Yanıt süresi (saniye)", "number", 60, min=0.1, max=120,
                  help="Süre dolarsa veya oturum değişirse sonuç kullanılmadan akış durur."),
            field("max_tokens", "Yanıt token sınırı", "number", 4096, min=16, max=16384,
                  help="Model yanıtının üst sınırı; güncel modellerin yanıttan önceki düşünmesi de buna sayılır. Sınır "
                       "düşünürken dolarsa adım bir kez daha geniş sınırla sorar."),
            output("ai_result")]),
    # ----- Veritabanı ------------------------------------------------------------------
    action("database.query", "Veritabanı sorgusu", "Veritabanı",
           "SQL Server, PostgreSQL, MySQL, Oracle veya SQLite veritabanında SELECT sorgusu çalıştırır; sonuç "
           "satır listesi olur ve Her satır için döngüsüne verilebilir. Yalnız okuma yapılır.",
           [DATABASE_CONNECTION,
            field("query", "SQL sorgusu", "code", "SELECT * FROM tablo WHERE durum = ${durum}", required=True,
                  raw=True),
            field("max_rows", "En fazla satır", "number", 1000, min=1, max=100000, required=True),
            output("rows")]),
    action("database.execute", "Veritabanında değişiklik yap", "Veritabanı",
           "Kayıt ekler, günceller, siler veya saklı yordam çalıştırır (INSERT, UPDATE, DELETE, MERGE, EXEC). Yalnız "
           "bağlantıda yazma izni verilen tablolarda çalışır; sınırdan fazla satır değişirse işlem geri alınır.",
           [DATABASE_CONNECTION,
            field("query", "SQL komutu", "code", "UPDATE dbo.siparisler SET durum = ${yeni_durum} WHERE no = ${row.no}",
                  required=True, raw=True),
            field("max_rows", "En fazla değişecek satır", "number", 1, min=1, max=100000, required=True),
            field("on_zero", "Hiç satır değişmezse", "select", "error", options=[
                {"value": "error", "label": "Akışı durdur"}, {"value": "continue", "label": "Devam et"}]),
            output("db_result")]),
    # ----- Akış ------------------------------------------------------------------------
    action("control.repeat", "Tekrarla (N kez)", "Akış",
           "İç adımları belirtilen sayıda çalıştırır; ${loop_index} 0'dan başlar.",
           [field("count", "Tekrar sayısı", "number", 3, min=1, max=10000, required=True)],
           container="loop", branches={"children": "TEKRARLA · İÇ ADIMLAR"}),
    action("control.try", "Hata olursa", "Akış",
           "İç adımlarda hata olursa akışı durdurmak yerine Hata olursa dalını çalıştırır; mesaj ${error_message}.",
           [field("error_name", "Hata mesajı değişkeni", default="error_message", required=True),
            field("screenshot", "Hata anında ekran görüntüsü kaydet", "boolean", False, omit_default=True,
                  help="Hata yakalandığı andaki ekran, çalışmanın çıktılarına PNG olarak eklenir; dosya yolu "
                       "${error_message_ekran} gibi hata değişkeninin adı + _ekran değişkenine yazılır.")],
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
    action("web.open", "Web sayfası aç", "Web, e-posta ve API",
           "Bilgisayardaki Edge veya Chrome ile sayfayı açar; sonraki web adımları bu sayfada çalışır. Tarayıcı, "
           "çalışma bitince kapanır; girişler ayrı RpaOrkestrAI profilinde hatırlanır.",
           [field("url", "Adres", default="https://", required=True, help="http:// veya https:// ile başlamalıdır."),
            field("browser", "Tarayıcı", "select", "auto", options=[
                {"value": "auto", "label": "Otomatik (Windows: Edge, Mac: Chrome)"},
                {"value": "msedge", "label": "Microsoft Edge"}, {"value": "chrome", "label": "Google Chrome"}]),
            field("headless", "Tarayıcıyı göstermeden çalıştır", "boolean", False, omit_default=True,
                  help="Açıkken pencere görünmez. Giriş veya doğrulama gereken sitelerde kapalı bırakın."),
            output("web_url", "Açılan sayfanın son adresi (yönlendirmelerden sonra).")]),
    action("web.click", "Web öğesine tıkla", "Web, e-posta ve API",
           "Açık sayfada düğme, bağlantı veya metne tıklar. Hedef birden fazla öğeyle eşleşirse tıklamaz.",
           WEB_TARGET),
    action("web.fill", "Web alanını doldur", "Web, e-posta ve API",
           "Açık sayfada bir yazı alanının değerini yazılan değerle değiştirir.",
           [*WEB_TARGET, field("text", "Yazılacak değer", default="", help="Değişken kullanılabilir: ${row.no}. "
                                                                           "Şifre için ${sifre.ad} kullanın.")]),
    action("web.read", "Web'den metin oku", "Web, e-posta ve API",
           "Açık sayfadaki bir öğenin metnini veya yazı alanının değerini okur.",
           [*WEB_TARGET, output("web_text")]),
    action("web.select", "Web listesinden seç", "Web, e-posta ve API",
           "Açık sayfadaki açılır listede (select) yazılan seçeneği seçer. Bulunamaz veya birden fazla eşleşirse seçmez.",
           [*WEB_TARGET, field("option", "Seçilecek seçenek", required=True,
                                help="Listede görünen ad. Tam eşleşme kapalıyken ad içinde geçmesi yeterlidir."),
            output("web_option", "Seçilen seçeneğin tam adı.")]),
    action("web.wait", "Web'de bekle", "Web, e-posta ve API",
           "Bir öğe görünene veya kaybolana ya da sayfa adresi bir metni içerene kadar bekler (ör. yükleniyor yazısı).",
           [field("condition", "Ne beklensin?", "select", "visible", required=True, options=[
                {"value": "visible", "label": "Öğe görünsün"}, {"value": "hidden", "label": "Öğe kaybolsun"},
                {"value": "url", "label": "Adres şu metni içersin"}]),
            *[{**f, "visible_when": {"condition": ["visible", "hidden"]}} for f in WEB_TARGET if f["name"] != "timeout"],
            field("url_text", "Adreste geçecek metin", required=True, visible_when={"condition": "url"},
                  help="Ör. /siparisler veya ?durum=tamam"),
            field("wait", "En fazla bekle (saniye)", "number", 30, min=0.5, max=600, required=True),
            field("on_missing", "Süre dolarsa", "select", "stop", required=True, options=[
                {"value": "stop", "label": "Akışı durdur"}, {"value": "continue", "label": "Yanlış sonucuyla devam et"}]),
            output("web_waited", "Koşul gerçekleştiyse doğru; süre dolduysa yanlış.")]),
    action("web.press", "Web'de tuşa bas", "Web, e-posta ve API",
           "Açık sayfada Enter, Tab, ok tuşları gibi bir tuşa basar; hedef verilirse önce o öğeye basar.",
           [field("key", "Tuş", "select", "Enter", required=True, options=[
                {"value": key, "label": label} for key, label in [
                    ("Enter", "Enter"), ("Tab", "Tab"), ("Escape", "Escape"), ("ArrowDown", "Aşağı ok"),
                    ("ArrowUp", "Yukarı ok"), ("ArrowLeft", "Sol ok"), ("ArrowRight", "Sağ ok"), ("PageDown", "Page Down"),
                    ("PageUp", "Page Up"), ("Home", "Home"), ("End", "End"), ("Space", "Boşluk"),
                    ("Backspace", "Backspace"), ("Delete", "Delete"), ("F5", "F5")]]),
            field("modifier", "Birlikte basılacak tuş", "select", "", omit_default=True, options=[
                {"value": "", "label": "Yok"}, {"value": "mod", "label": "Ctrl (Windows) / Command (Mac)"},
                {"value": "shift", "label": "Shift"}, {"value": "alt", "label": "Alt / Option"}]),
            *[{**f, "required": False} if f["name"] == "target" else f for f in WEB_TARGET]]),
    action("web.navigate", "Web'de geri / ileri / yenile", "Web, e-posta ve API",
           "Tarayıcının Geri, İleri veya Yenile düğmesine basar ve sayfanın yüklenmesini bekler.",
           [field("action", "İşlem", "select", "back", required=True, options=[
                {"value": "back", "label": "Geri"}, {"value": "forward", "label": "İleri"},
                {"value": "reload", "label": "Yenile"}]),
            output("web_url", "Gidilen sayfanın adresi.")]),
    action("web.tab", "Web sekmesine geç / kapat", "Web, e-posta ve API",
           "Açık sekmeler arasında geçer veya etkin sekmeyi kapatır. Sayfanın açtığı yeni sekmeye zaten "
           "kendiliğinden geçilir.",
           [field("action", "İşlem", "select", "last", required=True, options=[
                {"value": "last", "label": "Son açılan sekmeye geç"}, {"value": "first", "label": "İlk sekmeye geç"},
                {"value": "title", "label": "Başlığında şu geçen sekmeye geç"},
                {"value": "url", "label": "Adresinde şu geçen sekmeye geç"},
                {"value": "close", "label": "Etkin sekmeyi kapat"}]),
            field("match", "Aranacak metin", required=True, visible_when={"action": ["title", "url"]},
                  help="Tek bir sekmeyle eşleşmelidir; büyük/küçük harf fark etmez."),
            output("web_url", "Etkin sekmenin adresi.")]),
    action("web.read_table", "Web tablosunu oku", "Web, e-posta ve API",
           "Sayfadaki bir HTML tablosunu satır listesine çevirir; başlıklar alan adı olur. Ardından Her satır için ekleyin.",
           [*[{**f, "help": "Tablonun içindeki bir hücrenin yazısı (ör. bir sütun başlığı) veya tablonun CSS seçicisi "
                            "(ör. table#siparisler)."} if f["name"] == "target" else f for f in WEB_TARGET],
            field("header", "İlk satır sütun başlıklarıdır", "boolean", True,
                  help="Açıkken başlıklar alan adı olur: ${row.Tutar}. Kapalıyken sutun_1, sutun_2…"),
            output("web_rows")]),
    action("web.download", "Web'den dosya indir", "Web, e-posta ve API",
           "İndirmeyi başlatan bağlantıya veya düğmeye tıklar, inen dosyayı klasöre kaydeder ve yolunu verir.",
           [*WEB_TARGET,
            field("folder", "Kaydedilecek klasör", "path", "", required=True,
                  help="Klasör yoksa oluşturulur. Dosya, sitenin verdiği adla kaydedilir."),
            field("overwrite", "Aynı adlı dosyanın üzerine yaz", "boolean", False,
                  help="Kapalıyken aynı ad varsa sonuna (2), (3)… eklenir."),
            output("web_file", "İndirilen dosyanın tam yolu.")]),
    action("web.upload", "Web'e dosya yükle", "Web, e-posta ve API",
           "Sayfadaki dosya seçme alanına bilgisayardaki dosyaları verir (Gözat penceresi açılmaz).",
           [*[{**f, "help": "Dosya alanının etiketi (ör. Fatura dosyası) veya CSS seçicisi (ör. input[type=file])."}
              if f["name"] == "target" else f for f in WEB_TARGET],
            field("files", "Yüklenecek dosyalar", "code", "", required=True,
                  help="Her satıra bir dosya yolu. Bulunamayan dosya varsa hiçbiri yüklenmez.")]),
    action("web.screenshot", "Web sayfasının görüntüsünü al", "Web, e-posta ve API",
           "Açık sayfanın görüntüsünü çalışmanın çıktılarına PNG olarak ekler.",
           [field("filename", "Dosya adı", default="web-sayfasi.png", required=True, help="Uzantısı .png olur."),
            field("full_page", "Sayfanın tamamı (kaydırılan kısım dahil)", "boolean", True,
                  help="Kapalıyken yalnız ekranda görünen kısım alınır."),
            output("web_image", "Kaydedilen görüntünün yolu.")]),
    action("web.script", "Web'de JavaScript çalıştır", "Web, e-posta ve API",
           "Açık sayfada kendi JavaScript kodunuzu çalıştırır ve return ile döndürdüğünüz değeri değişkene kaydeder. "
           "Diğer web adımlarının yetmediği işler için.",
           [field("code", "JavaScript", "code", "return document.title;", required=True, raw=True,
                  help="async bir fonksiyonun gövdesi: await kullanılabilir, sonucu return ile verin. Akış "
                       "değişkenleri koda yazılmaz; Girdi alanından gelir: girdi.no"),
            field("input", "Girdi", "json", None,
                  help="Koda girdi adıyla verilen değer; değişken kullanılabilir: {\"no\": \"${row.no}\"}."),
            output("web_result", "return ile döndürülen değer (metin, sayı, liste veya nesne).")]),
    action("mail.send", "E-posta gönder", "Web, e-posta ve API",
           "Seçilen SMTP hesabından düz metin e-posta gönderir; ek dosya eklenebilir. Hata olursa yeniden denemez.",
           [MAIL_CONNECTION,
            field("to", "Kime", required=True, help="Virgül veya noktalı virgülle birden fazla adres: a@firma.com; b@firma.com"),
            field("cc", "Bilgi (CC)", default=""),
            field("bcc", "Gizli (BCC)", default=""),
            field("subject", "Konu", required=True, help="Değişken kullanılabilir: Fatura ${row.no} işlendi"),
            field("body", "İleti", "code", "", help="Düz metin. Değişken kullanılabilir."),
            field("attachments", "Ek dosyalar", "code", "",
                  help="Her satıra bir dosya yolu. Toplam en fazla 25 MB. Bulunamayan ek varsa gönderilmez."),
            field("in_reply_to", "Yanıtlanan e-posta (Message-ID)", default="", omit_default=True),
            output("mail_result", "Gönderilen adresler: ${mail_result.to}.")]),
    action("mail.read", "E-postaları oku", "Web, e-posta ve API",
           "Gelen kutusundaki (IMAP) e-postaları liste olarak okur: gönderen, konu, metin ve ekler. Okumak iletiyi "
           "okundu yapmaz; istenirse okundu işaretler ve ekleri bir klasöre kaydeder.",
           [IMAP_CONNECTION,
            field("folder", "Klasör", default="", omit_default=True,
                  help="Boş: bağlantıdaki klasör (genellikle INBOX). Ör. INBOX/Faturalar."),
            field("unread_only", "Yalnız okunmamışlar", "boolean", True),
            field("from_contains", "Gönderen içeriyorsa", default="", omit_default=True),
            field("subject_contains", "Konu içeriyorsa", default="", omit_default=True),
            field("since_days", "Son kaç gün (0: hepsi)", "number", 0, min=0, max=3650, omit_default=True),
            field("max_messages", "En fazla e-posta", "number", 20, min=1, max=200, required=True),
            field("mark_read", "Okunanları okundu olarak işaretle", "boolean", False, omit_default=True),
            field("attachment_folder", "Ekleri bu klasöre kaydet", default="", omit_default=True,
                  help="Boş bırakılırsa ekler kaydedilmez; yalnız adları ve boyutları listelenir."),
            output("emails", "E-posta listesi: Her satır için ile ${email.subject}, ${email.from}, ${email.text}.")]),
    action("ftp.transfer", "FTP dosya aktarımı", "Web, e-posta ve API",
           "FTP veya FTPS sunucusuna dosya yükler, sunucudan dosya indirir ya da klasördeki dosyaları listeler.",
           [FTP_CONNECTION,
            field("operation", "İşlem", "select", "download", options=[
                {"value": "download", "label": "Dosya indir"}, {"value": "upload", "label": "Dosya yükle"},
                {"value": "list", "label": "Klasörü listele"}]),
            field("remote_path", "Uzak yol", default="", help="Başlangıç klasörüne göre: gelen/fatura.xml veya gelen"),
            field("local_path", "Yerel dosya", default="", visible_when={"operation": ["download", "upload"]}),
            field("overwrite", "Varsa üzerine yaz", "boolean", False, visible_when={"operation": ["download", "upload"]}),
            output("ftp_result")]),
    action("notify.send", "Mesaj gönder (WhatsApp, Telegram, Teams…)", "Web, e-posta ve API",
           "WhatsApp, Telegram, Microsoft Teams, Slack, Google Chat veya Discord'a mesaj gönderir: hata bildirimi, "
           "günlük özet, müşteriye bilgi veya onay bekleyen iş haberi için.",
           [WEBHOOK_CONNECTION,
            field("title", "Başlık", default="", omit_default=True),
            field("text", "Mesaj", "code", "", required=True, help="Değişken kullanılabilir: ${row.no} numaralı fatura işlendi."),
            field("to", "Alıcı (WhatsApp, Telegram)", default="", omit_default=True),
            field("template_values", "Şablon değişkenleri (WhatsApp)", "code", "", omit_default=True),
            output("message_result")]),
    action("http.request", "HTTP isteği gönder (API)", "Web, e-posta ve API",
           "Bir web servisine istek gönderir; JSON yanıt ${response.body} içinde gelir.",
           [API_CONNECTION,
            field("method", "Yöntem", "select", "GET", options=[{"value": m, "label": m} for m in
                                                               ["GET", "POST", "PUT", "PATCH", "DELETE"]]),
            field("url", "Adres", default="https://", required=True), field("headers", "Başlıklar", "json", {}),
            field("body", "Gövde", "json", None, help="JSON nesnesi veya metin; GET'te gönderilmez."),
            field("timeout", "Zaman aşımı (saniye)", "number", 30, min=1, max=300),
            field("fail_on_error", "4xx/5xx yanıtında akışı durdur", "boolean", True), output("response")]),
]
CATEGORY_ORDER = ["Pencere", "Fare ve klavye", "Ekran ve görsel", "Uygulama ve sistem", "Dosya ve Excel",
                  "Veri ve metin", "Google Sheets", "Veritabanı", "Akış", "Kullanıcı etkileşimi", "Web, e-posta ve API"]
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
RETIRED = {"screen.find_image": "desktop.window_wait_image", "system.run_file": "system.command"}
for entry in CATALOG:
    if entry["type"] in RETIRED:
        entry["retired"] = RETIRED[entry["type"]]
ACTION_DEFINITIONS = ACTION_DEFINITIONS + [entry for entry in CATALOG if entry["type"] in RETIRED]
CATALOG = [entry for entry in CATALOG if entry["type"] not in RETIRED]
# Each library step's fixed number; retired steps have none.
for _entry in CATALOG:
    _entry["number"] = STEP_NUMBERS[_entry["type"]]  # a new library step needs its number in step_numbers.py
# Preview runs skip these (they touch the screen, files, network or other programs).
EXTERNAL_PREFIXES = ("database.", "desktop.", "browser.", "sheets.", "input.", "window.", "screen.", "system.",
                     "clipboard.", "file.", "ui.", "http.", "mail.", "web.", "ai.", "ftp.", "notify.")
CONTAINERS = {"control.for_each": ("children",), "control.while": ("children",), "control.repeat": ("children",),
              "control.if": ("children", "otherwise"), "control.try": ("children", "otherwise")}
LOOPS = {"control.for_each", "control.while", "control.repeat"}
# Nothing follows these on the same path; a step after one is reached only through Adıma git.
ENDINGS = {"control.goto", "control.continue", "control.break", "control.stop"}
# A single-step test may run these earlier steps by itself to get the values the tested step needs:
# they only compute or read, and never click, type or write.
TEST_PREPARE = {"file.read_pdf", "core.set", "data.append", "data.calculate", "text.transform", "data.date", "data.list", "data.sample",
                "desktop.find_window", "desktop.window_wait_image", "screen.find_image", "screen.read_text", "screen.wait_text", "screen.pixel",
                "input.mouse_position", "clipboard.get", "file.read_table", "file.read_text", "file.exists",
                "file.list", "sheets.read_cell", "sheets.read_rows", "sheets.read_column", "sheets.read",
                "database.read", "database.query", "ai.ask"}
# A test can show where these steps point (the mouse moves there) without clicking or typing.
LOCATABLE = {"window.write_table", "window.text_write", "window.checkbox", "desktop.window_click", "desktop.window_fill",
             "desktop.window_click_key", "window.read_field", "window.read_table",
             "input.mouse_click",
             "input.mouse_move", "screen.click_image"}


# Steps offered only with the separate agent license (MOD_AJAN). Saved flows keep them through
# ACTION_DEFINITIONS; running one without the license is refused by the agent service.
AGENT_STEPS = {"ai.ask"}


def library_catalog(agents: bool = True) -> list[dict[str, Any]]:
    return CATALOG if agents else [entry for entry in CATALOG if entry["type"] not in AGENT_STEPS]


def defaults(action_type: str) -> dict[str, Any]:
    return {f["name"]: f["default"] for f in BY_TYPE[action_type]["fields"]}
