"""
Özel istisna sınıfları.

API katmanında tutarlı hata yönetimi için domain-spesifik exception'lar tanımlanır.
Her sınıf HTTP status kodu ve kullanıcıya gösterilecek mesaj içerir.
"""

from fastapi import HTTPException, status


class MolaSistemiException(HTTPException):
    """Tüm uygulama istisnalarının temel sınıfı."""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(status_code=status_code, detail=detail)


class EmployeeNotFound(MolaSistemiException):
    """İstenen çalışan veritabanında bulunamadığında fırlatılır."""

    def __init__(self, employee_id: int | None = None, employee_code: str | None = None) -> None:
        if employee_code:
            detail = f"Çalışan bulunamadı: sicil no '{employee_code}'"
        elif employee_id is not None:
            detail = f"Çalışan bulunamadı: id={employee_id}"
        else:
            detail = "Çalışan bulunamadı"
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class EmployeeAlreadyExists(MolaSistemiException):
    """Aynı sicil numarasına sahip çalışan zaten kayıtlıysa fırlatılır."""

    def __init__(self, employee_code: str) -> None:
        super().__init__(
            detail=f"Bu sicil numarası zaten kayıtlı: '{employee_code}'",
            status_code=status.HTTP_409_CONFLICT,
        )


class ActiveBreakExists(MolaSistemiException):
    """Çalışanın zaten aktif bir molası varken yeni mola başlatılmaya çalışıldığında fırlatılır."""

    def __init__(self, employee_id: int) -> None:
        super().__init__(
            detail=f"Çalışanın (id={employee_id}) zaten aktif bir molası bulunmaktadır.",
            status_code=status.HTTP_409_CONFLICT,
        )


class NoActiveBreak(MolaSistemiException):
    """Aktif mola yokken mola bitirme işlemi yapılmaya çalışıldığında fırlatılır."""

    def __init__(self, employee_id: int) -> None:
        super().__init__(
            detail=f"Çalışanın (id={employee_id}) aktif bir molası bulunmamaktadır.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidCredentials(MolaSistemiException):
    """Giriş bilgileri hatalı olduğunda fırlatılır."""

    def __init__(self) -> None:
        super().__init__(
            detail="Kullanıcı adı veya şifre hatalı.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ReservedUsername(MolaSistemiException):
    """Rezerve edilmiş kullanıcı adı kayıt edilmeye çalışıldığında fırlatılır."""

    def __init__(self) -> None:
        super().__init__(
            detail="Bu kullanıcı adı rezerve edilmiştir ve kayıt olunamaz.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class UnauthorizedAction(MolaSistemiException):
    """Yetkisiz işlem denemesinde fırlatılır."""

    def __init__(self, detail: str = "Bu işlem için yetkiniz bulunmamaktadır.") -> None:
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class BreakQuotaExceeded(MolaSistemiException):
    """Günlük mola hakkı dolduğunda fırlatılır."""

    def __init__(self, employee_id: int, limit: int = 2) -> None:
        super().__init__(
            detail=f"Günlük mola hakkı ({limit}/{limit}) dolmuştur.",
            status_code=status.HTTP_409_CONFLICT,
        )


class BreakNotFound(MolaSistemiException):
    """İstenen mola kaydı bulunamadığında fırlatılır."""

    def __init__(self, break_id: int) -> None:
        super().__init__(
            detail=f"Mola kaydı bulunamadı: id={break_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
