"""
FastAPI uygulama giriş noktası ve API rotaları.

Tüm HTTP endpoint'leri bu modülde tanımlanır.
Veritabanı oturumu Dependency Injection ile güvenli şekilde yönetilir.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import os

from fastapi import Depends, FastAPI, File, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db, init_db
from app.errors import translate_validation_errors
from app.exceptions import MolaSistemiException
from app.models import BreakStatus, BreakType, Employee
from app.schemas import (
    AuthResponse,
    BreakEnd,
    BreakHistoryResponse,
    BreakResponse,
    BreakStart,
    BreakWithEmployee,
    DashboardStatistics,
    DashboardSummary,
    DailyActiveEmployeeCreate,
    DailyActiveEmployeeResponse,
    DepartmentCreate,
    DepartmentResponse,
    EmployeeCreate,
    EmployeeOverview,
    EmployeeResponse,
    EmployeeStatusResponse,
    EmployeeStatusUpdate,
    EmployeeUpdate,
    HealthResponse,
    MessageResponse,
    ShiftScheduleCreate,
    ShiftScheduleResponse,
    UserLogin,
    UserManageItem,
    UserRegister,
)

# Tip alias: Dependency Injection ile enjekte edilen DB oturumu
DbSession = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Uygulama yaşam döngüsü yöneticisi.

    Başlangıçta veritabanı tablolarını oluşturur;
    kapanışta temizlik işlemleri yapılabilir.
    """
    init_db()
    yield


app = FastAPI(
    title="Çok Kullanıcılı Mola Yönetim Sistemi",
    description="Yönetici ve personel rolleriyle mola yönetimi REST API",
    version="3.0.0",
    lifespan=lifespan,
)

# Frontend'in farklı porttan API'ye erişebilmesi için CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception Handler
# ---------------------------------------------------------------------------


@app.exception_handler(MolaSistemiException)
async def mola_sistemi_exception_handler(request, exc: MolaSistemiException):
    """Özel domain exception'larını standart HTTP yanıtına dönüştürür."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic doğrulama hatalarını anlaşılır Türkçe mesajlara çevirir."""
    message = translate_validation_errors(exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": message},
    )


# ---------------------------------------------------------------------------
# Sağlık Kontrolü
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Sistem"],
    summary="API sağlık kontrolü",
)
def health_check() -> HealthResponse:
    """Servisin ayakta olup olmadığını kontrol eder."""
    return HealthResponse()


# ---------------------------------------------------------------------------
# Kimlik Doğrulama
# ---------------------------------------------------------------------------


@app.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Kimlik Doğrulama"],
    summary="Kayıt ol",
)
def register(user_in: UserRegister, db: DbSession) -> AuthResponse:
    """Yeni kullanıcı kaydı oluşturur (varsayılan rol: Personel)."""
    employee = crud.register_user(db, user_in)
    return AuthResponse(
        id=employee.id,
        full_name=employee.full_name,
        employee_code=employee.employee_code,
        role=employee.role,
        message="Kayıt başarılı",
    )


@app.post(
    "/auth/login",
    response_model=AuthResponse,
    tags=["Kimlik Doğrulama"],
    summary="Giriş yap",
)
def login(login_in: UserLogin, db: DbSession) -> AuthResponse:
    """Sicil numarası ve şifre ile giriş yapar."""
    employee = crud.authenticate_user(db, login_in)
    return AuthResponse(
        id=employee.id,
        full_name=employee.full_name,
        employee_code=employee.employee_code,
        role=employee.role,
        message="Giriş başarılı",
    )


# ---------------------------------------------------------------------------
# Çalışan (Employee) Rotaları
# ---------------------------------------------------------------------------


@app.post(
    "/employees",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Çalışanlar"],
    summary="Yeni çalışan oluştur",
)
def create_employee(
    employee_in: EmployeeCreate,
    db: DbSession,
) -> EmployeeResponse:
    """Sisteme yeni bir çalışan kaydı ekler."""
    return crud.create_employee(db, employee_in)


@app.get(
    "/employees",
    response_model=list[EmployeeResponse],
    tags=["Çalışanlar"],
    summary="Çalışan listesi",
)
def list_employees(
    db: DbSession,
    skip: int = Query(0, ge=0, description="Atlanacak kayıt sayısı"),
    limit: int = Query(100, ge=1, le=500, description="Döndürülecek maksimum kayıt"),
    active_only: bool = Query(False, description="Sadece aktif çalışanları getir"),
) -> list[EmployeeResponse]:
    """Tüm çalışanları sayfalı olarak listeler."""
    return crud.get_employees(db, skip=skip, limit=limit, active_only=active_only)


@app.get(
    "/employees/overview",
    response_model=list[EmployeeOverview],
    tags=["Çalışanlar"],
    summary="Panel personel listesi",
)
def list_employees_overview(
    db: DbSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[EmployeeOverview]:
    """
    Yönetim paneli için çalışan listesini anlık durum bilgisiyle döndürür.

    Her kayıt; ad soyad, sicil no, çalışma durumu ve aktif mola geri sayımını içerir.
    """
    return crud.get_employees_overview(db, skip=skip, limit=limit)


@app.get(
    "/dashboard/summary",
    response_model=DashboardSummary,
    tags=["Dashboard"],
    summary="Günün özeti",
)
def get_dashboard_summary(db: DbSession) -> DashboardSummary:
    """Yönetici paneli özet kartları için anlık istatistikleri döndürür."""
    return crud.get_dashboard_summary(db)


@app.get(
    "/employees/{employee_id}/history",
    response_model=BreakHistoryResponse,
    tags=["Çalışanlar"],
    summary="Personel mola geçmişi",
)
def get_employee_history(
    employee_id: int,
    db: DbSession,
    period: str = Query(
        "gecen_hafta",
        description="Filtre: bugun, dun, gecen_hafta, tumu",
    ),
) -> BreakHistoryResponse:
    """Personelin geçmiş mola hareketlerini filtreli olarak listeler."""
    return crud.get_break_history(db, employee_id, period)


@app.get(
    "/employees/{employee_id}",
    response_model=EmployeeResponse,
    tags=["Çalışanlar"],
    summary="Çalışan detayı",
)
def get_employee(employee_id: int, db: DbSession) -> EmployeeResponse:
    """Belirli bir çalışanın bilgilerini getirir."""
    from app.exceptions import EmployeeNotFound

    employee = crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)
    return employee


@app.patch(
    "/employees/{employee_id}",
    response_model=EmployeeResponse,
    tags=["Çalışanlar"],
    summary="Çalışan güncelle",
)
def update_employee(
    employee_id: int,
    employee_in: EmployeeUpdate,
    db: DbSession,
) -> EmployeeResponse:
    """Mevcut çalışan bilgilerini kısmi olarak günceller."""
    return crud.update_employee(db, employee_id, employee_in)


@app.patch(
    "/employees/{employee_id}/status",
    response_model=EmployeeStatusResponse,
    tags=["Çalışanlar"],
    summary="Personel mola durumu güncelle",
)
def update_employee_status(
    employee_id: int,
    status_in: EmployeeStatusUpdate,
    db: DbSession,
) -> EmployeeStatusResponse:
    """
    Yönetici tarafından personel mola durumunu günceller.

    Mola başlatmak için is_on_break=true ve break_duration_minutes gönderilir.
    Mola bitirmek için is_on_break=false gönderilir.
    """
    return crud.update_employee_status(db, employee_id, status_in)


@app.get(
    "/employees/{employee_id}/status",
    response_model=EmployeeStatusResponse,
    tags=["Çalışanlar"],
    summary="Personel durum sorgula (polling)",
)
def get_employee_status(employee_id: int, db: DbSession) -> EmployeeStatusResponse:
    """Personelin anlık mola durumunu döndürür — frontend polling için kullanılır."""
    return crud.get_employee_status(db, employee_id)


# ---------------------------------------------------------------------------
# Kullanıcı Yönetimi (Yönetici)
# ---------------------------------------------------------------------------


@app.get(
    "/users/search",
    response_model=list[UserManageItem],
    tags=["Kullanıcı Yönetimi"],
    summary="Kullanıcı ara",
)
def search_users(
    db: DbSession,
    q: str = Query(..., min_length=1, description="Aranacak kullanıcı adı"),
) -> list[UserManageItem]:
    """Kullanıcı adına göre personel arar."""
    users = crud.search_users(db, q)
    return [
        UserManageItem(
            id=u.id,
            username=u.employee_code,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
        )
        for u in users
    ]


@app.patch(
    "/users/{user_id}/promote",
    response_model=UserManageItem,
    tags=["Kullanıcı Yönetimi"],
    summary="Yönetici yap",
)
def promote_user(user_id: int, db: DbSession) -> UserManageItem:
    """Personeli yönetici rolüne terfi ettirir."""
    employee = crud.promote_to_manager(db, user_id)
    return UserManageItem(
        id=employee.id,
        username=employee.employee_code,
        full_name=employee.full_name,
        role=employee.role,
        is_active=employee.is_active,
    )


@app.delete(
    "/users/{user_id}",
    response_model=MessageResponse,
    tags=["Kullanıcı Yönetimi"],
    summary="Kullanıcı sil",
)
def delete_user(user_id: int, db: DbSession) -> MessageResponse:
    """Kullanıcıyı ve tüm mola geçmişini sistemden kaldırır."""
    crud.delete_user(db, user_id)
    return MessageResponse(
        message="Kullanıcı başarıyla silindi",
        detail=f"user_id={user_id}",
    )


@app.delete(
    "/employees/{employee_id}",
    response_model=MessageResponse,
    tags=["Çalışanlar"],
    summary="Çalışan sil",
)
def delete_employee(employee_id: int, db: DbSession) -> MessageResponse:
    """Çalışanı ve tüm mola geçmişini sistemden kaldırır."""
    crud.delete_employee(db, employee_id)
    return MessageResponse(
        message="Çalışan başarıyla silindi",
        detail=f"employee_id={employee_id}",
    )


# ---------------------------------------------------------------------------
# Mola (Break) Rotaları
# ---------------------------------------------------------------------------


@app.post(
    "/employees/{employee_id}/breaks/start",
    response_model=BreakResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Molalar"],
    summary="Mola başlat",
)
def start_break(
    employee_id: int,
    break_in: BreakStart,
    db: DbSession,
) -> BreakResponse:
    """
    Belirtilen çalışan için yeni mola başlatır.

    Çalışanın zaten aktif bir molası varsa 409 Conflict döner.
    """
    return crud.start_break(db, employee_id, break_in)


@app.post(
    "/employees/{employee_id}/breaks/end",
    response_model=BreakResponse,
    tags=["Molalar"],
    summary="Mola bitir",
)
def end_break(
    employee_id: int,
    db: DbSession,
    break_in: BreakEnd | None = None,
) -> BreakResponse:
    """
    Çalışanın aktif molasını sonlandırır.

    Aktif mola yoksa 404 Not Found döner.
    """
    return crud.end_break(db, employee_id, break_in)


@app.get(
    "/employees/{employee_id}/breaks/active",
    response_model=BreakResponse,
    tags=["Molalar"],
    summary="Aktif mola sorgula",
)
def get_active_break(employee_id: int, db: DbSession) -> BreakResponse:
    """Çalışanın şu an devam eden aktif molasını getirir."""
    from app.exceptions import NoActiveBreak

    active = crud.get_active_break(db, employee_id)
    if not active:
        raise NoActiveBreak(employee_id)
    return active


@app.get(
    "/employees/{employee_id}/breaks",
    response_model=list[BreakResponse],
    tags=["Molalar"],
    summary="Çalışan mola geçmişi",
)
def list_employee_breaks(
    employee_id: int,
    db: DbSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: BreakStatus | None = Query(None, alias="status"),
) -> list[BreakResponse]:
    """Belirli bir çalışanın mola geçmişini listeler."""
    from app.exceptions import EmployeeNotFound

    employee = crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise EmployeeNotFound(employee_id=employee_id)

    return crud.get_breaks_by_employee(
        db, employee_id, skip=skip, limit=limit, status=status_filter
    )


@app.get(
    "/breaks",
    response_model=list[BreakWithEmployee],
    tags=["Molalar"],
    summary="Tüm mola kayıtları",
)
def list_all_breaks(
    db: DbSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status_filter: BreakStatus | None = Query(None, alias="status"),
    break_type: BreakType | None = Query(None, description="Mola türü filtresi"),
) -> list[BreakWithEmployee]:
    """Sistemdeki tüm mola kayıtlarını (çalışan bilgisiyle) listeler."""
    return crud.get_all_breaks(
        db,
        skip=skip,
        limit=limit,
        status=status_filter,
        break_type=break_type,
    )


@app.get(
    "/breaks/{break_id}",
    response_model=BreakResponse,
    tags=["Molalar"],
    summary="Mola detayı",
)
def get_break(break_id: int, db: DbSession) -> BreakResponse:
    """Belirli bir mola kaydının detaylarını getirir."""
    return crud.get_break_or_raise(db, break_id)


# ---------------------------------------------------------------------------
# Departman Endpoint'leri
# ---------------------------------------------------------------------------


@app.get("/departments", tags=["Departman"], response_model=list[DepartmentResponse])
def get_departments_endpoint(db: DbSession):
    """Tüm aktif departmanları getirir."""
    return crud.get_departments(db)


@app.post("/departments", tags=["Departman"], response_model=DepartmentResponse)
def create_department_endpoint(department_in: DepartmentCreate, db: DbSession):
    """Yeni departman oluşturur."""
    return crud.create_department(db, department_in)


@app.put("/departments/{department_id}", tags=["Departman"], response_model=DepartmentResponse)
def update_department_endpoint(
    department_id: int, department_in: DepartmentCreate, db: DbSession
):
    """Departman günceller."""
    return crud.update_department(db, department_id, department_in)


@app.delete("/departments/{department_id}", tags=["Departman"])
def delete_department_endpoint(department_id: int, db: DbSession):
    """Departman siler."""
    crud.delete_department(db, department_id)
    return {"message": "Departman silindi"}


# ---------------------------------------------------------------------------
# Vardiya Programı Endpoint'leri
# ---------------------------------------------------------------------------


@app.get("/shift-schedules", tags=["Vardiya Programı"], response_model=list[ShiftScheduleResponse])
def get_shift_schedules_endpoint(db: DbSession, employee_id: int | None = None):
    """Vardiya programlarını getirir."""
    return crud.get_shift_schedules(db, employee_id)


@app.post("/shift-schedules", tags=["Vardiya Programı"], response_model=ShiftScheduleResponse)
def create_shift_schedule_endpoint(schedule_in: ShiftScheduleCreate, db: DbSession):
    """Yeni vardiya programı oluşturur."""
    return crud.create_shift_schedule(db, schedule_in)


@app.put("/shift-schedules/{schedule_id}", tags=["Vardiya Programı"], response_model=ShiftScheduleResponse)
def update_shift_schedule_endpoint(
    schedule_id: int, schedule_in: ShiftScheduleCreate, db: DbSession
):
    """Vardiya programını günceller."""
    return crud.update_shift_schedule(db, schedule_id, schedule_in)


@app.delete("/shift-schedules/{schedule_id}", tags=["Vardiya Programı"])
def delete_shift_schedule_endpoint(schedule_id: int, db: DbSession):
    """Vardiya programını siler."""
    crud.delete_shift_schedule(db, schedule_id)
    return {"message": "Vardiya programı silindi"}


@app.get("/departments/{department_id}/employees/{day}", tags=["Departman"])
def get_employees_by_department_and_day_endpoint(
    department_id: int, day: str, db: DbSession
):
    """Departman ve güne göre personelleri getirir."""
    employees = crud.get_employees_by_department_and_day(db, department_id, day)
    return [
        {
            "id": emp.id,
            "employee_code": emp.employee_code,
            "full_name": emp.full_name,
            "department": emp.department,
        }
        for emp in employees
    ]


# ---------------------------------------------------------------------------
# Günlük Aktif Personel Listesi Endpoint'leri
# ---------------------------------------------------------------------------


@app.get("/daily-active-employees", tags=["Günlük Aktif Personel"], response_model=list[DailyActiveEmployeeResponse])
def get_daily_active_employees_endpoint(date: date, db: DbSession):
    """Belirli bir tarih için aktif personelleri getirir."""
    return crud.get_daily_active_employees(db, date)


@app.post("/daily-active-employees", tags=["Günlük Aktif Personel"], response_model=DailyActiveEmployeeResponse)
def create_daily_active_employee_endpoint(
    daily_in: DailyActiveEmployeeCreate,
    db: DbSession,
):
    """Günlük aktif personel ekler."""
    return crud.create_daily_active_employee(db, daily_in, "admin")


@app.delete("/daily-active-employees/{employee_id}", tags=["Günlük Aktif Personel"])
def delete_daily_active_employee_endpoint(
    employee_id: int, date: date, db: DbSession
):
    """Günlük aktif personeli siler."""
    crud.delete_daily_active_employee(db, employee_id, date)
    return {"message": "Personel aktif listeden kaldırıldı"}


@app.get("/active-employees-for-break-tracking", tags=["Mola Takibi"])
def get_active_employees_for_break_tracking_endpoint(date: date, db: DbSession):
    """Mola takibi için aktif personelleri getirir."""
    employees = crud.get_active_employees_for_break_tracking(db, date)
    return [
        {
            "id": emp.id,
            "employee_code": emp.employee_code,
            "full_name": emp.full_name,
            "is_on_break": emp.is_on_break,
            "break_start_time": emp.break_start_time,
            "break_duration_minutes": emp.break_duration_minutes,
            "kullanilan_mola": emp.kullanilan_mola,
        }
        for emp in employees
    ]


# ---------------------------------------------------------------------------
# Frontend (PWA) — Statik Dosya Sunumu
# ---------------------------------------------------------------------------

_frontend_dir = Path(__file__).resolve().parent.parent

# Render için özel statik dosya serving
from fastapi.responses import FileResponse
from fastapi import Request

@app.get("/{full_path:path}")
async def serve_static(full_path: str):
    file_path = _frontend_dir / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    # Dosya yoksa index.html döndür (SPA routing için)
    return FileResponse(_frontend_dir / "index.html")

@app.get("/")
async def serve_index():
    return FileResponse(_frontend_dir / "index.html")


# ---------------------------------------------------------------------------
# Seed Endpoint (Sadece geliştirme için - production'da kaldırılmalı)
# ---------------------------------------------------------------------------

@app.get("/seed-departments")
def seed_departments_endpoint(db: DbSession):
    """Departmanları ve personelleri seed eder."""
    from app.models import Department, Employee
    from app.auth import hash_password
    
    # Mevcut departmanları kontrol et
    existing_departments = db.query(Department).all()
    if existing_departments:
        return {"message": "Departmanlar zaten var", "count": len(existing_departments)}
    
    departments_data = [
        {
            "name": "Ana Mutfak / Ekip Programı",
            "description": "Ana mutfak ve ekip programı personeli",
            "employees": [
                "SEYFETTİN K.", "YAVUZ AKKAYA", "BURCU K.", "DAMLA KARATAŞ", "BEREN ALTUN",
                "BEYZA AYAZ", "KAĞAN KONAKCI", "ŞAHİNDE DELER", "ONURCAN DEMİREZEN",
                "YASİN MERT", "FURKAN BAYRAM", "ÖMER FARUK FARAŞ", "AYSEL Ç.",
                "HAYRETTİN G. (GENÇ)", "ESMA KEREM (GENÇ)", "EREN D. (GENÇ)", "RABİA KARA (GENÇ) PART"
            ]
        },
        {
            "name": "GEL",
            "description": "GEL grubu personeli",
            "employees": ["GÜLAY S.", "HANİFE T."]
        },
        {
            "name": "BARİSTA",
            "description": "Barista grubu personeli",
            "employees": ["ESMA OĞUZKAYA", "NURSENA AY (GENÇ İŞÇİ)", "MERCAN E. (PART)", "SEMANUR D."]
        },
        {
            "name": "MASAYA SERVİS TENT-LOBİ",
            "description": "Masa servisi ve tent-lobi personeli",
            "employees": ["NECLA", "ESMA A."]
        }
    ]
    
    for dept_data in departments_data:
        department = Department(
            name=dept_data["name"],
            description=dept_data["description"],
            is_active=True
        )
        db.add(department)
        db.flush()
        
        for employee_name in dept_data["employees"]:
            employee_code = employee_name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace(".", "")
            employee = Employee(
                full_name=employee_name,
                employee_code=employee_code,
                department_id=department.id,
                is_active=True,
                is_on_break=False,
                password_hash=hash_password("123456")
            )
            db.add(employee)
    
    db.commit()
    return {"message": "Seed tamamlandı", "departments": len(departments_data)}

