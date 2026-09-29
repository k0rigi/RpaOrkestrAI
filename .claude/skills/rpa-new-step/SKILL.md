---
name: rpa-new-step
description: RpaOrkestrAI adım kütüphanesine yeni bir adım türü (ör. yeni pencere, Sheets, web veya kontrol adımı) ya da mevcut adıma yeni bir hedef yöntemi eklerken kullan. Katalog, motor, arayüz, testler ve macOS/Windows uyumunu birlikte ele alır.
---

# Yeni adım ekleme

Kullanıcının akışına adım eklemesi yereldir. **Yeni adım türü** ise kodla eklenir ve yeni sürümle tüm kurulumlara ulaşır. Bu nedenle iş bitince sürüm yayını gerekir (`rpa-release`).

## 1. İhtiyacı netleştir

- Adım ne okur, ne yazar, ERP'ye hangi girişi gönderir? Hata/bulunamadı durumunda akış durmalı mı, devam mı etmeli?
- İki platformda nasıl çalışacak? macOS'ta hangi izin (Ekran Kaydı, Erişilebilirlik, Otomasyon), Windows'ta hangi API gerekir?
- Belirsizlik varsa uygulamaya geçmeden kullanıcıya sor.

## 2. Katalog (`src/rpa_orkestrai/catalog.py`)

- Yeni adımı `CATALOG` listesine `action(type, label, category, description, fields)` ile ekle. Tür adı `alan.eylem` biçimindedir; dış sistem adımları `desktop.`, `sheets.`, `browser.` veya `database.` önekini kullanır. Önizleme modu bu önekli adımları atlar.
- Alanlar `field(name, label, kind, default, ...)` ile tanımlanır. Türler: `text`, `number` (`min`/`max`), `select` (`options`), `boolean`, `json`, `columns`, `element`. Koşullu alan için `visible_when={"alan": değer}` ya da birden fazla değer için `{"alan": [değer1, değer2]}` kullan.
- Pencere hedefli adımlar `WINDOW` ve `target_fields()` alanlarını yeniden kullanır.
- Eski bir adım kütüphaneden kaldırılacaksa tanımını `ACTION_DEFINITIONS` listesine taşı. Kayıtlı akışlar açılmaya ve çalışmaya devam etmelidir.

## 3. Çalıştırıcı (`src/rpa_orkestrai/actions/`)

- Yeni adımın çalıştırıcısını uygun modüle `@handler("tür")` ile ekle: `inputs` (fare/klavye), `windows`, `screen`, `system`, `files`, `data`, `dialogs`, `web`. İşlev `(ctx, p)` alır ve adımın sonucunu döndürür. `ctx` motordur: `desktop()`, `windows()`, `wait()`, `check_cancelled()`, `save_artifact()`, `variables` ve `config`.
- Argümanları `actions/common.py` içindeki yardımcılarla doğrula: `number`, `integer`, `text`, `choice`, `path` ve `region`. Hata mesajı Türkçe `WorkflowError` olmalıdır.
- Ekrana, dosyaya veya ağa dokunan adımın tür öneki `catalog.EXTERNAL_PREFIXES` içinde olmalıdır; önizleme bu adımları atlar.
- Yeni blok adımları (alt adım içeren) `catalog.CONTAINERS` ve `LOOPS` ile tanımlanır; motordaki `steps()` dalına eklenir.
- `tests/test_actions_data.py::test_every_library_step_has_a_handler` testi eksik çalıştırıcıyı yakalar.

## 3b. Motor (`src/rpa_orkestrai/engine.py`)

- Yalnız akış kontrolü motorda kalır; diğer adımlar `actions/` içine yazılır. Parametre türlerini ve aralıklarını doğrula, kullanıcıya Türkçe `WorkflowError` göster.
- Yerel kütüphaneleri (pyobjc, comtypes, pyautogui, gspread…) fonksiyon içinde içe aktar. Pencere işlemleri `WindowService` üzerinden geçer. Bu servis odak, pencere kimliği ve ana ekran kontrollerini zaten yapar; bu kontrolleri atlama.
- ERP'ye giriş gönderen adımlar tahmini konuma asla tıklamaz. Belirsizlikte hata verip durur.

## 4. Arayüz (`src/rpa_orkestrai/static/app.js`, `styles.css`)

- Standart alan türleri denetçide otomatik çizilir. Özel bir alan türü gerekiyorsa `renderInspector` içindeki `columns`/`element` örneğini izle.
- Tüm metinler Türkçe olmalıdır. Arayüz 980 px genişlikte ve mobil tarayıcı genişliğinde bozulmamalıdır.
- `node --check src/rpa_orkestrai/static/app.js` ile sözdizimini kontrol et.

## 5. İki platform

- Kısayollarda `mod` kullan. Dosya yollarında `pathlib`, platform ayrımında `platform.system()` kullan.
- Yeni bağımlılığı `pyproject.toml` içindeki `automation` grubuna platform işaretçisiyle ekle. Yerel ortama da kur: `.bootstrap/bin/uv pip install -p "$PY" "<paket>"`.
- PyInstaller'ın dinamik içe aktarmaları görmediği durumda `scripts/build_desktop.py` dosyasına `--hidden-import` veya `--collect-submodules` ekle. Paket içinde yüklenebildiğini `package_check.py` öz-testine ekle.
- Bu Mac'te çalıştırılamayan Windows kodu için `pytest.mark.skipif(platform.system() != "Windows")` ile gerçek bir Windows testi yaz. Bu test CI'daki `windows-latest` üzerinde koşar.

## 6. Testler

- Birim testlerinde gerçek ekrana/ERP'ye asla giriş gönderme; `Mock` ve sahte arka uçlar kullan (`tests/test_windows.py`, `tests/test_elements.py` örnekleri).
- Doğrulama hatalarında `activate`/`click`/`write` çağrılmadığını da test et.
- Çalıştır:

```bash
PY="$HOME/Library/Application Support/RpaOrkestrAI/runtime/bin/python"
"$PY" -m pytest -p no:cacheprovider && "$PY" -m ruff check .
```

## 7. Belgeler ve teslim

- `README.md` içindeki adım havuzu ve tabloyu, ilgili `docs/*.md` rehberini güncelle (ör. pencere adımları için `docs/pencere-tanitma.md`).
- Commit + push sonrası GitHub'daki **Python checks** iş akışının macOS ve Windows işlerinin hepsinin başarılı olduğunu kontrol et.
- Sürüm yayını için `rpa-release` skill'ine geç.
