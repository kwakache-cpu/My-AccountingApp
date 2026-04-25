import re


_LONG_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]{24,}(?![A-Za-z0-9])")
_KEY_QUERY_PATTERN = re.compile(r"([?&])key=[^&\s]+", re.IGNORECASE)
_SECRET_QUERY_PATTERN = re.compile(r"([?&])(key|token|apikey|api_key|access_token|auth|authorization|signature)=[^&\s]+", re.IGNORECASE)
_AUTH_BEARER_PATTERN = re.compile(r"Authorization\s*:\s*Bearer\s+[^\s,;]+", re.IGNORECASE)
_AUTH_PATTERN = re.compile(r"Authorization\s*:\s*[^\s,;]+", re.IGNORECASE)
_BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)
_URL_CREDENTIAL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def sanitize_error_message(msg):
    """Remove secrets, bearer headers, and long tokens from user-visible error text."""
    if msg is None:
        return ""

    sanitized = str(msg)
    sanitized = _AUTH_BEARER_PATTERN.sub("Authorization: [redacted]", sanitized)
    sanitized = _AUTH_PATTERN.sub("Authorization: [redacted]", sanitized)
    sanitized = _BEARER_TOKEN_PATTERN.sub("Bearer [redacted]", sanitized)
    sanitized = _KEY_QUERY_PATTERN.sub(r"\1key=[redacted]", sanitized)
    sanitized = _SECRET_QUERY_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}=[redacted]", sanitized)
    sanitized = sanitized.replace("key=", "key=[redacted]")
    sanitized = _URL_CREDENTIAL_PATTERN.sub(_sanitize_url, sanitized)
    sanitized = _LONG_TOKEN_PATTERN.sub("[redacted]", sanitized)
    return sanitized


def build_user_safe_error(exc, role=None):
    generic_message = "An error occurred. Please contact the system administrator."
    sanitized = sanitize_error_message(exc)
    normalized_role = str(role or "").strip()
    if normalized_role in {"Dev", "Master Admin"} and sanitized:
        return f"{generic_message} Details: {sanitized}"
    return generic_message


def _sanitize_url(match):
    url = match.group(0)
    if (
        "key=" in url.lower()
        or "token=" in url.lower()
        or "apikey=" in url.lower()
        or "api_key=" in url.lower()
        or "access_token=" in url.lower()
        or "authorization=" in url.lower()
        or "signature=" in url.lower()
        or "bearer" in url.lower()
    ):
        url = _KEY_QUERY_PATTERN.sub(r"\1key=[redacted]", url)
        url = _SECRET_QUERY_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}=[redacted]", url)
        return url.split("?", 1)[0]
    return url
