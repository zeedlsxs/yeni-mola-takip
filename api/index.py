"""
Vercel Serverless Function Entry Point
FastAPI uygulamasını Vercel'de çalıştırır
"""

from app.main import app

# Vercel serverless handler
handler = app
