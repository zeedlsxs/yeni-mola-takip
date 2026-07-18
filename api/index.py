"""
Vercel Serverless Function Entry Point
FastAPI uygulamasını Vercel'de çalıştırır
"""

import sys
from pathlib import Path

# Proje kök dizinini Python path'ine ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

# Vercel serverless handler
handler = app
