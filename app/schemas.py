"""
Pydantic veri doğrulama şemaları.

API istek/yanıt gövdelerinin doğrulanması ve serileştirilmesi bu modülde yapılır.
ORM modelleri ile API katmanı arasında ayrım sağlar (DTO pattern).
"""

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import BreakStatus, BreakType, UserRole


# ---------------------------------------------------------------------------
# Kimlik Doğrulama Şemaları
# ---------------------------------------------------------------------------


class UserRegister(BaseModel):
    """Kayıt olma isteği — sadece kullanıcı adı ve şifre."""

    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Kullanıcı adı",
    )
    password: str = Field(
        ...,
        min_length=4,
        max_length=100,
        description="Şifre",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower() == "eren":
            raise ValueError("Bu kullanıcı adı rezerve edilmiştir ve kayıt olunamaz.")
        return cleaned


class UserLogin(BaseModel):
    """Giriş isteği."""

    username: str = Field(..., description="Sicil numarası")
    password: str = Field(..., min_length=4)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().upper()


class AuthResponse(BaseModel):
    """Başarılı giriş/kayıt yanıtı."""

    id: int
    full_name: str
    employee_code: str
    role: UserRole
    is_super_admin: bool = False
    message: str = "İşlem başarılı"

    @model_validator(mode="after")
    def set_super_admin(self) -> "AuthResponse":
        """Sadece sabit admin hesabı süper yönetici olarak işaretlenir."""
        self.is_super_admin = self.employee_code.upper() == "EREN"
        return self


class UserManageItem(BaseModel):
    """Kullanıcı yönetimi listesi öğesi."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: UserRole
    is_active: bool


# ---------------------------------------------------------------------------
# Çalışan (Employee) Şemaları
# ---------------------------------------------------------------------------


class EmployeeBase(BaseModel):
    """Çalışan oluşturma ve güncelleme için ortak alanlar."""

    employee_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Benzersiz sicil numarası",
        examples=["EMP001"],
    )
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Çalışanın adı soyadı",
        examples=["Ahmet Yılmaz"],
    )
    department: str | None = Field(
        default=None,
        max_length=100,
        description="Departman adı",
        examples=["Üretim"],
    )

    @field_validator("employee_code")
    @classmethod
    def normalize_employee_code(cls, value: str) -> str:
        """Sicil numarasını büyük harfe çevirerek normalize eder."""
        return value.strip().upper()


class EmployeeCreate(EmployeeBase):
    """Yönetici tarafından yeni personel oluşturma."""

    password: str = Field(default="123456", min_length=4, max_length=100)


class EmployeeUpdate(BaseModel):
    """Çalışan güncelleme isteği (tüm alanlar opsiyonel)."""

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    department: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class EmployeeResponse(EmployeeBase):
    """Çalışan API yanıt şeması."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    is_active: bool
    is_on_break: bool = False
    created_at: datetime


class EmployeeStatusUpdate(BaseModel):
    """PATCH /employees/{id}/status — mola durumu güncelleme."""

    is_on_break: bool
    break_duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=480,
        description="Mola süresi (dakika); başlatırken zorunlu",
    )
    assigned_by: str | None = Field(
        default=None,
        max_length=150,
        description="Molayı atayan yönetici adı",
    )

    @model_validator(mode="after")
    def validate_start_fields(self) -> "EmployeeStatusUpdate":
        if self.is_on_break and not self.break_duration_minutes:
            raise ValueError("Mola başlatırken break_duration_minutes zorunludur.")
        return self


class EmployeeStatusResponse(BaseModel):
    """Personel durum sorgulama yanıtı (polling)."""

    id: int
    full_name: str
    employee_code: str
    role: UserRole
    department: str | None
    is_on_break: bool
    break_start_time: datetime | None
    break_duration_minutes: int | None
    remaining_seconds: int = 0
    remaining_minutes: float = 0
    is_expired: bool = False
    assigned_by: str | None = None

    @model_validator(mode="after")
    def compute_remaining(self) -> "EmployeeStatusResponse":
        """Kalan süreyi hesaplar; süre dolduysa is_expired=True yapar."""
        if not self.is_on_break or not self.break_start_time or not self.break_duration_minutes:
            self.remaining_seconds = 0
            self.remaining_minutes = 0
            self.is_expired = False
            return self

        now = datetime.now(timezone.utc)
        start = self.break_start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        elapsed = (now - start).total_seconds()
        total = self.break_duration_minutes * 60
        remaining = max(0, int(total - elapsed))
        self.remaining_seconds = remaining
        self.remaining_minutes = round(remaining / 60, 1)
        self.is_expired = remaining <= 0
        return self


class ActiveBreakSummary(BaseModel):
    """Aktif mola özeti — geri sayım için kullanılır."""

    break_id: int
    start_time: datetime
    planned_duration_minutes: int
    remaining_seconds: int = Field(description="Kalan süre (saniye)")

    @model_validator(mode="after")
    def compute_remaining(self) -> "ActiveBreakSummary":
        """Sunucu tarafında kalan süreyi hesaplar."""
        now = datetime.now(timezone.utc)
        start = self.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        elapsed = (now - start).total_seconds()
        total = self.planned_duration_minutes * 60
        self.remaining_seconds = max(0, int(total - elapsed))
        return self


class EmployeeOverview(EmployeeResponse):
    """Panel listesi için çalışan + anlık durum bilgisi."""

    work_status: Literal["calisiyor", "molada"] = Field(
        description="Anlık çalışma durumu"
    )
    active_break: ActiveBreakSummary | None = None
    assigned_by: str | None = None
    kullanilan_mola: int = Field(0, description="Bugün kullanılan mola sayısı")
    mola_hakki_limit: int = Field(2, description="Günlük mola hakkı limiti")
    bugunku_toplam_mola_dk: float = Field(0, description="Bugünkü toplam mola süresi (dk)")
    mola_hakki_bitti: bool = Field(False, description="Günlük mola hakkı doldu mu")
    can_start_break: bool = Field(True, description="Yeni mola başlatılabilir mi")


# ---------------------------------------------------------------------------
# Mola (Break) Şemaları
# ---------------------------------------------------------------------------


class BreakStart(BaseModel):
    """Mola başlatma isteği."""

    break_type: BreakType = Field(
        default=BreakType.SHORT,
        description="Mola türü",
    )
    planned_duration_minutes: int = Field(
        default=15,
        ge=1,
        le=480,
        description="Planlanan mola süresi (dakika)",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Opsiyonel not",
    )


class BreakEnd(BaseModel):
    """Mola bitirme isteği."""

    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Mola bitiş notu",
    )


class BreakResponse(BaseModel):
    """Mola API yanıt şeması."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    break_type: BreakType
    status: BreakStatus
    start_time: datetime
    end_time: datetime | None
    planned_duration_minutes: int
    notes: str | None
    duration_minutes: float | None = Field(
        default=None,
        description="Mola süresi (dakika); aktif molalarda None döner",
    )

    @model_validator(mode="after")
    def compute_fields(self) -> "BreakResponse":
        """Süre ve aktif mola alanlarını hesaplar."""
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            self.duration_minutes = round(delta.total_seconds() / 60, 2)
        elif self.status == BreakStatus.ACTIVE and self.duration_minutes is None:
            self.duration_minutes = float(self.planned_duration_minutes)
        return self


class BreakWithEmployee(BreakResponse):
    """Çalışan bilgisiyle birlikte mola yanıtı."""

    employee: EmployeeResponse


# ---------------------------------------------------------------------------
# Genel Yanıt Şemaları
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    """Basit mesaj yanıtı (silme, onay vb. işlemler için)."""

    message: str
    detail: str | None = None


class HealthResponse(BaseModel):
    """Sağlık kontrolü yanıtı."""

    status: str = "ok"
    service: str = "mola-yonetim-sistemi"


# ---------------------------------------------------------------------------
# Dashboard & Geçmiş Raporlama
# ---------------------------------------------------------------------------


class DashboardSummary(BaseModel):
    """Yönetici paneli günün özeti kartları."""

    toplam_aktif_personel: int = Field(description="Aktif personel sayısı")
    su_an_molada: int = Field(description="Şu an molada olan personel sayısı")
    mola_hakki_biten: int = Field(description="Günlük mola hakkı biten personel sayısı")


class DashboardStatistics(BaseModel):
    """Yönetici paneli detaylı istatistikleri."""

    toplam_aktif_personel: int = Field(description="Aktif personel sayısı")
    su_an_molada: int = Field(description="Şu an molada olan personel sayısı")
    son_24_saat_toplam_mola_dk: int = Field(description="Son 24 saatteki toplam mola süresi (dakika)")
    personel_bazli_istatistikler: list[dict] = Field(description="Personel bazlı mola istatistikleri")


class BreakHistoryItem(BaseModel):
    """Geçmiş mola kaydı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    start_time: datetime
    end_time: datetime
    duration: float
    date: date


class BreakHistoryResponse(BaseModel):
    """Personel geçmiş mola listesi."""

    employee_id: int
    full_name: str
    username: str
    period: str
    total_records: int
    total_duration_minutes: float


# ---------------------------------------------------------------------------
# Departman Şemaları
# ---------------------------------------------------------------------------


class DepartmentCreate(BaseModel):
    """Departman oluşturma isteği."""

    name: str = Field(..., min_length=1, max_length=100, description="Departman adı")
    description: str | None = Field(None, max_length=255, description="Departman açıklaması")


class DepartmentResponse(BaseModel):
    """Departman yanıtı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Vardiya Programı Şemaları
# ---------------------------------------------------------------------------


class ShiftScheduleCreate(BaseModel):
    """Vardiya programı oluşturma isteği."""

    employee_id: int = Field(..., description="Personel ID")
    day: str = Field(..., description="Gün (Pazartesi-Pazar)")
    shift_time: str = Field(..., description="Vardiya saati (örn: 07:30)")


class ShiftScheduleResponse(BaseModel):
    """Vardiya programı yanıtı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    day: str
    shift_time: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Günlük Aktif Personel Listesi Şemaları
# ---------------------------------------------------------------------------


class DailyActiveEmployeeCreate(BaseModel):
    """Günlük aktif personel ekleme isteği."""

    employee_id: int = Field(..., description="Personel ID")
    date: datetime.date = Field(..., description="Tarih")


class DailyActiveEmployeeResponse(BaseModel):
    """Günlük aktif personel yanıtı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    date: date
    added_by: str | None
    created_at: datetime
