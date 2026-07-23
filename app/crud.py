"""
Veritabanı CRUD işlemleri (fonksiyon bazlı).

Tüm veritabanı erişim mantığı bu modülde toplanır.
Route katmanı doğrudan SQL sorguları çalıştırmaz; bu fonksiyonları çağırır.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.constants import ADMIN_CODE, ADMIN_PASSWORD, ADMIN_USERNAME, DAILY_BREAK_LIMIT
from app.exceptions import (
    ActiveBreakExists,
    BreakNotFound,
    BreakQuotaExceeded,
    EmployeeAlreadyExists,
    EmployeeNotFound,
    InvalidCredentials,
    NoActiveBreak,
    ReservedUsername,
)
from app.models import (
    Break,
    BreakHistory,
    BreakStatus,
    BreakType,
    DailyActiveEmployee,
    Department,
    Employee,
    ShiftSchedule,
    UserRole,
)
from app.schemas import (
    ActiveBreakSummary,
    BreakEnd,
    BreakHistoryItem,
    BreakHistoryResponse,
    BreakStart,
    DashboardStatistics,
    DashboardSummary,
    DailyActiveEmployeeCreate,
    DailyActiveEmployeeResponse,
    DepartmentCreate,
    DepartmentResponse,
    EmployeeCreate,
    EmployeeOverview,
    EmployeeStatusResponse,
    EmployeeStatusUpdate,
    EmployeeUpdate,
    ShiftScheduleCreate,
    ShiftScheduleResponse,
    UserLogin,
    UserRegister,
)


# ---------------------------------------------------------------------------
# Günlük Mola Hakkı Yardımcıları
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    """UTC bazında bugünün tarihini döndürür."""
    return datetime.now(timezone.utc).date()


def _today_start_utc() -> datetime:
    """Bugünün UTC başlangıç zamanı."""
    return datetime.combine(_today_utc(), time.min, tzinfo=timezone.utc)


def ensure_daily_quota(employee: Employee) -> bool:
    """Yeni güne geçildiyse günlük mola sayacını sıfırlar. Sıfırlandıysa True döner."""
    today = _today_utc()
    if employee.mola_kota_tarihi != today:
        employee.kullanilan_mola = 0
        employee.mola_kota_tarihi = today
        return True
    return False


def get_today_break_minutes(db: Session, employee_id: int) -> float:
    """Bugün tamamlanan molaların toplam süresini dakika cinsinden hesaplar."""
    today_start = _today_start_utc()
    stmt = (
        select(Break)
        .where(Break.employee_id == employee_id)
        .where(Break.status == BreakStatus.COMPLETED)
        .where(Break.end_time >= today_start)
    )
    breaks = list(db.execute(stmt).scalars().all())
    total = 0.0
    for brk in breaks:
        if brk.end_time and brk.start_time:
            delta = brk.end_time - brk.start_time
            total += delta.total_seconds() / 60
    return round(total, 1)


def increment_break_usage(employee: Employee) -> None:
    """Mola bittiğinde günlük kullanılan mola sayısını artırır."""
    ensure_daily_quota(employee)
    employee.kullanilan_mola += 1


def can_start_break(employee: Employee) -> bool:
    """Personelin yeni mola başlatıp başlatamayacağını kontrol eder."""
    ensure_daily_quota(employee)
    return employee.kullanilan_mola < DAILY_BREAK_LIMIT and not employee.is_on_break


def log_break_history(db: Session, employee: Employee, break_record: Break) -> None:
    """Tamamlanan molayı breaks_history tablosuna yazar."""
    if not break_record.start_time or not break_record.end_time:
        return

    start = break_record.start_time
    end = break_record.end_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    duration = round((end - start).total_seconds() / 60, 2)
    history = BreakHistory(
        employee_id=employee.id,
        username=employee.employee_code,
        start_time=start,
        end_time=end,
        duration=duration,
        date=end.date(),
    )
    db.add(history)


def get_dashboard_summary(db: Session) -> DashboardSummary:
    """Yönetici paneli özet kartları için anlık istatistikleri döndürür."""
    stmt = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .where(Employee.role == UserRole.PERSONEL)
    )
    employees = list(db.execute(stmt).scalars().all())
    quota_reset = False
    on_break = 0
    quota_exhausted = 0

    for employee in employees:
        if ensure_daily_quota(employee):
            quota_reset = True
        if employee.is_on_break:
            on_break += 1
        elif employee.kullanilan_mola >= DAILY_BREAK_LIMIT:
            quota_exhausted += 1

    if quota_reset:
        db.commit()

    return DashboardSummary(
        toplam_aktif_personel=len(employees),
        su_an_molada=on_break,
        mola_hakki_biten=quota_exhausted,
    )


def get_dashboard_statistics(db: Session) -> DashboardStatistics:
    """Yönetici paneli detaylı istatistiklerini döndürür."""
    from datetime import datetime, timedelta
    
    stmt = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .where(Employee.role == UserRole.PERSONEL)
    )
    employees = list(db.execute(stmt).scalars().all())
    
    on_break = 0
    quota_exhausted = 0
    personel_istatistikleri = []
    
    # Son 24 saat hesaplaması
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    
    for employee in employees:
        if ensure_daily_quota(employee):
            db.commit()
        
        if employee.is_on_break:
            on_break += 1
        elif employee.kullanilan_mola >= DAILY_BREAK_LIMIT:
            quota_exhausted += 1
        
        # Personel bazlı istatistikler
        personel_istatistikleri.append({
            "id": employee.id,
            "full_name": employee.full_name,
            "employee_code": employee.employee_code,
            "kullanilan_mola": employee.kullanilan_mola,
            "is_on_break": employee.is_on_break,
        })
    
    # Son 24 saatteki toplam mola süresi
    stmt_breaks = (
        select(Break)
        .where(Break.start_time >= twenty_four_hours_ago)
        .where(Break.status == BreakStatus.COMPLETED)
    )
    breaks = list(db.execute(stmt_breaks).scalars().all())
    son_24_saat_toplam = sum(int((b.end_time - b.start_time).total_seconds() / 60) for b in breaks if b.end_time)
    
    return DashboardStatistics(
        toplam_aktif_personel=len(employees),
        su_an_molada=on_break,
        son_24_saat_toplam_mola_dk=son_24_saat_toplam,
        personel_bazli_istatistikler=personel_istatistikleri,
    )


def _history_date_range(period: str) -> tuple[date | None, date | None]:
    """Geçmiş filtre dönemine göre tarih aralığı döndürür."""
    today = _today_utc()
    if period == "bugun":
        return today, today
    if period == "dun":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if period == "gecen_hafta":
        return today - timedelta(days=6), today
    return None, None


def get_break_history(
    db: Session,
    employee_id: int,
    period: str = "gecen_hafta",
) -> BreakHistoryResponse:
    """
    Personelin geçmiş mola kayıtlarını filtreli olarak getirir.

    Raises:
        EmployeeNotFound: Çalışan bulunamazsa.
    """
    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)

    start_date, end_date = _history_date_range(period)
    stmt = select(BreakHistory).where(BreakHistory.employee_id == employee_id)

    if start_date and end_date:
        stmt = stmt.where(BreakHistory.date >= start_date).where(BreakHistory.date <= end_date)

    stmt = stmt.order_by(BreakHistory.start_time.desc())
    records = list(db.execute(stmt).scalars().all())
    total_duration = round(sum(r.duration for r in records), 1)

    return BreakHistoryResponse(
        employee_id=employee.id,
        full_name=employee.full_name,
        username=employee.employee_code,
        period=period,
        total_records=len(records),
        total_duration_minutes=total_duration,
        records=[BreakHistoryItem.model_validate(r) for r in records],
    )


def build_employee_overview(db: Session, employee: Employee) -> EmployeeOverview:
    """Tek bir çalışan için panel özet kaydı oluşturur."""
    ensure_daily_quota(employee)
    total_minutes = get_today_break_minutes(db, employee.id)
    quota_exhausted = employee.kullanilan_mola >= DAILY_BREAK_LIMIT
    on_break = employee.is_on_break

    if on_break and employee.break_start_time and employee.break_duration_minutes:
        summary = ActiveBreakSummary(
            break_id=0,
            start_time=employee.break_start_time,
            planned_duration_minutes=employee.break_duration_minutes,
            remaining_seconds=0,
        )
        work_status = "molada"
    else:
        summary = None
        work_status = "calisiyor"

    return EmployeeOverview(
        id=employee.id,
        employee_code=employee.employee_code,
        full_name=employee.full_name,
        department=employee.department,
        role=employee.role,
        is_active=employee.is_active,
        is_on_break=on_break,
        created_at=employee.created_at,
        work_status=work_status,
        active_break=summary,
        assigned_by=employee.assigned_by if on_break else None,
        kullanilan_mola=employee.kullanilan_mola,
        mola_hakki_limit=DAILY_BREAK_LIMIT,
        bugunku_toplam_mola_dk=total_minutes,
        mola_hakki_bitti=quota_exhausted,
        can_start_break=can_start_break(employee),
    )


# ---------------------------------------------------------------------------
# Kimlik Doğrulama
# ---------------------------------------------------------------------------


def is_admin_username(username: str) -> bool:
    """Kullanıcı adının sabit admin hesabına ait olup olmadığını kontrol eder."""
    return username.strip().lower() == ADMIN_USERNAME.lower()


def ensure_admin_user(db: Session) -> Employee:
    """Sabit admin hesabını oluşturur veya günceller."""
    admin = get_employee_by_code(db, ADMIN_CODE)
    if not admin:
        admin = Employee(
            employee_code=ADMIN_CODE,
            full_name=ADMIN_USERNAME,
            role=UserRole.YONETICI,
            password_hash=hash_password(ADMIN_PASSWORD),
        )
        db.add(admin)
    else:
        admin.full_name = ADMIN_USERNAME
        admin.role = UserRole.YONETICI
        admin.password_hash = hash_password(ADMIN_PASSWORD)
        admin.is_active = True
    db.commit()
    db.refresh(admin)
    return admin


def register_user(db: Session, user_in: UserRegister) -> Employee:
    """
    Yeni kullanıcı kaydı oluşturur (varsayılan rol: Personel).

    Raises:
        ReservedUsername: Admin kullanıcı adı rezerve edilmişse.
        EmployeeAlreadyExists: Kullanıcı adı zaten kayıtlıysa.
    """
    if is_admin_username(user_in.username):
        raise ReservedUsername()

    code = user_in.username.strip().upper()
    existing = get_employee_by_code(db, code)
    if existing:
        raise EmployeeAlreadyExists(user_in.username)

    employee = Employee(
        employee_code=code,
        full_name=user_in.username.strip(),
        role=UserRole.PERSONEL,
        password_hash=hash_password(user_in.password),
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def authenticate_user(db: Session, login_in: UserLogin) -> Employee:
    """
    Kullanıcı girişini doğrular.

    'Eren' kullanıcısı sabit admin hesabıdır; doğru şifre ile
    otomatik yönetici yetkisi verilir.

    Her login sırasında veritabanından güncel rolü getirir.

    Raises:
        InvalidCredentials: Kullanıcı bulunamazsa veya şifre yanlışsa.
    """
    # Sabit admin girişi
    if login_in.username == ADMIN_CODE:
        admin = get_employee_by_code(db, ADMIN_CODE) or ensure_admin_user(db)
        if login_in.password != ADMIN_PASSWORD:
            raise InvalidCredentials()
        admin.role = UserRole.YONETICI
        db.commit()
        db.refresh(admin)
        return admin

    employee = get_employee_by_code(db, login_in.username)
    if not employee or not employee.is_active:
        raise InvalidCredentials()
    if not employee.password_hash or not verify_password(login_in.password, employee.password_hash):
        raise InvalidCredentials()
    
    # Veritabanından güncel rolü refresh et
    db.refresh(employee)
    return employee


# ---------------------------------------------------------------------------
# Çalışan (Employee) CRUD
# ---------------------------------------------------------------------------


def get_employee_by_id(db: Session, employee_id: int) -> Employee | None:
    """ID ile çalışan getirir."""
    return db.get(Employee, employee_id)


def get_employee_by_code(db: Session, employee_code: str) -> Employee | None:
    """Kullanıcı adı (sicil no) ile çalışan getirir."""
    stmt = select(Employee).where(Employee.employee_code == employee_code.upper())
    return db.execute(stmt).scalar_one_or_none()


def get_employees(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
) -> list[Employee]:
    """Çalışan listesini sayfalı olarak getirir."""
    stmt = select(Employee).offset(skip).limit(limit).order_by(Employee.full_name)
    if active_only:
        stmt = stmt.where(Employee.is_active.is_(True))
    return list(db.execute(stmt).scalars().all())


def search_users(db: Session, query: str) -> list[Employee]:
    """Kullanıcı adına göre personel arar (yönetim paneli için)."""
    pattern = f"%{query.strip().upper()}%"
    stmt = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .where(
            (Employee.employee_code.ilike(pattern))
            | (Employee.full_name.ilike(pattern))
        )
        .order_by(Employee.full_name)
        .limit(50)
    )
    return list(db.execute(stmt).scalars().all())


def promote_to_manager(db: Session, employee_id: int) -> Employee:
    """
    Personeli yönetici rolüne terfi ettirir.

    Raises:
        EmployeeNotFound: Kullanıcı bulunamazsa.
        UnauthorizedAction: Zaten yönetici ise.
    """
    from app.exceptions import UnauthorizedAction

    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)
    if employee.role == UserRole.YONETICI:
        raise UnauthorizedAction("Bu kullanıcı zaten yönetici yetkisine sahip.")

    employee.role = UserRole.YONETICI
    db.commit()
    db.refresh(employee)
    return employee


def create_employee(db: Session, employee_in: EmployeeCreate) -> Employee:
    """
    Yeni çalışan oluşturur.

    Raises:
        EmployeeAlreadyExists: Sicil numarası zaten kayıtlıysa.
    """
    existing = get_employee_by_code(db, employee_in.employee_code)
    if existing:
        raise EmployeeAlreadyExists(employee_in.employee_code)

    employee = Employee(
        employee_code=employee_in.employee_code,
        full_name=employee_in.full_name,
        department=employee_in.department,
        role=UserRole.PERSONEL,
        password_hash=hash_password(employee_in.password),
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def update_employee(
    db: Session,
    employee_id: int,
    employee_in: EmployeeUpdate,
) -> Employee:
    """
    Mevcut çalışan bilgilerini günceller.

    Raises:
        EmployeeNotFound: Çalışan bulunamazsa.
    """
    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)

    update_data = employee_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)
    return employee


def get_employees_overview(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[EmployeeOverview]:
    """
    Yönetici paneli için personel listesini anlık mola durumuyla getirir.
    Sadece 'personel' rolündeki aktif çalışanlar listelenir.
    """
    stmt = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .where(Employee.role == UserRole.PERSONEL)
        .offset(skip)
        .limit(limit)
        .order_by(Employee.full_name)
    )
    employees = list(db.execute(stmt).scalars().all())
    overview: list[EmployeeOverview] = []
    quota_reset = False

    for employee in employees:
        if ensure_daily_quota(employee):
            quota_reset = True
        overview.append(build_employee_overview(db, employee))

    if quota_reset:
        db.commit()

    return overview


def get_employee_status(db: Session, employee_id: int) -> EmployeeStatusResponse:
    """
    Personel durum sorgulama — polling endpoint'i için.

    Raises:
        EmployeeNotFound: Çalışan bulunamazsa.
    """
    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)

    if ensure_daily_quota(employee):
        db.commit()
        db.refresh(employee)

    return EmployeeStatusResponse(
        id=employee.id,
        full_name=employee.full_name,
        employee_code=employee.employee_code,
        role=employee.role,
        department=employee.department,
        is_on_break=employee.is_on_break,
        break_start_time=employee.break_start_time,
        break_duration_minutes=employee.break_duration_minutes,
        assigned_by=employee.assigned_by,
    )


def update_employee_status(
    db: Session,
    employee_id: int,
    status_in: EmployeeStatusUpdate,
) -> EmployeeStatusResponse:
    """
    Çalışan mola durumunu günceller (PATCH /employees/{id}/status).

    Mola başlatıldığında Employee alanları ve Break kaydı senkronize edilir.
    Mola bitirildiğinde her iki kaynak da temizlenir.

    Raises:
        EmployeeNotFound: Çalışan bulunamazsa.
        ActiveBreakExists: Zaten molada iken tekrar başlatma.
    """
    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)

    if status_in.is_on_break:
        if employee.is_on_break:
            raise ActiveBreakExists(employee_id)

        ensure_daily_quota(employee)
        if employee.kullanilan_mola >= DAILY_BREAK_LIMIT:
            raise BreakQuotaExceeded(employee_id, DAILY_BREAK_LIMIT)

        now = datetime.now(timezone.utc)
        employee.is_on_break = True
        employee.break_start_time = now
        employee.break_duration_minutes = status_in.break_duration_minutes
        employee.assigned_by = status_in.assigned_by or "Bölüm Müdürü"

        # Mola geçmişi kaydı oluştur
        break_record = Break(
            employee_id=employee_id,
            break_type=BreakType.SHORT,
            status=BreakStatus.ACTIVE,
            start_time=now,
            planned_duration_minutes=status_in.break_duration_minutes,
            notes=f"{employee.assigned_by} tarafından atandı",
        )
        db.add(break_record)
    else:
        employee.is_on_break = False
        employee.break_start_time = None
        employee.break_duration_minutes = None
        employee.assigned_by = None

        active_break = get_active_break(db, employee_id)
        if active_break:
            active_break.status = BreakStatus.COMPLETED
            active_break.end_time = datetime.now(timezone.utc)
            log_break_history(db, employee, active_break)

        increment_break_usage(employee)

    db.commit()
    db.refresh(employee)
    return get_employee_status(db, employee_id)


def delete_employee(db: Session, employee_id: int) -> None:
    """
    Çalışanı ve ilişkili mola kayıtlarını siler (cascade).

    Raises:
        EmployeeNotFound: Çalışan bulunamazsa.
    """
    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)

    db.delete(employee)
    db.commit()


def delete_user(db: Session, user_id: int) -> None:
    """
    Kullanıcıyı sistemden siler.

    Sabit admin hesabı (Eren) silinemez.

    Raises:
        EmployeeNotFound: Kullanıcı bulunamazsa.
        UnauthorizedAction: Admin hesabı silinmeye çalışılırsa.
    """
    from app.exceptions import UnauthorizedAction

    employee = get_employee_by_id(db, user_id)
    if not employee:
        raise EmployeeNotFound(employee_id=user_id)
    if employee.employee_code.upper() == ADMIN_CODE:
        raise UnauthorizedAction("Admin hesabı silinemez.")

    delete_employee(db, user_id)


# ---------------------------------------------------------------------------
# Mola (Break) CRUD
# ---------------------------------------------------------------------------


def get_break_by_id(db: Session, break_id: int) -> Break | None:
    """ID ile mola kaydı getirir."""
    return db.get(Break, break_id)


def get_active_break(db: Session, employee_id: int) -> Break | None:
    """Çalışanın aktif molasını getirir (varsa)."""
    stmt = (
        select(Break)
        .where(Break.employee_id == employee_id)
        .where(Break.status == BreakStatus.ACTIVE)
        .order_by(Break.start_time.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_breaks_by_employee(
    db: Session,
    employee_id: int,
    *,
    skip: int = 0,
    limit: int = 50,
    status: BreakStatus | None = None,
) -> list[Break]:
    """Belirli bir çalışanın mola geçmişini getirir."""
    stmt = (
        select(Break)
        .where(Break.employee_id == employee_id)
        .offset(skip)
        .limit(limit)
        .order_by(Break.start_time.desc())
    )
    if status:
        stmt = stmt.where(Break.status == status)
    return list(db.execute(stmt).scalars().all())


def get_all_breaks(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    status: BreakStatus | None = None,
    break_type: BreakType | None = None,
) -> list[Break]:
    """Tüm mola kayıtlarını filtreli olarak getirir."""
    stmt = select(Break).offset(skip).limit(limit).order_by(Break.start_time.desc())
    if status:
        stmt = stmt.where(Break.status == status)
    if break_type:
        stmt = stmt.where(Break.break_type == break_type)
    return list(db.execute(stmt).scalars().all())


def start_break(
    db: Session,
    employee_id: int,
    break_in: BreakStart,
) -> Break:
    """
    Çalışan için yeni mola başlatır.

    Raises:
        EmployeeNotFound: Çalışan bulunamazsa veya pasifse.
        ActiveBreakExists: Zaten aktif mola varsa.
    """
    employee = get_employee_by_id(db, employee_id)
    if not employee or not employee.is_active:
        raise EmployeeNotFound(employee_id=employee_id)

    active = get_active_break(db, employee_id)
    if active:
        raise ActiveBreakExists(employee_id)

    ensure_daily_quota(employee)
    if employee.kullanilan_mola >= DAILY_BREAK_LIMIT:
        raise BreakQuotaExceeded(employee_id, DAILY_BREAK_LIMIT)

    break_record = Break(
        employee_id=employee_id,
        break_type=break_in.break_type,
        status=BreakStatus.ACTIVE,
        planned_duration_minutes=break_in.planned_duration_minutes,
        notes=break_in.notes,
    )
    db.add(break_record)

    # Employee durum alanlarını senkronize et
    employee.is_on_break = True
    employee.break_start_time = break_record.start_time
    employee.break_duration_minutes = break_in.planned_duration_minutes

    db.commit()
    db.refresh(break_record)
    return break_record


def end_break(
    db: Session,
    employee_id: int,
    break_in: BreakEnd | None = None,
) -> Break:
    """
    Çalışanın aktif molasını sonlandırır.

    Raises:
        EmployeeNotFound: Çalışan bulunamazsa.
        NoActiveBreak: Aktif mola yoksa.
    """
    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)

    active_break = get_active_break(db, employee_id)
    if not active_break:
        raise NoActiveBreak(employee_id)

    active_break.status = BreakStatus.COMPLETED
    active_break.end_time = datetime.now(timezone.utc)

    if break_in and break_in.notes:
        # Mevcut not varsa birleştir, yoksa doğrudan ata
        if active_break.notes:
            active_break.notes = f"{active_break.notes} | Bitiş: {break_in.notes}"
        else:
            active_break.notes = break_in.notes

    log_break_history(db, employee, active_break)

    # Employee durum alanlarını temizle ve mola hakkını artır
    employee.is_on_break = False
    employee.break_start_time = None
    employee.break_duration_minutes = None


# ---------------------------------------------------------------------------
# Departman CRUD İşlemleri
# ---------------------------------------------------------------------------


def get_departments(db: Session) -> list[Department]:
    """Tüm aktif departmanları getirir."""
    return db.query(Department).filter(Department.is_active == True).all()


def get_department_by_id(db: Session, department_id: int) -> Department | None:
    """ID'ye göre departman getirir."""
    return db.query(Department).filter(Department.id == department_id).first()


def create_department(db: Session, department_in: DepartmentCreate) -> Department:
    """Yeni departman oluşturur."""
    department = Department(
        name=department_in.name,
        description=department_in.description,
    )
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


def update_department(
    db: Session, department_id: int, department_in: DepartmentCreate
) -> Department:
    """Departman günceller."""
    department = get_department_by_id(db, department_id)
    if not department:
        raise Exception(f"Departman bulunamadı: {department_id}")
    
    department.name = department_in.name
    department.description = department_in.description
    db.commit()
    db.refresh(department)
    return department


def delete_department(db: Session, department_id: int) -> bool:
    """Departman siler (soft delete)."""
    department = get_department_by_id(db, department_id)
    if not department:
        return False
    
    department.is_active = False
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Vardiya Programı CRUD İşlemleri
# ---------------------------------------------------------------------------


def get_shift_schedules(db: Session, employee_id: int | None = None) -> list[ShiftSchedule]:
    """Vardiya programlarını getirir."""
    query = db.query(ShiftSchedule)
    if employee_id:
        query = query.filter(ShiftSchedule.employee_id == employee_id)
    return query.all()


def get_shift_schedule_by_id(db: Session, schedule_id: int) -> ShiftSchedule | None:
    """ID'ye göre vardiya programı getirir."""
    return db.query(ShiftSchedule).filter(ShiftSchedule.id == schedule_id).first()


def create_shift_schedule(db: Session, schedule_in: ShiftScheduleCreate) -> ShiftSchedule:
    """Yeni vardiya programı oluşturur."""
    schedule = ShiftSchedule(
        employee_id=schedule_in.employee_id,
        day=schedule_in.day,
        shift_time=schedule_in.shift_time,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def update_shift_schedule(
    db: Session, schedule_id: int, schedule_in: ShiftScheduleCreate
) -> ShiftSchedule:
    """Vardiya programını günceller."""
    schedule = get_shift_schedule_by_id(db, schedule_id)
    if not schedule:
        raise Exception(f"Vardiya programı bulunamadı: {schedule_id}")
    
    schedule.employee_id = schedule_in.employee_id
    schedule.day = schedule_in.day
    schedule.shift_time = schedule_in.shift_time
    db.commit()
    db.refresh(schedule)
    return schedule


def delete_shift_schedule(db: Session, schedule_id: int) -> bool:
    """Vardiya programını siler."""
    schedule = get_shift_schedule_by_id(db, schedule_id)
    if not schedule:
        return False
    
    db.delete(schedule)
    db.commit()
    return True


def get_employees_by_department_and_day(
    db: Session, department_id: int, day: str
) -> list[Employee]:
    """Departman ve güne göre personelleri getirir."""
    return (
        db.query(Employee)
        .join(ShiftSchedule, Employee.id == ShiftSchedule.employee_id)
        .filter(
            Employee.department_id == department_id,
            ShiftSchedule.day == day,
            Employee.is_active == True,
        )
        .all()
    )


# ---------------------------------------------------------------------------
# Günlük Aktif Personel Listesi CRUD İşlemleri
# ---------------------------------------------------------------------------


def get_daily_active_employees(db: Session, date: date) -> list[DailyActiveEmployee]:
    """Belirli bir tarih için aktif personelleri getirir."""
    return (
        db.query(DailyActiveEmployee)
        .filter(DailyActiveEmployee.date == date)
        .all()
    )


def get_daily_active_employee_by_employee_and_date(
    db: Session, employee_id: int, date: date
) -> DailyActiveEmployee | None:
    """Personel ve tarihe göre aktif personel kaydını getirir."""
    return (
        db.query(DailyActiveEmployee)
        .filter(
            DailyActiveEmployee.employee_id == employee_id,
            DailyActiveEmployee.date == date,
        )
        .first()
    )


def create_daily_active_employee(
    db: Session, daily_in: DailyActiveEmployeeCreate, added_by: str
) -> DailyActiveEmployee:
    """Günlük aktif personel ekler."""
    daily = DailyActiveEmployee(
        employee_id=daily_in.employee_id,
        date=daily_in.work_date,
        added_by=added_by,
    )
    db.add(daily)
    db.commit()
    db.refresh(daily)
    return daily


def delete_daily_active_employee(
    db: Session, employee_id: int, date: date
) -> bool:
    """Günlük aktif personeli siler."""
    daily = get_daily_active_employee_by_employee_and_date(db, employee_id, date)
    if not daily:
        return False
    
    db.delete(daily)
    db.commit()
    return True


def get_active_employees_for_break_tracking(db: Session, date: date) -> list[Employee]:
    """Mola takibi için aktif personelleri getirir (detaylı)."""
    daily_records = get_daily_active_employees(db, date)
    employee_ids = [d.employee_id for d in daily_records]
    
    return (
        db.query(Employee)
        .filter(Employee.id.in_(employee_ids))
        .all()
    )


def get_break_or_raise(db: Session, break_id: int) -> Break:
    """
    Mola kaydını getirir; bulunamazsa exception fırlatır.

    Raises:
        BreakNotFound: Mola kaydı bulunamazsa.
    """
    break_record = get_break_by_id(db, break_id)
    if not break_record:
        raise BreakNotFound(break_id)
    return break_record
