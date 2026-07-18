"""
Netlify build — config.js ve _redirects üretir (proje kökü).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REDIRECTS = """\
# Netlify _redirects — API proxy + sayfa yönlendirmeleri

# --- API → Mangum handler ---
/health              /.netlify/functions/api    200
/auth/*              /.netlify/functions/api    200
/employees/*         /.netlify/functions/api    200
/users/*             /.netlify/functions/api    200
/breaks/*            /.netlify/functions/api    200
/dashboard/summary   /.netlify/functions/api    200
/upload-shift        /.netlify/functions/api    200

# --- Uzantısız sayfa URL'leri ---
/dashboard           /dashboard.html            200
/employee            /employee.html             200

# --- SPA / sayfa yenileme fallback (en sonda) ---
/*                   /index.html                200
"""


def main() -> None:
    (ROOT / "config.js").write_text(
        'window.MOLA_API_BASE = "";\n',
        encoding="utf-8",
    )
    (ROOT / "_redirects").write_text(REDIRECTS, encoding="utf-8")
    print("Netlify build: config.js + _redirects hazır (kök dizin)")


if __name__ == "__main__":
    main()
