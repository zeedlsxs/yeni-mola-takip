"""
Seed script for departments and employees.

This script adds the predefined departments and employees to the database.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, init_db
from app.models import Department, Employee
from app.auth import hash_password


def seed_departments_and_employees():
    """Seed departments and employees to the database."""
    db = SessionLocal()
    
    try:
        # Check if departments already exist
        existing_departments = db.query(Department).all()
        if existing_departments:
            print(f"Found {len(existing_departments)} existing departments. Skipping seed.")
            return
        
        # Define departments and their employees
        departments_data = [
            {
                "name": "Ana Mutfak / Ekip Programı",
                "description": "Ana mutfak ve ekip programı personeli",
                "employees": [
                    "SEYFETTİN K.",
                    "YAVUZ AKKAYA",
                    "BURCU K.",
                    "DAMLA KARATAŞ",
                    "BEREN ALTUN",
                    "BEYZA AYAZ",
                    "KAĞAN KONAKCI",
                    "ŞAHİNDE DELER",
                    "ONURCAN DEMİREZEN",
                    "YASİN MERT",
                    "FURKAN BAYRAM",
                    "ÖMER FARUK FARAŞ",
                    "AYSEL Ç.",
                    "HAYRETTİN G. (GENÇ)",
                    "ESMA KEREM (GENÇ)",
                    "EREN D. (GENÇ)",
                    "RABİA KARA (GENÇ) PART"
                ]
            },
            {
                "name": "GEL",
                "description": "GEL grubu personeli",
                "employees": [
                    "GÜLAY S.",
                    "HANİFE T."
                ]
            },
            {
                "name": "BARİSTA",
                "description": "Barista grubu personeli",
                "employees": [
                    "ESMA OĞUZKAYA",
                    "NURSENA AY (GENÇ İŞÇİ)",
                    "MERCAN E. (PART)",
                    "SEMANUR D."
                ]
            },
            {
                "name": "MASAYA SERVİS TENT-LOBİ",
                "description": "Masa servisi ve tent-lobi personeli",
                "employees": [
                    "NECLA",
                    "ESMA A."
                ]
            }
        ]
        
        # Add departments and employees
        for dept_data in departments_data:
            # Create department
            department = Department(
                name=dept_data["name"],
                description=dept_data["description"],
                is_active=True
            )
            db.add(department)
            db.flush()  # Get the department ID
            
            print(f"Created department: {department.name}")
            
            # Create employees for this department
            for employee_name in dept_data["employees"]:
                # Generate employee code from name
                employee_code = employee_name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace(".", "")
                
                employee = Employee(
                    full_name=employee_name,
                    employee_code=employee_code,
                    department_id=department.id,
                    is_active=True,
                    is_on_break=False,
                    password_hash=hash_password("123456")  # Default password
                )
                db.add(employee)
                print(f"  - Added employee: {employee_name}")
        
        db.commit()
        print("\nSeed completed successfully!")
        print(f"  - {len(departments_data)} departments created")
        print(f"  - Total employees: {sum(len(d['employees']) for d in departments_data)}")
        
    except Exception as e:
        db.rollback()
        print(f"Error during seed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Seed data
    seed_departments_and_employees()
