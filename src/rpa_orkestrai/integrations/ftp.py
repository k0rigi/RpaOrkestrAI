"""FTP / FTPS file transfer. SFTP (SSH) is a different protocol and is not supported."""

from __future__ import annotations

import ftplib
import posixpath
import ssl
from pathlib import Path

from ..errors import WorkflowError


def describe(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("530") or "login" in message.lower():
        return "FTP kullanıcı adı veya şifresi kabul edilmedi."
    if message.startswith("550"):
        return "Uzak dosya veya klasör bulunamadı ya da erişim izni yok."
    if any(word in message.lower() for word in ("timed out", "refused", "unreachable", "getaddrinfo", "not known")):
        return "FTP sunucusuna ulaşılamadı. Sunucu adını, portu ve güvenlik duvarını kontrol edin."
    return f"FTP işlemi tamamlanamadı: {message.splitlines()[0][:200] if message else type(exc).__name__}"


def connect(config: dict, timeout: float = 30) -> ftplib.FTP:
    import certifi

    if config.get("security", "ftps") == "ftps":
        client: ftplib.FTP = ftplib.FTP_TLS(context=ssl.create_default_context(cafile=certifi.where()), timeout=timeout)
    else:
        client = ftplib.FTP(timeout=timeout)
    client.connect(config["host"], int(config.get("port") or 21))
    try:
        client.login(config.get("user") or "anonymous", config.get("password") or "")
        if isinstance(client, ftplib.FTP_TLS):
            client.prot_p()
        client.set_pasv(bool(config.get("passive", True)))
        base = config.get("base_dir") or "/"
        if base not in {"", "/"}:
            client.cwd(base)
    except BaseException:
        client.close()
        raise
    return client


def remote(path: str) -> str:
    """A path below the connection's start folder; ".." never leaves it."""
    clean = posixpath.normpath(str(path or ".").replace("\\", "/")).lstrip("/")
    if clean == ".." or clean.startswith("../"):
        raise WorkflowError("Uzak yol başlangıç klasörünün dışına çıkamaz (.. kullanmayın).")
    return clean or "."


def listing(client: ftplib.FTP, folder: str) -> list[dict]:
    try:
        return [{"name": name, "type": "folder" if facts.get("type") == "dir" else "file",
                 "size": int(facts["size"]) if facts.get("size", "").isdigit() else None,
                 "modified": facts.get("modify", "")}
                for name, facts in client.mlsd(folder) if facts.get("type") in {"file", "dir"}]
    except ftplib.error_perm:
        # Older servers have no MLSD; names are all they report.
        return [{"name": posixpath.basename(name), "type": "unknown", "size": None, "modified": ""}
                for name in client.nlst(folder)]


def exists(client: ftplib.FTP, path: str) -> bool:
    folder, name = posixpath.split(path)
    return any(item["name"] == name for item in listing(client, folder or "."))


def download(client: ftplib.FTP, source: str, target: Path, *, overwrite: bool) -> int:
    if target.exists() and not overwrite:
        raise WorkflowError(f"Hedef dosya zaten var: {target}. Üzerine yazmak için seçeneği açın.")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    try:
        with partial.open("wb") as handle:
            client.retrbinary(f"RETR {source}", handle.write)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target.stat().st_size


def upload(client: ftplib.FTP, source: Path, target: str, *, overwrite: bool) -> int:
    if not source.is_file():
        raise WorkflowError(f"Yüklenecek dosya bulunamadı: {source}")
    if not overwrite and exists(client, target):
        raise WorkflowError(f"Uzak dosya zaten var: {target}. Üzerine yazmak için seçeneği açın.")
    with source.open("rb") as handle:
        client.storbinary(f"STOR {target}", handle)
    return source.stat().st_size
