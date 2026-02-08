#!/usr/bin/env python3
"""Check and display alembic versions in database"""

from sqlalchemy import text, create_engine
from core.db.engine import DATABASE_URL

def check_versions():
    """Display all alembic versions in database"""
    sync_url = DATABASE_URL.replace('asyncpg', 'psycopg')
    engine = create_engine(sync_url)
    
    try:
        with engine.connect() as conn:
            print("\n=== Alembic Versions in Database ===\n")
            result = conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
            versions = result.fetchall()
            for v in versions:
                print(f"  {v[0]}")
            
            print(f"\nTotal: {len(versions)} versions\n")
            
            # Check for problematic versions
            problematic = ['f1a2b3c4d5e6', '3d3b0b2c7bf8', 'd2f20e5011be']
            print("=== Status of Key Versions ===\n")
            for p in problematic:
                has_it = any(v[0] == p for v in versions)
                status = "✅ Present" if has_it else "❌ Missing"
                print(f"  {p}: {status}")
                
    finally:
        engine.dispose()

if __name__ == "__main__":
    check_versions()
