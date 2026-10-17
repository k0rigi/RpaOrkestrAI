"""Ajanların internet araştırması: arama ve sayfa okuma, yalnız okuma ve yalnız açık internet.

Web content is untrusted data for the model. The page reader only GETs public addresses: every address,
and every redirect, must resolve to public IPs (no loopback, private, link-local or cloud metadata
networks), use http(s) on the default ports and stay inside the agent's allowed sites. Addresses that
contain a saved secret, or a long query string that could carry business data out, are refused.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from ..config import atomic_json
from ..errors import WorkflowError

PROVIDERS = {
    "none": "Kapalı",
    "tavily": "Tavily (ayda 1.000 ücretsiz arama, anahtar gerekir)",
    "brave": "Brave Search (aylık 5 $ kredi, anahtar gerekir)",
    "searxng": "SearXNG (kendi sunucunuz, ücretsiz)",
    "wikipedia": "Vikipedi (anahtarsız, yalnız ansiklopedik bilgi)",
    "model": "Model sağlayıcısının kendi araması (Gemini, OpenAI, Claude; ek anahtar gerekmez)",
}
MODEL_PROVIDERS = frozenset({"gemini", "openai", "anthropic"})
GROUNDING_REDIRECT = "vertexaisearch.cloud.google.com"
PAGE_LIMIT = 2 * 1024 * 1024
TEXT_LIMIT = 12_000
QUERY_STRING_LIMIT = 300
REQUESTS_PER_RUN = 20
DOMAIN = re.compile(r"^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
READABLE = ("text/html", "text/plain", "application/json", "application/xml", "text/xml", "application/xhtml+xml")


def normalize_domain(value: str) -> str:
    domain = value.strip().casefold().removeprefix("https://").removeprefix("http://").split("/")[0]
    domain = domain.removeprefix("www.") if not domain.startswith("*.") else domain
    if not DOMAIN.fullmatch(domain):
        raise ValueError(f"Site adı geçersiz: {value}. Ör. mevzuat.gov.tr veya *.gib.gov.tr")
    return domain


def allowed_host(host: str, domains: list[str]) -> bool:
    host = (host or "").casefold().rstrip(".")
    for domain in domains:
        base = domain.removeprefix("*.")
        if host == base or host.endswith("." + base):
            return True
    return False


def _public(host: str) -> str:
    """The address to connect to; the host is refused unless every address it resolves to is public."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        raise WorkflowError(f"{host} adresi çözümlenemedi.") from None
    addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    if not addresses or any(not address.is_global or address.is_multicast for address in addresses):
        raise WorkflowError("Ajan iç ağdaki veya bu bilgisayardaki adreslere erişemez; yalnız açık internet okunur.")
    return str(addresses[0])


def check_url(url: str, domains: list[str] | None, contains_secret=None) -> str:
    if not isinstance(url, str) or len(url) > 2000:
        raise WorkflowError("Adres en fazla 2000 karakter olmalıdır.")
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise WorkflowError("Yalnız http:// veya https:// ile başlayan web adresleri okunabilir.")
    if parts.username or parts.password:
        raise WorkflowError("Adreste kullanıcı adı veya şifre olamaz.")
    if parts.port not in (None, 80, 443):
        raise WorkflowError("Yalnız standart web portları (80, 443) kullanılabilir.")
    if len(parts.query) > QUERY_STRING_LIMIT:
        raise WorkflowError("Adresin ? sonrası bölümü çok uzun; ajan adresle veri gönderemez.")
    if contains_secret is not None and contains_secret(url):
        raise WorkflowError("Adres kayıtlı bir şifre veya anahtar içeriyor; istek gönderilmedi.")
    if domains is not None and not allowed_host(parts.hostname, domains):
        raise WorkflowError(f"{parts.hostname} bu ajanın izinli siteleri arasında değil.")
    _public(parts.hostname)
    return url.strip()


class _Redirects(HTTPRedirectHandler):
    max_redirections = 3

    def __init__(self, domains, contains_secret):
        super().__init__()
        self.domains, self.contains_secret = domains, contains_secret

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Every hop is checked again: a public page must not bounce the reader into the local network.
        check_url(newurl, self.domains, self.contains_secret)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _pinned_socket(address, timeout, source_address=None):
    # Connect to the address that was just checked: a second DNS answer cannot point the reader inward.
    host, port = address
    return socket.create_connection((_public(host), port), timeout, source_address)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _pinned_socket


class _PinnedHTTPS(http.client.HTTPSConnection):
    # The certificate is still verified against the host name (SNI), not the address.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _pinned_socket


class _PinnedHTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PinnedHTTP, req)


class _PinnedHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PinnedHTTPS, req, context=self._context)


def _opener(domains=None, contains_secret=None):
    import certifi

    return build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
                        _Redirects(domains, contains_secret))


def _page_opener(domains=None, contains_secret=None):
    import certifi

    # Pages are read directly: a proxy would resolve the name again, after the check.
    return build_opener(ProxyHandler({}), _PinnedHTTPHandler(),
                        _PinnedHTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
                        _Redirects(domains, contains_secret))


def _json(url: str, *, headers: dict | None = None, data: bytes | None = None, timeout: float = 20) -> dict:
    request = Request(url, data=data, method="POST" if data else "GET",
                      headers={"Accept": "application/json", "User-Agent": "RpaOrkestrAI", **(headers or {})})
    try:
        with _opener().open(request, timeout=timeout) as response:
            return json.loads(response.read(PAGE_LIMIT).decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise WorkflowError("Arama hizmeti anahtarı kabul etmedi; Ajanlar → Bağlantılar → Web araması'ndan "
                                "anahtarı kontrol edin.") from None
        if exc.code == 429:
            raise WorkflowError("Arama hizmetinin kotası veya istek sınırı doldu.") from None
        raise WorkflowError(f"Arama hizmeti {exc.code} hatası döndürdü.") from None
    except (URLError, OSError, ValueError) as exc:
        raise WorkflowError(f"Arama hizmetine ulaşılamadı: {getattr(exc, 'reason', exc)}") from None


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def search(config: dict, key: str | None, query: str, max_results: int = 5,
           domains: list[str] | None = None) -> list[dict]:
    provider = config.get("provider", "none")
    query = query.strip()
    if domains:
        # Narrow the search itself to the allowed sites; results are filtered again below.
        query = f"{query} ({' OR '.join('site:' + domain.removeprefix('*.') for domain in domains[:8])})"
    if provider == "tavily":
        body = {"query": query[:400], "max_results": max_results, "search_depth": "basic"}
        if domains:
            body["include_domains"] = [domain.removeprefix("*.") for domain in domains]
        data = _json("https://api.tavily.com/search", headers={"Authorization": f"Bearer {key}",
                                                                "Content-Type": "application/json"},
                     data=json.dumps(body).encode())
        items = [{"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("content", "")}
                 for item in data.get("results", [])]
    elif provider == "brave":
        data = _json("https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query[:400], "count": max_results}),
                     headers={"X-Subscription-Token": key or ""})
        items = [{"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("description", "")}
                 for item in data.get("web", {}).get("results", [])]
    elif provider == "searxng":
        base = (config.get("searxng_url") or "").rstrip("/")
        if not base:
            raise WorkflowError("SearXNG sunucusunun adresi girilmemiş.")
        data = _json(f"{base}/search?" + urlencode({"q": query[:400], "format": "json"}))
        items = [{"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("content", "")}
                 for item in data.get("results", [])]
    elif provider == "wikipedia":
        language = config.get("language") or "tr"
        data = _json(f"https://{language}.wikipedia.org/w/api.php?" + urlencode({
            "action": "query", "list": "search", "srsearch": query.split(" (site:")[0][:300], "format": "json",
            "srlimit": max_results}))
        items = [{"title": item.get("title", ""), "snippet": item.get("snippet", ""),
                  "url": f"https://{language}.wikipedia.org/wiki/{quote(str(item.get('title', '')).replace(' ', '_'))}"}
                 for item in data.get("query", {}).get("search", [])]
    elif provider == "model":
        raise WorkflowError("Model araması ajanın kendi model bağlantısıyla yapılır.")
    else:
        raise WorkflowError("Web araması kapalı. Ajanlar → Bağlantılar → Web araması bölümünden bir hizmet seçin.")
    return clean_results(items, domains, max_results)


class _NoFollow(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_redirect(url: str, timeout: float = 8) -> str:
    """Gemini's source links are Google redirects; the real address is read without opening the page."""
    import certifi

    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != GROUNDING_REDIRECT:
        return url
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
                          _NoFollow())
    try:
        opener.open(Request(url, method="GET", headers={"User-Agent": "RpaOrkestrAI"}), timeout=timeout).close()
    except HTTPError as exc:
        location = exc.headers.get("Location", "") if exc.headers else ""
        exc.close()
        if location.startswith(("https://", "http://")) and len(location) <= 2000:
            return location
    except (URLError, OSError, ValueError):
        pass
    return url


def clean_results(items, domains: list[str] | None, max_results: int) -> list[dict]:
    results = []
    for item in items:
        url = str(item.get("url") or "")
        if not url.startswith(("https://", "http://")):
            continue
        if domains is not None and not allowed_host(urlsplit(url).hostname or "", domains):
            continue
        results.append({"title": _strip(item.get("title"))[:300], "url": url[:2000], "snippet": _strip(item.get("snippet"))[:600]})
        if len(results) >= max_results:
            break
    return results


def fetch(url: str, domains: list[str] | None = None, contains_secret=None, timeout: float = 20) -> dict:
    from ..integrations.imap import html_text

    url = check_url(url, domains, contains_secret)
    request = Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 (RpaOrkestrAI ajan okuyucu)",
                                                   "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1"})
    try:
        with _page_opener(domains, contains_secret).open(request, timeout=timeout) as response:
            final = response.geturl()
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().casefold()
            if content_type and not content_type.startswith(READABLE):
                raise WorkflowError(f"Bu tür içerik okunamaz ({content_type}); yalnız web sayfası ve metin okunur.")
            raw = response.read(PAGE_LIMIT + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except WorkflowError:
        raise
    except HTTPError as exc:
        raise WorkflowError(f"Sayfa okunamadı: site {exc.code} döndürdü.") from None
    except (URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, WorkflowError):
            raise reason from None
        raise WorkflowError(f"Sayfaya ulaşılamadı: {reason}") from None
    content = raw[:PAGE_LIMIT].decode(charset, errors="replace")
    title = ""
    if "html" in content_type or content.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        title = _strip(match.group(1))[:300] if match else ""
        content = html_text(content)
    return {"url": final, "title": title, "text": content[:TEXT_LIMIT], "truncated": len(content) > TEXT_LIMIT}


class SearchSettings:
    """The workspace's search service per company; the key lives in the system's secret store."""

    def __init__(self, data_dir: Path, *, vault=None):
        from ..vault import Vault

        self.path = Path(data_dir) / "agent_search.json"
        self.vault = vault if vault is not None else Vault(Path(data_dir), purpose="agent_search")
        self._lock = threading.RLock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _name(company_id: int) -> str:
        return f"company_{int(company_id)}"

    def get(self, company_id: int) -> dict:
        with self._lock:
            config = self._read().get(str(company_id)) or {}
        provider = config.get("provider") if config.get("provider") in PROVIDERS else "none"
        return {"provider": provider, "provider_label": PROVIDERS[provider], "searxng_url": config.get("searxng_url", ""),
                "language": config.get("language", "tr"), "has_key": self.vault.has(self._name(company_id))}

    def key(self, company_id: int) -> str | None:
        return self.vault.get(self._name(company_id))

    def save(self, company_id: int, body: dict) -> dict:
        provider = body.get("provider", "none")
        if provider not in PROVIDERS:
            raise ValueError("Arama hizmeti geçersiz.")
        url = str(body.get("searxng_url") or "").strip().rstrip("/")
        if provider == "searxng" and urlsplit(url).scheme not in {"http", "https"}:
            raise ValueError("SearXNG sunucusunun tam adresini yazın (ör. https://arama.firma.com).")
        language = str(body.get("language") or "tr").strip().casefold()
        if not re.fullmatch(r"[a-z]{2,3}", language):
            raise ValueError("Dil kodu iki harf olmalıdır (ör. tr, en).")
        key = body.get("key")
        if key is not None:
            if not isinstance(key, str) or len(key) > 500 or any(ord(char) < 32 for char in key):
                raise ValueError("Anahtar geçersiz.")
        with self._lock:
            data = self._read()
            data[str(company_id)] = {"provider": provider, "searxng_url": url, "language": language}
            atomic_json(self.path, data)
            if key:
                self.vault.set(self._name(company_id), key.strip())
            elif body.get("remove_key"):
                self.vault.delete(self._name(company_id))
        return self.get(company_id)

    def secrets(self) -> list[str]:
        with self._lock:
            names = [self._name(int(company)) for company in self._read() if str(company).isdigit()]
        return [value for value in (self.vault.get(name) for name in names) if value]
