"""
API hata mesajlarını Türkçe'ye çevirir.
"""

# Pydantic alan adı → Türkçe etiket
FIELD_LABELS: dict[str, str] = {
    "username": "Kullanıcı adı",
    "password": "Şifre",
    "full_name": "Ad soyad",
    "employee_code": "Sicil no",
    "break_duration_minutes": "Mola süresi",
}

# Hata türü → Türkçe mesaj şablonu
ERROR_MESSAGES: dict[str, str] = {
    "missing": "{field} zorunludur.",
    "string_too_short": "{field} en az {min} karakter olmalıdır.",
    "string_too_long": "{field} en fazla {max} karakter olabilir.",
    "greater_than_equal": "{field} en az {min} olmalıdır.",
    "less_than_equal": "{field} en fazla {max} olabilir.",
    "value_error": "{msg}",
}


def translate_validation_error(error: dict) -> str:
    """Tek bir Pydantic doğrulama hatasını Türkçe mesaja çevirir."""
    loc = error.get("loc", ())
    field = str(loc[-1]) if loc else "alan"
    label = FIELD_LABELS.get(field, field.replace("_", " ").capitalize())

    err_type = error.get("type", "")
    ctx = error.get("ctx", {})

    if err_type == "string_too_short":
        min_len = ctx.get("min_length", 4)
        if field == "password":
            return "Şifre en az 4 karakter olmalıdır."
        return f"{label} en az {min_len} karakter olmalıdır."

    if err_type == "string_too_long":
        max_len = ctx.get("max_length", 100)
        return f"{label} en fazla {max_len} karakter olabilir."

    if err_type == "missing":
        return f"{label} zorunludur."

    if err_type == "value_error":
        msg = error.get("msg", "Geçersiz değer.")
        if "rezerve" in msg.lower():
            return "Bu kullanıcı adı rezerve edilmiştir ve kayıt olunamaz."
        if "break_duration_minutes" in msg:
            return "Mola başlatırken süre belirtmelisiniz."
        return msg

    # Varsayılan
    return error.get("msg", "Geçersiz istek. Lütfen bilgilerinizi kontrol edin.")


def translate_validation_errors(errors: list) -> str:
    """Birden fazla doğrulama hatasını tek Türkçe mesaja dönüştürür."""
    if not errors:
        return "Geçersiz istek."
    messages = [translate_validation_error(e) for e in errors]
    return messages[0] if len(messages) == 1 else " · ".join(messages)
