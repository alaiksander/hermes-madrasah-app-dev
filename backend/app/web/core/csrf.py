"""CSRF protection untuk web forms.

Strategi berlapis:
1. `samesite=lax` cookie (sudah di auth.py) — blok cross-site POST
   dari luar (browser tidak kirim cookie pada cross-site POST).
2. Middleware Origin/Referer check — blok request POST cross-origin
   yang mencoba memanfaatkan cookie (defense-in-depth, tanpa perlu
   ubah template/views).

Catatan: token-based CSRF (hidden field) sengaja TIDAK dipakai —
overhead tinggi (30+ endpoint, 15+ template) dan samesite=lax sudah
memblokir vektor utama. Middleware ini menutup sisa celah.
"""
from fastapi import Request, Response


def is_same_origin(request: Request) -> bool:
    """Cek apakah request berasal dari origin yang sama (host kita).

    Bandingkan Origin/Referer header dengan host request.
    - Origin header: dikirim browser pada fetch/XHR POST + form POST
    - Referer header: fallback untuk beberapa browser/konfigurasi
    Return True kalau sama-origin atau header tidak ada (non-browser).
    """
    host = request.headers.get("host", "")
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")

    # Ambil host dari origin/referer kalau ada (format: https://host)
    def _host_from_url(url: str) -> str:
        url = url.strip()
        if url.startswith(("http://", "https://")):
            return url.split("/")[2].split(":")[0]
        return ""

    if origin:
        origin_host = _host_from_url(origin)
        if origin_host and origin_host != host.split(":")[0]:
            return False
    elif referer:
        referer_host = _host_from_url(referer)
        if referer_host and referer_host != host.split(":")[0]:
            return False
    # Tidak ada Origin/Referer = non-browser (curl, API internal) → izinkan
    return True


async def csrf_middleware(request: Request, call_next):
    """ASGI middleware: blok POST cross-origin ke /madrasah-app/*.

    Dipasang di main.py via `app.middleware("http")`.
    """
    path = request.url.path
    if request.method == "POST" and path.startswith("/madrasah-app"):
        if not is_same_origin(request):
            from fastapi.responses import RedirectResponse
            return RedirectResponse(
                "/madrasah-app/login?msg=Sesi+kedaluwarsa,+silakan+masuk+lagi&type=error",
                status_code=303,
            )
    return await call_next(request)