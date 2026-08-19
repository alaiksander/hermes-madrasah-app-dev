"""Cookie helpers untuk web admin panel.

Token JWT disimpan di cookie HTTP-only dengan path spesifik
supaya hanya dikirim untuk endpoint web (bukan Flutter API).
"""
from fastapi import Request
from fastapi.responses import Response


_COOKIE_NAME = "madrasah_app_token"
_COOKIE_PATH = "/madrasah-app"


def set_token_cookie(response: Response, token: str, max_age_seconds: int,
                     secure: bool | None = None) -> None:
    """Set JWT di cookie HTTP-only.

    `secure`: default None → otomatis ikut skema request (True kalau HTTPS).
    Jangan hardcode True — di HTTP (akses IP tanpa SSL) cookie Secure tidak
    pernah dikirim browser → login gagal (kejadian 2026-08-17).
    """
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure if secure is not None else False,
        samesite="lax",
        max_age=max_age_seconds,
        path=_COOKIE_PATH,
    )


def clear_token_cookie(response: Response) -> None:
    """Hapus cookie auth."""
    response.delete_cookie(key=_COOKIE_NAME, path=_COOKIE_PATH)


def get_token_from_request(request: Request) -> str | None:
    """Ambil token dari cookie. Return None kalau tidak ada."""
    return request.cookies.get(_COOKIE_NAME)