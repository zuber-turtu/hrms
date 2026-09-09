import urllib.parse
from fastapi import Request


def get_safe_redirect(request: Request, default: str = "/dashboard") -> str:
    """
    Validates the Referer header to prevent Open Redirect vulnerabilities.
    Only allows local relative URLs or redirects matching the current application Host.
    """
    referer = request.headers.get("referer")
    if not referer:
        return default

    try:
        parsed = urllib.parse.urlparse(referer)
        host = request.headers.get("host")

        # Reject external domains
        if parsed.netloc and host and parsed.netloc.lower() != host.lower():
            return default

        # Reject non-http/https schemes
        if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
            return default

        path = parsed.path or "/"
        # Prevent protocol-relative URL bypasses like '//attacker.com' or '/\\attacker.com'
        if not path.startswith("/") or path.startswith("//") or path.startswith("/\\"):
            return default

        query_str = f"?{parsed.query}" if parsed.query else ""
        return f"{path}{query_str}"
    except Exception:
        return default


def append_query_param(url: str, param_name: str, param_value: str) -> str:
    """
    Appends or updates a query parameter in a given URL/path safely.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        query_dict = dict(urllib.parse.parse_qsl(parsed.query))
        query_dict[param_name] = param_value
        new_query = urllib.parse.urlencode(query_dict)
        return urllib.parse.urlunparse(
            ("", "", parsed.path, parsed.params, new_query, parsed.fragment)
        )
    except Exception:
        return url
