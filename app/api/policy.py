"""Explicit public API allowlist, reviewed when a public operation is added."""

PUBLIC_OPERATIONS = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/csrf"),
    ("GET", "/api/v1/public/plots"),
    ("GET", "/api/v1/public/plots/{plot_id}"),
    ("GET", "/api/v1/public/map/plots"),
    ("GET", "/api/v1/map/layers"),
    ("POST", "/api/v1/chat/messages"),
}
