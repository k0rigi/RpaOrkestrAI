"""Publish only RpaOrkestrAI's static /rpa/ files through the existing SSH host.

Copy this standalone script to the hosting repository's
.github/scripts/publish-rpa.py. No web service, database or other site is changed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shlex
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BUNDLE_HOST = "release-assets.githubusercontent.com"
MAX_BUNDLE = 1024**3
REMOTE_ROOT = "/home/orkestrai.net/public_html/rpa"
# Public host key already trusted in the operator's known_hosts, not a secret.
HOST_ED25519 = "AAAAC3NzaC1lZDI1NTE5AAAAIPUVhfiU2qevA8m7fINyiSWxSOZXczcLVj/KpfRHo/+S"
# Same public update trust anchor shipped in rpa_orkestrai.update_config.
UPDATE_PUBLIC_KEY = "MmqvE+JGXTNZ9YSoaXjR1fMBVP6PIiLGk3Huy8O/P1U="

# The remote program uses only Python's standard library. Its root is fixed;
# every archive member is created explicitly instead of using extractall().
REMOTE_CODE = r'''
import base64
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path('/home/orkestrai.net/public_html/rpa')
BASE_URL = 'https://orkestrai.net/rpa/'
LIMIT = 1024**3
VERSION_PATTERN = r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)'

def ensure_root(create=False):
    if ROOT.parent.resolve() != ROOT.parent or ROOT.is_symlink() or ROOT.resolve() != ROOT:
        raise ValueError('The fixed publication directory must not be a symlink.')
    if create:
        ROOT.mkdir(mode=0o755, exist_ok=True)
    if ROOT.exists() and not ROOT.is_dir():
        raise ValueError('The publication path is not a directory.')

def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()

def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate manifest field.')
        value[key] = item
    return value

def manifest_payload(raw):
    if len(raw) > 128 * 1024:
        raise ValueError('Manifest is too large.')
    envelope = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
    if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
        raise ValueError('Unexpected manifest envelope.')
    signature = base64.b64decode(envelope['signature'], validate=True)
    if len(signature) != 64:
        raise ValueError('Invalid manifest signature length.')
    payload = json.loads(base64.b64decode(envelope['payload'], validate=True).decode('utf-8'),
                         object_pairs_hook=unique_object)
    if not isinstance(payload, dict):
        raise ValueError('Invalid manifest payload.')
    return payload

def current_version():
    path = ROOT / 'stable.manifest'
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ValueError('Existing manifest cannot be inspected safely.')
    version = manifest_payload(path.read_bytes()).get('version')
    if not isinstance(version, str) or not re.fullmatch(VERSION_PATTERN, version):
        raise ValueError('Existing manifest version is invalid.')
    return version

def inspect_root():
    ensure_root()
    return {'ok': True, 'action': 'inspect', 'exists': ROOT.exists(),
            'readable': os.access(ROOT if ROOT.exists() else ROOT.parent, os.R_OK),
            'writable': os.access(ROOT if ROOT.exists() else ROOT.parent, os.W_OK),
            'current_version': current_version(),
            'python_version': '.'.join(str(part) for part in sys.version_info[:3])}

def utc_timestamp(value):
    # The publisher emits UTC Z timestamps. strptime also works on Python 3.6,
    # unlike datetime.fromisoformat which was introduced in Python 3.7.
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value):
        raise ValueError('Manifest dates are not valid.')
    pattern = '%Y-%m-%dT%H:%M:%S.%fZ' if '.' in value else '%Y-%m-%dT%H:%M:%SZ'
    try:
        return datetime.strptime(value, pattern).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError('Manifest dates are not valid.')

def unpack_verified(bundle, staging, version):
    known = {}
    total = 0
    pattern = (r'releases/' + re.escape(version) +
               r'/[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.(?:exe|dmg)')
    with tarfile.open(bundle, 'r:gz') as archive:
        for member in archive:
            name = member.name
            if (not member.isfile() or name in known or len(known) >= 5
                    or not (name in {'index.html', 'stable.manifest'} or re.fullmatch(pattern, name))):
                raise ValueError('Archive contains an unexpected member or link.')
            limit = 128 * 1024 if name == 'stable.manifest' else (256 * 1024 if name == 'index.html' else LIMIT)
            total += member.size
            if not 0 < member.size <= limit or total > LIMIT:
                raise ValueError('Archive exceeds publication size limits.')
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            count = 0
            value = hashlib.sha256()
            source = archive.extractfile(member)
            if source is None:
                raise ValueError('Archive member is not readable.')
            with source, target.open('xb') as destination:
                while True:
                    chunk = source.read(min(1024 * 1024, member.size - count + 1))
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > member.size:
                        raise ValueError('Archive member size changed.')
                    value.update(chunk)
                    destination.write(chunk)
            if count != member.size:
                raise ValueError('Archive member is incomplete.')
            target.chmod(0o644)
            known[name] = (count, value.hexdigest())
    if not {'index.html', 'stable.manifest'} <= set(known):
        raise ValueError('Publication page or manifest is missing.')
    data = manifest_payload((staging / 'stable.manifest').read_bytes())
    if data.get('schema') != 1 or data.get('channel') != 'stable' or data.get('version') != version:
        raise ValueError('Manifest does not describe the requested stable version.')
    now = datetime.now(timezone.utc)
    published = utc_timestamp(data.get('published_at'))
    expires = utc_timestamp(data.get('expires_at'))
    if (published.tzinfo is None or expires.tzinfo is None or published > now + timedelta(minutes=10)
            or expires <= now or expires <= published):
        raise ValueError('Manifest dates are not valid.')
    assets = data.get('assets')
    types = {'windows-x64': 'exe', 'macos-arm64': 'dmg', 'macos-x64': 'dmg'}
    if (not isinstance(assets, dict) or not {'windows-x64', 'macos-arm64'} <= set(assets)
            or set(assets) - set(types)):
        raise ValueError('Required platform packages are missing.')
    expected = {'index.html', 'stable.manifest'}
    for platform, asset in assets.items():
        if not isinstance(asset, dict) or asset.get('type') != types[platform]:
            raise ValueError('Unexpected platform package type.')
        url = asset.get('url')
        prefix = BASE_URL + 'releases/' + version + '/'
        if not isinstance(url, str) or not url.startswith(prefix):
            raise ValueError('Package URL is outside the publication directory.')
        relative = 'releases/' + version + '/' + url[len(prefix):]
        if (not re.fullmatch(pattern, relative) or not relative.endswith('.' + types[platform])
                or relative in expected or type(asset.get('size')) is not int
                or known.get(relative) != (asset['size'], asset.get('sha256'))):
            raise ValueError('Package bytes do not match the signed manifest.')
        expected.add(relative)
    if set(known) != expected:
        raise ValueError('The archive has files not declared by the manifest.')
    return known

def publish(version, expected_hash, token):
    if (not re.fullmatch(VERSION_PATTERN, version) or not re.fullmatch(r'[0-9a-f]{64}', expected_hash)
            or not re.fullmatch(r'[0-9a-f]{32}', token)):
        raise ValueError('Invalid publication arguments.')
    ensure_root(create=True)
    bundle = ROOT / ('.upload-' + token + '.tar.gz')
    if bundle.is_symlink() or not bundle.is_file() or not 0 < bundle.stat().st_size <= LIMIT:
        raise ValueError('Uploaded bundle is not a regular bounded file.')
    try:
        if digest(bundle) != expected_hash:
            raise ValueError('Uploaded bundle checksum does not match.')
        old = current_version()
        if old and tuple(map(int, version.split('.'))) < tuple(map(int, old.split('.'))):
            raise ValueError('Publishing an older stable version is not permitted.')
        with tempfile.TemporaryDirectory(prefix='.publish-', dir=ROOT) as temporary:
            staging = Path(temporary)
            known = unpack_verified(bundle, staging, version)
            releases = ROOT / 'releases'
            if releases.is_symlink() or (releases.exists() and not releases.is_dir()):
                raise ValueError('Existing releases path is not a directory.')
            releases.mkdir(mode=0o755, exist_ok=True)
            target = releases / version
            source = staging / 'releases' / version
            source.chmod(0o755)
            expected_names = {Path(name).name for name in known if name.startswith('releases/')}
            if target.exists() or target.is_symlink():
                if (target.is_symlink() or not target.is_dir()
                        or {item.name for item in target.iterdir()} != expected_names):
                    raise ValueError('Existing version is immutable and differs from this publication.')
                for name in expected_names:
                    existing = target / name
                    info = known['releases/' + version + '/' + name]
                    if (existing.is_symlink() or not existing.is_file()
                            or (existing.stat().st_size, digest(existing)) != info):
                        raise ValueError('Existing version is immutable and differs from this publication.')
            else:
                os.rename(source, target)
            # Publish the discoverable feed only after every package is in place.
            os.replace(staging / 'index.html', ROOT / 'index.html')
            os.replace(staging / 'stable.manifest', ROOT / 'stable.manifest')
        return {'ok': True, 'action': 'publish', 'version': version, 'package_count': len(expected_names)}
    finally:
        try:
            bundle.unlink()
        except FileNotFoundError:
            pass

def main():
    action = sys.argv[1]
    if action == 'inspect':
        result = inspect_root()
    elif action == 'prepare':
        ensure_root(create=True)
        result = {'ok': True, 'action': 'prepare'}
    elif action == 'publish':
        result = publish(*sys.argv[2:])
    else:
        raise ValueError('Unknown publication action.')
    print(json.dumps(result))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not expose arbitrary environment values, server paths or tracebacks.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(json.dumps({'ok': False, 'error_type': type(error).__name__, 'error': message}))
        raise SystemExit(1)
'''


def validate_bundle_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        allowed = (parsed.scheme == "https" and parsed.hostname == BUNDLE_HOST and parsed.port in (None, 443)
                   and parsed.username is None and parsed.password is None and not parsed.fragment
                   and not re.search(r"[\s\x00-\x1f\x7f]", url))
    except ValueError:
        allowed = False
    if not allowed:
        raise ValueError("Bundle must use the approved HTTPS GitHub asset host.")


class AssetRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_bundle_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_bundle(url: str, checksum: str, destination: Path) -> None:
    validate_bundle_url(url)
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("A SHA-256 checksum is required.")
    opener = build_opener(AssetRedirect())
    request = Request(url, headers={"Accept-Encoding": "identity", "User-Agent": "RpaOrkestrAI-Publisher/1"})
    count, digest = 0, hashlib.sha256()
    deadline = time.monotonic() + 600
    with opener.open(request, timeout=30) as response, destination.open("xb") as handle:
        validate_bundle_url(response.geturl())
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise ValueError("Unexpected bundle download response.")
        size = response.headers.get("Content-Length")
        if size is not None and (not size.isdigit() or not 0 < int(size) <= MAX_BUNDLE):
            raise ValueError("Bundle exceeds download size limit.")
        read = getattr(response, "read1", response.read)
        while True:
            chunk = read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_BUNDLE or time.monotonic() > deadline:
                raise ValueError("Bundle download size or time limit exceeded.")
            digest.update(chunk)
            handle.write(chunk)
    if not count or digest.hexdigest() != checksum:
        raise ValueError("Downloaded bundle checksum does not match.")


def validate_local_bundle(bundle: Path, version: str) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    # Share the exact path/size/hash rules between the runner and remote Python.
    namespace = {"__name__": "publication_validation"}
    exec(compile(REMOTE_CODE, "publication_validation", "exec"), namespace)
    if not re.fullmatch(namespace["VERSION_PATTERN"], version):
        raise ValueError("Invalid publication version.")
    if bundle.is_symlink() or not bundle.is_file() or not 0 < bundle.stat().st_size <= MAX_BUNDLE:
        raise ValueError("Invalid publication bundle.")
    with tempfile.TemporaryDirectory(prefix="rpa-verify-") as temporary:
        staging = Path(temporary)
        namespace["unpack_verified"](bundle, staging, version)
        envelope = json.loads((staging / "stable.manifest").read_bytes())
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(UPDATE_PUBLIC_KEY, validate=True))
        try:
            key.verify(base64.b64decode(envelope["signature"], validate=True),
                       base64.b64decode(envelope["payload"], validate=True))
        except InvalidSignature as exc:
            raise ValueError("Bundle publisher signature did not verify.") from exc


def remote_failure_diagnostic(action: str, result: dict) -> None:
    allowed_types = {
        "AttributeError", "TypeError", "FileNotFoundError", "PermissionError", "FileExistsError",
        "ValueError", "OSError", "RuntimeError", "JSONDecodeError", "ReadError", "EOFError",
        "UnicodeDecodeError", "KeyError", "IndexError", "NotADirectoryError", "IsADirectoryError", "Error",
    }
    error_type = result.get("error_type")
    diagnostic = {
        "action": action if action in {"inspect", "prepare", "publish"} else "operation",
        "error_type": error_type if error_type in allowed_types else "RemoteError",
    }
    # Only literal messages from our trusted remote source may reach logs;
    # never forward arbitrary server strings, environment values or URLs.
    allowed_reasons = set(re.findall(r"raise ValueError\('([^']+)'\)", REMOTE_CODE))
    reason = result.get("error")
    if error_type == "ValueError" and isinstance(reason, str) and reason in allowed_reasons:
        diagnostic["reason"] = reason
    print("Scoped server failure: " + json.dumps(diagnostic), file=sys.stderr)


def remote(client, action: str, *arguments: str) -> dict:
    command = "python3 -c " + shlex.quote(REMOTE_CODE) + " " + " ".join(
        shlex.quote(value) for value in (action, *arguments)
    )
    stdin, stdout, stderr = client.exec_command(command, timeout=600)
    stdin.close()
    raw = stdout.read(65537)
    status = stdout.channel.recv_exit_status()
    stderr.close()
    stdout.close()
    if len(raw) > 65536:
        raise RuntimeError("Unexpected server response size.")
    result = json.loads(raw.decode("utf-8"))
    if status or not isinstance(result, dict) or result.get("ok") is not True:
        remote_failure_diagnostic(action, result if isinstance(result, dict) else {})
        raise RuntimeError("Scoped publication did not complete; inspect /rpa before retrying.")
    return result


def settings() -> dict[str, str]:
    # Avoid a workflow step env entry for the signed URL: Actions prints step env
    # values before the script starts. Read dispatch inputs directly instead.
    inputs = {}
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        inputs = json.loads(Path(event_path).read_text(encoding="utf-8")).get("inputs", {})
    return {name: os.environ.get("RPA_" + name.upper(), inputs.get(name, ""))
            for name in ("action", "version", "bundle_url", "bundle_sha256")}


def main() -> int:
    import paramiko

    logging.getLogger("paramiko").disabled = True
    config = settings()
    action = config["action"]
    if action not in {"inspect", "publish"}:
        raise ValueError("RPA_ACTION must be inspect or publish.")
    if action == "publish" and not re.fullmatch(r"\d+\.\d+\.\d+", config["version"]):
        raise ValueError("A stable publication version is required.")
    host, username, password = (os.environ[name] for name in ("HOST", "USERNAME", "PASSWORD"))
    client = paramiko.SSHClient()
    client.get_host_keys().add(host, "ssh-ed25519", paramiko.Ed25519Key(data=base64.b64decode(HOST_ED25519)))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(host, username=username, password=password, allow_agent=False, look_for_keys=False,
                       timeout=20, banner_timeout=20, auth_timeout=20)
        if action == "inspect":
            print(json.dumps(remote(client, "inspect")))
            return 0
        with tempfile.TemporaryDirectory(prefix="rpa-publish-") as folder:
            bundle = Path(folder) / "publish-bundle.tar.gz"
            download_bundle(config["bundle_url"], config["bundle_sha256"], bundle)
            validate_local_bundle(bundle, config["version"])
            remote(client, "prepare")
            token = uuid.uuid4().hex
            remote_path = REMOTE_ROOT + "/.upload-" + token + ".tar.gz"
            with client.open_sftp() as sftp:
                try:
                    with sftp.open(remote_path, "wx") as target, bundle.open("rb") as source:
                        sftp.chmod(remote_path, 0o600)
                        target.set_pipelined(True)
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            target.write(chunk)
                    result = remote(client, "publish", config["version"], config["bundle_sha256"], token)
                    print(json.dumps(result))
                finally:
                    try:
                        sftp.remove(remote_path)
                    except FileNotFoundError:
                        pass
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Network and SSH errors may contain signed URLs or connection details.
        print(f"Scoped publication failed ({type(error).__name__}). No credentials were logged.", file=sys.stderr)
        raise SystemExit(1)
