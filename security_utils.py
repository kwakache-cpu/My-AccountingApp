import re


_LONG_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]{24,}(?![A-Za-z0-9])")
_KEY_QUERY_PATTERN = re.compile(r"([?&])key=[^&\s]+", re.IGNORECASE)
_AUTH_BEARER_PATTERN = re.compile(r"Authorization\s*:\s*Bearer\s+[^\s,;]+", re.IGNORECASE)
_AUTH_PATTERN = re.compile(r"Authorization\s*:\s*[^\s,;]+", re.IGNORECASE)
_URL_CREDENTIAL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def sanitize_error_message(msg):
    """Remove secrets, bearer headers, and long tokens from user-visible error text."""
    if msg is None:
        return ""

    sanitized = str(msg)
    sanitized = _AUTH_BEARER_PATTERN.sub("Authorization: [redacted]", sanitized)
    sanitized = _AUTH_PATTERN.sub("Authorization: [redacted]", sanitized)
    sanitized = _KEY_QUERY_PATTERN.sub(r"\1key=[redacted]", sanitized)
    sanitized = sanitized.replace("key=", "key=[redacted]")
    sanitized = _URL_CREDENTIAL_PATTERN.sub(_sanitize_url, sanitized)
    sanitized = _LONG_TOKEN_PATTERN.sub("[redacted]", sanitized)
    return sanitized


def _sanitize_url(match):
    url = match.group(0)
    if "key=" in url.lower() or "token=" in url.lower() or "bearer" in url.lower():
        url = _KEY_QUERY_PATTERN.sub(r"\1key=[redacted]", url)
        url = re.sub(r"([?&])token=[^&\s]+", r"\1token=[redacted]", url, flags=re.IGNORECASE)
        return url.split("?", 1)[0]
    return url
