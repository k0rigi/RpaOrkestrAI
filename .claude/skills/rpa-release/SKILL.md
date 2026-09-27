---
name: rpa-release
description: RpaOrkestrAI'nin yeni sürümünü (ör. 0.5.0 → 0.6.0) derleyip orkestrai.net/rpa üzerinden yayınlamak ve kurulu uygulamalara otomatik güncelleme olarak ulaştırmak için kullan. Sürüm artırma, GitHub Actions derlemesi, imzalı bildirim, GitHub ön sürümü ve hosting yayın iş akışını kapsar.
---

# Sürüm yayınlama

Yayın dışa dönüktür: kurulu tüm uygulamalar yeni sürümü indirir. Kullanıcı açıkça "yayınla / devreye al" demediyse başlatmadan önce sor. Ayrıntılı mimari: `docs/guncelleme-mimarisi.md`.

Ortak değişkenler:

```bash
ROOT="/Users/k0rigi/Desktop/Web projeleri/RpaOrkestrAI"
PY="$HOME/Library/Application Support/RpaOrkestrAI/runtime/bin/python"
UV="$ROOT/.bootstrap/bin/uv"
SCRATCH=<oturumun geçici klasörü>   # iCloud dışında
V=0.6.0   # yeni sürüm
```

`gh` kurulu değildir. GitHub API'sini git kimlik bilgisiyle çağıran küçük bir yardımcıyı geçici klasörde oluştur ve belirteci ekrana yazdırma:

```bash
cat > "$SCRATCH/ghapi.sh" <<'EOF'
#!/bin/bash
TOKEN=$(printf "protocol=https\nhost=github.com\n\n" | git credential fill 2>/dev/null | sed -n 's/^password=//p')
M=$1; P=$2; shift 2
case "$P" in http*) URL="$P";; *) URL="https://api.github.com$P";; esac
curl -sS -X "$M" -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$URL" "$@"
EOF
chmod +x "$SCRATCH/ghapi.sh"
```

## 1. Sürümü hazırla

- `pyproject.toml` (`version`), `src/rpa_orkestrai/__init__.py` (`__version__`), `packaging/windows-installer.iss` (`AppVersion`) ve README'deki `RpaOrkestrAI-Setup-<V>-Windows-x64.exe` / `RpaOrkestrAI-<V>-macOS-arm64.dmg` adlarını güncelle.
- Kullanıcıya dönük değişiklikleri README ve `docs/` içine işle.
- `"$PY" -m pytest -p no:cacheprovider`, `"$PY" -m ruff check .`, `node --check src/rpa_orkestrai/static/app.js`.
- Commit + push. Push'ta **Python checks** yalnız Python 3.12'yi çalıştırır; yayından önce bir kez **Run workflow** ile tam 3.11–3.14 matrisini başlat (`POST /repos/k0rigi/RpaOrkestrAI/actions/workflows/tests.yml/dispatches`). macOS ve Windows'taki tüm işler başarılı olmalıdır.
- Önce Actions kotasını kontrol et (`GET /users/k0rigi/settings/billing/usage`; ücretsiz plan 2.000 dk, macOS 10×, Windows 2×). Bir tam matris + bir derleme kotanın yaklaşık %20'sini kullanır. Kota yetmeyecekse kullanıcıya sor.

## 2. Paketleri derle

```bash
"$SCRATCH/ghapi.sh" POST /repos/k0rigi/RpaOrkestrAI/actions/workflows/desktop-build.yml/dispatches -d '{"ref":"main"}'
```

**Build desktop apps** tamamlanınca artefaktları indir. Artefakt adları `RpaOrkestrAI-Windows-x64` (EXE) ve `RpaOrkestrAI-macOS` (DMG) şeklindedir. İndirme isteği `archive_download_url` adresine yönlendirilir; `curl -L` ile ZIP olarak indirip aç.

```bash
RUN=<run id>
"$SCRATCH/ghapi.sh" GET /repos/k0rigi/RpaOrkestrAI/actions/runs/$RUN/artifacts   # id + archive_download_url
"$SCRATCH/ghapi.sh" GET <archive_download_url> -L -o "$SCRATCH/win.zip"
```

`build-check-*` artefaktlarındaki `package-check.json` dosyasında `ok: true` ve `frozen: true` olduğunu kontrol et. Dosya adlarını `RpaOrkestrAI-Setup-$V-Windows-x64.exe` ve `RpaOrkestrAI-$V-macOS-arm64.dmg` olarak düzenle. Paketleri iCloud ile eşitlenen proje klasörüne değil, geçici klasöre (`$SCRATCH`) indir: her yayın ~1 GB geçici alan kullanır ve Masaüstü iCloud'a yüklenir. İşe başlamadan `df -h /` ile en az 2 GB boş alan olduğunu kontrol et; disk dolarsa araçlar dahil hiçbir şey dosya yazamaz.

## 3. İmzalı yayını hazırla

```bash
cd "$ROOT" && "$PY" scripts/prepare_update_release.py --version $V \
  --windows dist/release-$V/RpaOrkestrAI-Setup-$V-Windows-x64.exe \
  --macos-arm64 dist/release-$V/RpaOrkestrAI-$V-macOS-arm64.dmg \
  --signing-key credentials/update-signing-ed25519.pem \
  --output "$SCRATCH/update-site-$V" --archive "$SCRATCH/publish-bundle-$V.tar.gz"
shasum -a 256 "$SCRATCH/publish-bundle-$V.tar.gz"
```

Çıktı klasörü ve arşiv yeni olmalıdır. Betik, bildirimi uygulamanın gerçek güncelleme istemcisiyle doğrular.

## 4. GitHub ön sürümü ve aktarım bağlantısı

- `v$V-test.1` etiketiyle **prerelease** oluştur (`POST /repos/k0rigi/RpaOrkestrAI/releases`). `target_commitish` olarak paketlerin derlendiği commit'in tam SHA'sını ver. Başlık ve açıklama önceki sürümlerdeki gibi Türkçedir: değişiklikler, kurulum adresi, dosya adları, test sürümü uyarısı ve doğrulama kapsamı.
- EXE, DMG ve `publish-bundle-$V.tar.gz` dosyalarını `uploads.github.com/repos/k0rigi/RpaOrkestrAI/releases/<id>/assets?name=<ad>` adresine `Content-Type: application/octet-stream` ile yükle.
- Arşiv varlığının kısa ömürlü indirme adresini al: `GET /repos/k0rigi/RpaOrkestrAI/releases/assets/<asset id>` isteğini **yalnız** `Accept: application/octet-stream` başlığıyla yap ve yönlendirmeyi izleme. `ghapi.sh` kendi `Accept` başlığını da eklediği için burada doğrudan `curl -w "%{redirect_url}"` kullan. Adres `https://release-assets.githubusercontent.com/...` ile başlar ve kısa süre geçerlidir. Hemen kullan; ekrana, belgeye veya commit'e yazma.

## 5. orkestrai.net'e yayınla

Hosting deposunda (`k0rigi/orkestrai`) önce inceleme, sonra yayın çalıştır:

```bash
"$SCRATCH/ghapi.sh" POST /repos/k0rigi/orkestrai/actions/workflows/publish-rpa.yml/dispatches \
  -d '{"ref":"main","inputs":{"action":"inspect"}}'
"$SCRATCH/ghapi.sh" POST /repos/k0rigi/orkestrai/actions/workflows/publish-rpa.yml/dispatches \
  -d "{\"ref\":\"main\",\"inputs\":{\"action\":\"publish\",\"version\":\"$V\",\"bundle_sha256\":\"<sha>\",\"bundle_url\":\"<location>\"}}"
```

İş akışı arşivi doğrular, paketleri `releases/$V/` altına koyar ve `stable.manifest` dosyasını en son, atomik olarak yayımlar. Başarısız olursa iş günlüğünü oku; aktarım adresinin süresi dolduysa 4. adımdaki gibi yeni adres al.

İş *"recent account payments have failed or your spending limit needs to be increased"* notuyla hiç başlamıyorsa Actions kotası dolmuştur. Kullanıcıya sor: harcama limiti mi, ayın 1'ini beklemek mi, yoksa yerelden yayın mı? orkestrai kuralları sunucuya elle yüklemeyi yasaklar. **Yerelden yayın yalnız kullanıcının açık onayıyla** yapılır ve aynı betik aynı doğrulamalarla çalıştırılır:

```bash
"$UV" venv -p "$PY" "$SCRATCH/pubvenv" && "$UV" pip install -p "$SCRATCH/pubvenv/bin/python" 'paramiko>=3.5,<5'
export HOST=89.252.185.172 USERNAME=root
export PASSWORD=$(sed -n 's/.*şifre: "\([^"]*\)".*/\1/p' "../orkestrai/.agents/rules/orkestrai.md" | head -1)
RPA_ACTION=inspect "$SCRATCH/pubvenv/bin/python" scripts/deploy_update_bundle.py
RPA_ACTION=publish RPA_VERSION=$V RPA_BUNDLE_SHA256=<sha> RPA_BUNDLE_URL="$URL" \
  "$SCRATCH/pubvenv/bin/python" scripts/deploy_update_bundle.py
```

Şifreyi ekrana yazdırma. Sunucu anahtarı betikte sabittir; bilinmeyen anahtar reddedilir.

## 6. Doğrula

```bash
curl -s https://orkestrai.net/rpa/stable.manifest | python3 -c "import sys,json,base64;print(json.loads(base64.b64decode(json.load(sys.stdin)['payload']))['version'])"
curl -sI https://orkestrai.net/rpa/releases/$V/RpaOrkestrAI-Setup-$V-Windows-x64.exe | head -1
curl -sI https://orkestrai.net/rpa/releases/$V/RpaOrkestrAI-$V-macOS-arm64.dmg | head -1
```

İndirme sayfasının (`https://orkestrai.net/rpa/`) yeni sürümü gösterdiğini kontrol et. Kurulu uygulamalar yeni sürümü arka planda indirir ve bir sonraki açılışta kurar.

Son olarak geçici klasördeki paketleri, arşivi ve sanal ortamları sil; dosyalar GitHub ön sürümünde durur. Kullanıcıya yayınlanan sürümü, paket adlarını ve gerçek bilgisayarda yapılması gereken açılış kontrolünü bildir.
