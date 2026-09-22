"""
TURTU HRMS: Storage Provider Migration Utility
Allows zero-downtime migration of all avatars and documents between any storage providers:
Local Disk <-> Google Drive <-> Supabase Storage <-> Cloudflare R2 <-> AWS S3.

Usage:
    python migrate_storage.py --from local --to supabase
    python migrate_storage.py --from local --to cloudflare
    python migrate_storage.py --from gdrive --to s3
"""

import os
import sys
import argparse

# Force UTF-8 for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.models.employee import EmployeeProfile
from app.models.document import EmployeeDocument
from app.services.storage import get_storage_provider


def migrate_storage(source_name: str, target_name: str):
    print("=" * 65)
    print(f"📦 TURTU HRMS STORAGE MIGRATION: [{source_name.upper()}] ➔ [{target_name.upper()}]")
    print("=" * 65)

    source_provider = get_storage_provider(source_name)
    target_provider = get_storage_provider(target_name)

    print(f" • Source Provider: {source_provider.__class__.__name__}")
    print(f" • Target Provider: {target_provider.__class__.__name__}")

    db = SessionLocal()
    try:
        # 1. Migrate Employee Profile Avatars
        print("\n[1] Migrating Employee Avatars...")
        profiles = db.query(EmployeeProfile).filter(EmployeeProfile.photo_file_id.isnot(None)).all()
        avatar_count = 0
        for p in profiles:
            if not p.photo_file_id:
                continue
            file_bytes = source_provider.get_file_bytes(p.photo_file_id)
            if file_bytes:
                filename = os.path.basename(p.photo_file_id) or "avatar.jpg"
                new_url, new_id = target_provider.upload_file(
                    file_bytes, filename=filename, content_type="image/jpeg", folder="avatars"
                )
                p.avatar_url = new_url
                p.photo_file_id = new_id
                avatar_count += 1
                print(f"   ✅ Migrated Avatar for Employee ID {p.employee_id} -> {new_url}")
            else:
                print(f"   ⚠️ Could not read source file for Employee ID {p.employee_id}: {p.photo_file_id}")

        # 2. Migrate Employee Documents
        print("\n[2] Migrating Employee Documents & KYC PDFs...")
        docs = db.query(EmployeeDocument).all()
        doc_count = 0
        for d in docs:
            if not d.file_url:
                continue
            file_bytes = source_provider.get_file_bytes(d.file_url)
            if file_bytes:
                filename = d.file_name or "document.pdf"
                new_url, new_id = target_provider.upload_file(
                    file_bytes, filename=filename, content_type=d.mime_type or "application/pdf", folder="documents"
                )
                d.file_url = new_url
                doc_count += 1
                print(f"   ✅ Migrated Document #{d.id} ({d.title}) -> {new_url}")
            else:
                print(f"   ⚠️ Could not read source document #{d.id}: {d.file_url}")

        db.commit()
        print("\n" + "=" * 65)
        print(f"🎉 MIGRATION COMPLETE! Migrated {avatar_count} avatars and {doc_count} documents successfully.")
        print(f"👉 Remember to update STORAGE_PROVIDER={target_name} in your .env file!")
        print("=" * 65)

    except Exception as e:
        db.rollback()
        print(f"\n❌ MIGRATION FAILED: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate HRMS storage between cloud providers.")
    parser.add_argument("--from", dest="source", required=True, help="Source provider (local, gdrive, supabase, cloudflare, s3)")
    parser.add_argument("--to", dest="target", required=True, help="Target provider (local, gdrive, supabase, cloudflare, s3)")
    args = parser.parse_args()

    migrate_storage(args.source, args.target)
