# RpaOrkestrAI — proje kuralları

RpaOrkestrAI, orkestrai.net'in bir modülü olarak satılan, yerelde çalışan görsel RPA Studio'dur (FastAPI + statik HTML/CSS/JS + pywebview). Kurulum paketleri Windows EXE ve macOS DMG olarak orkestrai.net/rpa üzerinden dağıtılır. Arayüz, belgeler, commit mesajları ve kullanıcıya dönük tüm metinler Türkçedir.

## Kurallar

1. **Her özellik macOS ve Windows'ta çalışmalıdır.** Platforma özel kod `platform.system()` ile ayrılır ve yerel kütüphaneler (pyobjc, comtypes, ctypes/winreg) fonksiyon içinde, ihtiyaç anında içe aktarılır. Kısayollarda `mod` kullanılır (macOS'ta Command, Windows'ta Ctrl). Yollar `pathlib` ile kurulur. İzin gerektiren işlerde (macOS Ekran Kaydı/Erişilebilirlik, Windows odak/UAC) iki platformun hata mesajı da yazılır.
   - Yeni bağımlılık `pyproject.toml` içinde platform işaretçisiyle (`sys_platform == 'darwin'` / `'win32'`) eklenir. PyInstaller'ın göremediği modüller `scripts/build_desktop.py` içine, yüklenebildiği ise `package_check.py` öz-testine ve `.github/workflows/tests.yml` içine eklenir.
   - Bu Mac'te çalıştırılamayan Windows kodu için Windows CI'da çalışan gerçek bir test yazılır (ör. `tests/test_elements_native.py`). Push sonrası iki platformun CI sonucu kontrol edilmeden iş bitti sayılmaz.
2. **Lisans kuralı bozulmaz.** Kullanıcının uygulamayı kullanması için hem firmasında hem kendi hesabında `MOD_RPA` açık, firma `BitisTarihi` dolmamış olmalıdır. Yeni `/api/` uçları lisans kapısının arkasında kalır; `licensing.OPEN_PATHS` yalnız sağlık, kimlik ve lisans uçları içindir. `LICENSE_PUBLIC_KEY` değişirse kurulu uygulamalar ancak yeni sürümle doğrulayabilir.
3. **ERP'ye tahmini giriş yapılmaz.** Hedef bulunamazsa, pencere/odak değişirse veya belirsiz eşleşme varsa adım durur; tıklama veya yazma yapılmaz.
4. **Kullanıcıya dönük değişiklikte belgeler güncellenir:** `README.md` ve ilgili `docs/*.md`. Sürüm artışında `pyproject.toml`, `src/rpa_orkestrai/__init__.py`, `packaging/windows-installer.iss` ve README'deki dosya adları birlikte değişir.
5. **Sunucu tarafı** (`../orkestrai`, orkestrai.net hosting deposu) SSH/SFTP ile elle güncellenmez. Değişiklik commit + push ile gönderilir; `Deploy to Server` iş akışı sunucuyu günceller ve gunicorn'u yeniden başlatır. Sunucu Python 3.6.8 ile çalışır ve `cryptography` kurulu değildir; kod 3.6 uyumlu olmalıdır (`uvx vermin -t=3.6-`). O depoya yalnız RPA yayın araçları eklenirken commit mesajına `[skip ci]` konur. O deponun `.agents/rules/orkestrai.md` kuralları da geçerlidir.
6. **Gizli bilgiler:** güncelleme imza anahtarı `credentials/update-signing-ed25519.pem` içindedir ve Git'e, pakete veya sunucuya girmez. Lisans imza anahtarı yalnız sunucuda, web klasörü dışında durur.
7. **GitHub Actions maliyeti:** Ücretsiz kota ayda 2.000 dakikadır; macOS dakikası 10, Windows dakikası 2 kat sayılır ve harcama limiti 0 $'dır. Push'ta CI yalnız Python 3.12'yi (macOS + Windows) çalıştırır. Tam 3.11–3.14 matrisini (`Python checks → Run workflow`) ve `Build desktop apps` derlemesini yalnız yayın öncesinde, birer kez başlat; gereksiz push ve yeniden derlemeden kaçın. Kullanım: `GET /users/k0rigi/settings/billing/usage`. Kota dolduysa kullanıcıya sor: harcama limiti, ayın 1'ini beklemek veya (onayla) yerelden yayın. Ücret doğuracak her adımı önceden bildir.
8. **Kural önerileri:** Çalışırken bu projede tekrar edecek, faydalı bir kural fark edersen önce kullanıcıya sor. Kullanıcı onaylarsa bu listeye kısa ve gerekçeli olarak ekle. Onay almadan kural ekleme.

## Komutlar

Proje iCloud ile eşitlenen Masaüstü'nde olduğundan içindeki `.venv` çok yavaştır. Testler ve araçlar için iCloud dışındaki çalışma ortamını kullan:

```bash
PY="$HOME/Library/Application Support/RpaOrkestrAI/runtime/bin/python"
"$PY" -m pytest -p no:cacheprovider      # tüm testler (lisans kapısı conftest ile taklit edilir)
"$PY" -m ruff check .
node --check src/rpa_orkestrai/static/app.js
```

Bağımlılık eklendiyse aynı ortama kur: `.bootstrap/bin/uv pip install -p "$PY" "<paket>"`. `gh` CLI kurulu değildir; GitHub API'si için git kimlik bilgisi kullanılır (bkz. `rpa-release` skill).

## Yapı

| Yol | Görev |
| --- | --- |
| `src/rpa_orkestrai/app.py` | Yerel FastAPI uygulaması; kaynak kontrolü, lisans kapısı, Studio uçları |
| `src/rpa_orkestrai/licensing.py` | orkestrai.net lisansı: her açılışta ve 10 dakikada bir taze imzalı onay (isteğe özel rastgele değer), cihaz bağlama, tek bilgisayar oturumu, bağlantısız en fazla 60 dk; diskteki hiçbir şey Studio'yu açmaz |
| `src/rpa_orkestrai/catalog.py` | Adım kütüphanesi ve form alanları (`CATALOG`, eski akışlar için `ACTION_DEFINITIONS`) |
| `src/rpa_orkestrai/guide.py` | Her adımın "Nasıl kullanılır?" özeti ve alan açıklamaları; yeni adım/alan eklenince burası da doldurulur (test zorunlu kılar) |
| `src/rpa_orkestrai/connections.py` | Adlandırılmış Sheets/veritabanı bağlantıları (`data/connections.json`); adım `connection` alanıyla seçer, gizli bilgiler dışa aktarılmaz |
| `src/rpa_orkestrai/engine.py` | Akış doğrulama, çalıştırma, akış kontrolü (tekrarla, döngüden çık, hata olursa, alt akış), tek adım testi |
| `src/rpa_orkestrai/actions/` | Adım çalıştırıcıları: `inputs`, `windows`, `screen`, `system`, `files`, `data`, `dialogs`, `web`; `@handler("tür")` ile kaydolur |
| `src/rpa_orkestrai/desktop/` | Pencere (`windows.py`), alan kimliği (`elements.py`), hedef seçici (`picker.py`), görsel eşleştirme, sistem OCR'ı (`ocr.py`: macOS Vision, Windows.Media.Ocr) |
| `src/rpa_orkestrai/static/` | Studio arayüzü (derleme adımı yok); akış Liste ve Diyagram (soldan sağa, n8n tarzı) görünümünde düzenlenir. `styles.css` içindeki tüm renkler `:root` tema değişkenleridir (açık + `[data-theme="dark"]`); sabit renk yazılmaz. Yazı tipleri `static/fonts/` içinde paketlenir |
| `src/rpa_orkestrai/updates.py`, `update_service.py` | İmzalı güncelleme bildirimi ve kurulum |
| `scripts/` | Paket derleme, yayın hazırlama, hosting yayın betiği |

## Skill'ler

- `rpa-release` — yeni sürümü derleyip orkestrai.net/rpa üzerinden yayınlama.
- `rpa-new-step` — adım kütüphanesine iki platformda çalışan yeni adım ekleme.
- `rpa-license-admin` — firmaya/kullanıcıya MOD_RPA lisansı verme, uzatma ve lisans sorunlarını inceleme.
