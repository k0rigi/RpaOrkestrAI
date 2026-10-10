"""Prepare public desktop downloads and an authenticated update feed offline.

This command does not upload anything. The private key stays outside the output;
deployment must upload versioned assets first and stable.manifest last.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rpa_orkestrai import update_config  # noqa: E402
from rpa_orkestrai.updates import UpdateClient, UpdateError  # noqa: E402

BASE_URL = "https://orkestrai.net/rpa/"
PLATFORM_TYPES = {"windows-x64": "exe", "macos-arm64": "dmg", "macos-x64": "dmg"}


def _private_key(path: Path) -> Ed25519PrivateKey:
    try:
        value = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("İmza anahtarı okunamadı; Ed25519 PEM dosyasını kontrol edin.") from exc
    if not isinstance(value, Ed25519PrivateKey):
        raise ValueError("Güncelleme için Ed25519 özel anahtarı gereklidir.")
    public_key = base64.b64encode(value.public_key().public_bytes_raw()).decode("ascii")
    if public_key != update_config.PUBLIC_KEY:
        raise ValueError("İmza anahtarı uygulamaya gömülü yayıncı anahtarıyla eşleşmiyor.")
    return value


def _digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _download_page(version: str, assets: dict) -> str:
    cards = []
    for key, title, detail, instructions in (
        ("windows-x64", "Windows için indir", "Windows 10 / 11 · 64 bit",
         "EXE dosyasını açın, kurulumu tamamlayın ve masaüstündeki RpaOrkestrAI Studio kısayolunu kullanın."),
        ("macos-arm64", "Mac için indir", "Apple Silicon · M1 ve sonrası",
         "DMG dosyasını açın. RpaOrkestrAI uygulamasını Applications klasörüne sürükleyip oradan açın."),
        ("macos-x64", "Intel Mac için indir", "Intel işlemcili Mac · 64 bit",
         "DMG dosyasını açın. RpaOrkestrAI uygulamasını Applications klasörüne sürükleyip oradan açın."),
    ):
        if key not in assets:
            continue
        asset = assets[key]
        cards.append(
            f'<article><p class="platform">{detail}</p><h2>{title}</h2><p>{instructions}</p>'
            f'<a class="download" href="{html.escape(asset["url"], quote=True)}" download>'
            f'İndir · {asset["type"].upper()} · {asset["size"] / 1024**2:.1f} MB</a></article>'
        )
    return f'''<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="RpaOrkestrAI Studio için Windows ve macOS masaüstü uygulamasını indirin.">
<title>RpaOrkestrAI Studio · İndir</title>
<style>
:root{{color-scheme:light;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#151a26;background:#edeae1}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1080px;margin:auto;padding:56px 24px 72px}}
header{{background:#151a26;color:white;border-radius:24px;padding:40px;margin-bottom:28px}}
.brand{{font-weight:750;letter-spacing:-.6px;font-size:22px}}.mark{{display:inline-grid;place-items:center;width:30px;height:30px;margin-right:8px;border-radius:6px;background:#ffd23f;color:#151a26;font-weight:800;vertical-align:middle}}h1{{font-size:clamp(32px,5vw,54px);
line-height:1.08;max-width:720px;letter-spacing:-1.8px;margin:32px 0 20px}}header p{{max-width:680px;color:#d4d6dc}}
p{{line-height:1.65}}.version{{display:inline-block;border:1px solid #4a5368;border-radius:30px;padding:6px 14px;
font-size:14px;margin-top:12px}}.downloads{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));
gap:20px}}article{{border:1px solid #d8d3c4;border-radius:18px;background:white;padding:28px;display:flex;
flex-direction:column}}article h2{{margin:8px 0;font-size:25px}}article p{{color:#5d6270}}.platform{{font-size:13px;
font-weight:600;margin:0}}.download{{display:block;background:#ffd23f;color:#151a26;padding:15px 18px;border-radius:10px;
font-weight:700;text-align:center;text-decoration:none;margin-top:auto}}.download:focus-visible{{outline:3px solid
#151a26;outline-offset:4px}}.download:hover{{background:#f2c21a}}.note{{max-width:850px;margin:30px 0 0;color:#5d6270;
font-size:14px}}footer{{border-top:1px solid #d8d3c4;margin-top:36px;padding-top:20px;font-size:13px;color:#5d6270}}
@media(max-width:540px){{main{{padding:20px 16px 40px}}header{{padding:26px}}}}
</style></head><body><main><header><div class="brand"><span class="mark" aria-hidden="true">O</span>RpaOrkestrAI Studio</div>
<h1>İşlerinize akış kazandırın.</h1><p>Masaüstü uygulamanızı bir kez kurun. Akışlarınızı bilgisayarınızda oluşturun;
yayımlanan yeni sürümler uygulama açıldığında otomatik kontrol edilsin.</p>
<span class="version">Sürüm {html.escape(version)}</span></header>
<section class="downloads" aria-label="Bilgisayarınıza uygun sürümü indirin">{''.join(cards)}</section>
<p class="note"><strong>Uygulama orkestrai.net kullanıcı adınız ve şifrenizle açılır.</strong>
Kullanım için firmanızda ve hesabınızda RpaOrkestrAI lisansı tanımlı olmalıdır; lisans için firma yöneticinize başvurun.</p>
<p class="note">Python veya sanal ortam kurmanız gerekmez. Uygulama terminal açmadan çalışır.
Windows için Microsoft Edge WebView2 gerekir; eksikse kurulum yönlendirmesini izleyin.
Mac'te ERP pencerelerini tanımak ve kontrol etmek için Ekran Kaydı ve Erişilebilirlik izinleri gerekir.</p>
<p class="note">Bu dağıtımda Apple noter onayı ve Windows yayıncı sertifikası henüz yoktur;
işletim sistemi veya şirketinizin kuralları ilk kurulumda ek onay isteyebilir.
Güncelleme dosyaları uygulama tarafından yayıncı anahtarıyla doğrulanır.</p>
<footer>Akışlarınız ve bağlantı ayarlarınız güncelleme sırasında korunur.
Yeni sürüm arka planda indirilir ve sonraki açılışta yüklenir.</footer>
</main></body></html>'''


def prepare_release(
    *, version: str, windows: Path, macos_arm64: Path, signing_key: Path, output: Path,
    macos_x64: Path | None = None, expires_in_days: int = 90, archive: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Build in a private temporary directory, verify, then expose the result."""
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ValueError("Kararlı sürümü 0.2.0 biçiminde belirtin.")
    if not 1 <= expires_in_days <= 365:
        raise ValueError("Bildirimin geçerlilik süresi 1–365 gün arasında olmalıdır.")
    output = Path(output).expanduser().absolute()
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("Yayın çıktısı için yeni veya boş bir klasör seçin.")
    signing_key = Path(signing_key).expanduser().resolve(strict=True)
    if signing_key.is_relative_to(output.resolve()):
        raise ValueError("Özel imza anahtarı yayın klasöründe bulunamaz.")
    key = _private_key(signing_key)
    sources = {"windows-x64": Path(windows), "macos-arm64": Path(macos_arm64)}
    if macos_x64 is not None:
        sources["macos-x64"] = Path(macos_x64)
    names = set()
    for platform_key, source in sources.items():
        expected_type = PLATFORM_TYPES[platform_key]
        if (source.is_symlink() or not source.is_file() or source.stat().st_size == 0
                or source.resolve() == signing_key
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\." + expected_type, source.name)):
            raise ValueError(f"{platform_key} için geçerli bir .{expected_type} paket dosyası seçin.")
        if source.name in names:
            raise ValueError("Her platformun paket dosyası farklı bir ada sahip olmalıdır.")
        names.add(source.name)
    if archive is not None:
        archive = Path(archive).expanduser().absolute()
        if archive.exists() or archive.is_symlink() or archive.resolve().is_relative_to(output.resolve()):
            raise ValueError("Dağıtım arşivi yayın klasörü dışında yeni bir dosya olmalıdır.")
    published = now or datetime.now(timezone.utc)
    if published.tzinfo is None:
        raise ValueError("Yayın tarihi saat dilimi içermelidir.")
    published = published.astimezone(timezone.utc).replace(microsecond=0)
    def timestamp(date: datetime) -> str:
        return date.isoformat().replace("+00:00", "Z")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".rpa-release-", dir=output.parent) as temporary:
        staging = Path(temporary) / "site"
        release_dir = staging / "releases" / version
        release_dir.mkdir(parents=True)
        assets, known_files = {}, []
        for platform_key, source in sources.items():
            destination = release_dir / source.name
            shutil.copyfile(source, destination)
            known_files.append(destination.relative_to(staging))
            assets[platform_key] = {
                "url": f"{BASE_URL}releases/{version}/{source.name}",
                "size": destination.stat().st_size,
                "sha256": _digest(destination),
                "type": PLATFORM_TYPES[platform_key],
            }
        payload = json.dumps({
            "schema": 1, "channel": "stable", "version": version,
            "published_at": timestamp(published),
            "expires_at": timestamp(published + timedelta(days=expires_in_days)),
            "assets": assets,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = json.dumps({
            "payload": base64.b64encode(payload).decode("ascii"),
            "signature": base64.b64encode(key.sign(payload)).decode("ascii"),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        client = UpdateClient(update_config.FEED_URL, update_config.PUBLIC_KEY,
                              cache_dir=Path(temporary) / "verification", now=lambda: published,
                              os_version="99.0.0")
        for platform_key, source in sources.items():
            check = client.authenticate_manifest(envelope, "0.0.0", platform_key)
            if check.status != "available" or check.release is None:
                raise ValueError(f"Yayın bildirimi uygulama tarafından doğrulanamadı: {check.message}")
            client.verify_download(check.release, release_dir / source.name)
        (staging / "index.html").write_text(_download_page(version, assets), encoding="utf-8")
        (staging / "stable.manifest").write_bytes(envelope)
        known_files.extend([Path("index.html"), Path("stable.manifest")])
        if archive is not None:
            archive.parent.mkdir(parents=True, exist_ok=True)
            # Whitelisted files only: never recursively archive a working directory.
            with tempfile.NamedTemporaryFile(prefix=".rpa-publish-", dir=archive.parent, delete=False) as handle:
                temporary_archive = Path(handle.name)
            try:
                with tarfile.open(temporary_archive, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
                    for relative in sorted(known_files):
                        path = staging / relative
                        info = bundle.gettarinfo(str(path), arcname=relative.as_posix())
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mode = 0o644
                        with path.open("rb") as handle:
                            bundle.addfile(info, handle)
                if archive.exists():
                    raise ValueError("Dağıtım arşivi zaten var; yeni bir dosya adı seçin.")
                temporary_archive.replace(archive)
            finally:
                temporary_archive.unlink(missing_ok=True)
        if output.exists():
            output.rmdir()
        staging.replace(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="İmzalı RpaOrkestrAI güncelleme ve indirme yayınını hazırla")
    parser.add_argument("--version", required=True)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--macos-arm64", required=True, type=Path)
    parser.add_argument("--macos-x64", type=Path)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "update-site")
    parser.add_argument("--expires-in-days", type=int, default=90)
    parser.add_argument("--archive", type=Path, help="İsteğe bağlı, yalnız yayın dosyalarını içeren .tar.gz arşivi")
    arguments = parser.parse_args(argv)
    try:
        destination = prepare_release(**vars(arguments))
    except (OSError, ValueError, UpdateError) as exc:
        parser.exit(1, f"Yayın hazırlanamadı: {exc}\n")
    print(f"Verified release ready: {destination}")
    print("Upload versioned packages first and stable.manifest last.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
