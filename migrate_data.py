#!/usr/bin/env python3
"""
Data Migration Script

This script migrates existing JSON data to the new database schema.
Run this after setting up the database with Alembic migrations.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from models import SessionLocal, Operator, Machine, SystemLog
from sqlalchemy.orm import Session

def migrate_operators(db: Session):
    """Migrate operators from JSON to database."""
    operators_file = Path(__file__).resolve().parent / "data" / "operators.json"

    if not operators_file.exists():
        print("Operators file not found, skipping...")
        return

    with open(operators_file, "r", encoding="utf-8") as f:
        operators_data = json.load(f)

    migrated_count = 0
    for op_data in operators_data:
        # Check if operator already exists
        existing = db.query(Operator).filter_by(phone=op_data["phone"]).first()
        if existing:
            print(f"Operator {op_data['phone']} already exists, skipping...")
            continue

        operator = Operator(
            name=op_data["name"],
            phone=op_data["phone"],
            role="operator",
            is_active=True
        )
        db.add(operator)
        migrated_count += 1

    db.commit()
    print(f"Migrated {migrated_count} operators")

def migrate_machines(db: Session):
    """Migrate machines from Excel or create sample data."""
    # For now, create some sample machines since Excel parsing is complex
    sample_machines = [
        {
            "id": "M001",
            "type": "Excavator",
            "status": "normal",
            "operator_phone": "+919876543210",
            "location": "Site A"
        },
        {
            "id": "M002",
            "type": "Bulldozer",
            "status": "maintenance",
            "operator_phone": "+916381528758",
            "location": "Site B"
        },
        {
            "id": "M003",
            "type": "Crane",
            "status": "normal",
            "operator_phone": "+919876543210",
            "location": "Site C"
        }
    ]

    migrated_count = 0
    for machine_data in sample_machines:
        # Check if machine already exists
        existing = db.query(Machine).filter_by(id=machine_data["id"]).first()
        if existing:
            print(f"Machine {machine_data['id']} already exists, skipping...")
            continue

        machine = Machine(
            id=machine_data["id"],
            type=machine_data["type"],
            status=machine_data["status"],
            operator_phone=machine_data["operator_phone"],
            location=machine_data["location"]
        )
        db.add(machine)
        migrated_count += 1

    db.commit()
    print(f"Migrated {migrated_count} machines")

def create_initial_logs(db: Session):
    """Create initial system logs."""
    log_entries = [
        {
            "level": "INFO",
            "message": "Database migration completed",
            "module": "migration",
            "function": "migrate_data"
        },
        {
            "level": "INFO",
            "message": "System initialized with sample data",
            "module": "migration",
            "function": "create_initial_logs"
        }
    ]

    for log_data in log_entries:
        log_entry = SystemLog(
            level=log_data["level"],
            message=log_data["message"],
            module=log_data["module"],
            function=log_data["function"]
        )
        db.add(log_entry)

    db.commit()
    print("Created initial system logs")

def main():
    """Main migration function."""
    print("Starting data migration...")

    db = SessionLocal()
    try:
        migrate_operators(db)
        migrate_machines(db)
        create_initial_logs(db)

        print("Data migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()