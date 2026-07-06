"""
Netlify Serverless Handler — FastAPI + Mangum

Netlify Functions, AWS Lambda üzerinde çalışır.
Mangum, ASGI (FastAPI) uygulamasını Lambda olay modeline uyarlar.

Handler: /.netlify/functions/api
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# app/ paketinin import edilebilmesi için proje kökünü path'e ekle
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Serverless ortam değişkenleri (Netlify UI'dan da override edilebilir)
os.environ.setdefault("SERVE_FRONTEND", "false")
os.environ.setdefault("NETLIFY", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/mola_sistemi.db")

from mangum import Mangum

from app.database import init_db
from app.main import app

# Mangum lifespan="off" kullandığı için DB'yi burada başlatıyoruz
init_db()

# Lambda/Netlify handler — tüm API istekleri bu fonksiyona yönlendirilir
handler = Mangum(app, lifespan="off")
