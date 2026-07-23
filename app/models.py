"""
SQLAlchemy ORM veri modelleri (veritabanı şemaları).

Bu modüller veritabanı tablolarının yapısını ve ilişkilerini tanımlar.
API katmanı bu modelleri doğrudan dışarıya açmaz; Pydantic şemaları kullanılır.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BreakStatus(str, enum.Enum):
    """Mola durumu enum'u."""

    ACTIVE = "active"        # Mola devam ediyor
    COMPLETED = "completed"  # Mola tamamlandı


class BreakType(str, enum.Enum):
    """Mola türü enum'u."""

    SHORT = "short"    # Kısa mola (ör. 15 dk)
    LUNCH = "lunch"    # Yemek molası
    OTHER = "other"    # Diğer


class UserRole(str, enum.Enum):
    """Kullanıcı rolü enum'u."""

    YONETICI = "yonetici"
    PERSONEL = "personel"


class Employee(Base):
    """
    Çalışan tablosu.

    Her çalışan benzersiz bir sicil numarası (employee_code) ile tanımlanır.
    """

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        default=UserRole.PERSONEL,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # Anlık mola durumu — personel polling ile bu alanları okur
    is_on_break: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    break_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    break_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_by: Mapped[str | None] = mapped_column(
        String(150), nullable=True, comment="Molayı atayan yönetici adı"
    )
    # Günlük mola hakkı takibi
    kullanilan_mola: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Bugün kullanılan mola sayısı"
    )
    mola_kota_tarihi: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Mola kotasının geçerli olduğu gün"
    )
    vardiya_saati: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="Vardiya başlama saati (örn: 07:30)"
    )
    vardiya_gunu: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Vardiya günü (Pazartesi-Pazar)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # İlişki: bir çalışanın birden fazla mola kaydı olabilir
    breaks: Mapped[list["Break"]] = relationship(
        "Break",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    # İlişki: bir çalışan bir departmana ait olabilir
    department_obj: Mapped["Department"] = relationship(
        "Department",
        back_populates="employees",
    )

    def __repr__(self) -> str:
        return f"<Employee(id={self.id}, code='{self.employee_code}', name='{self.full_name}')>"


class Break(Base):
    """
    Mola kayıt tablosu.

    Her mola bir çalışana bağlıdır; başlangıç ve bitiş zamanları ile
    süre hesaplaması yapılabilir.
    """

    __tablename__ = "breaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    break_type: Mapped[BreakType] = mapped_column(
        Enum(BreakType),
        default=BreakType.SHORT,
        nullable=False,
    )
    status: Mapped[BreakStatus] = mapped_column(
        Enum(BreakStatus),
        default=BreakStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15,
        comment="Planlanan mola süresi (dakika): 15, 30 veya 60",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # İlişki: her mola bir çalışana aittir
    employee: Mapped["Employee"] = relationship("Employee", back_populates="breaks")

    def __repr__(self) -> str:
        return (
            f"<Break(id={self.id}, employee_id={self.employee_id}, "
            f"status='{self.status.value}')>"
        )


class BreakHistory(Base):
    """
    Tamamlanan mola geçmişi tablosu.

    Her mola bittiğinde otomatik olarak bu tabloya kayıt yazılır.
    Raporlama ve geçmiş analiz için kullanılır.
    """

    __tablename__ = "breaks_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Personel kullanıcı adı (sicil)",
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Mola süresi (dakika)",
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    employee: Mapped["Employee"] = relationship("Employee")

    def __repr__(self) -> str:
        return (
            f"<BreakHistory(id={self.id}, username='{self.username}', "
            f"date={self.date})>"
        )


class Department(Base):
    """
    Departman tablosu.

    Vardiya programındaki departmanları tanımlar.
    """

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    employees: Mapped[list["Employee"]] = relationship(
        "Employee",
        back_populates="department_obj",
    )

    def __repr__(self) -> str:
        return f"<Department(id={self.id}, name='{self.name}')>"


class ShiftSchedule(Base):
    """
    Vardiya programı tablosu.

    Her personelin hangi gün ve saatte çalışacağını tanımlar.
    """

    __tablename__ = "shift_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    shift_time: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    employee: Mapped["Employee"] = relationship("Employee")

    def __repr__(self) -> str:
        return (
            f"<ShiftSchedule(id={self.id}, employee_id={self.employee_id}, "
            f"day='{self.day}', time='{self.shift_time}')>"
        )


class DailyActiveEmployee(Base):
    """
    Günlük aktif personel listesi tablosu.

    Her gün için hangi personellerin mola takip listesinde olduğunu tanımlar.
    """

    __tablename__ = "daily_active_employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    added_by: Mapped[str] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    employee: Mapped["Employee"] = relationship("Employee")

    def __repr__(self) -> str:
        return (
            f"<DailyActiveEmployee(id={self.id}, employee_id={self.employee_id}, "
            f"date={self.date})>"
        )
