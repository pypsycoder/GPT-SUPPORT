#!/usr/bin/env python3
"""Check migration heads and status"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic.script import ScriptDirectory

def main():
    alembic_config = Config(str(project_root / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_config)
    
    print("\n=== Migration Heads ===")
    heads = script.get_heads()
    for head in heads:
        print(f"  {head}")
    
    print(f"\nTotal heads: {len(heads)}")
    
    if len(heads) > 1:
        print("\n⚠️  WARNING: Multiple heads detected!")
        print("     Run: alembic upgrade heads")
    elif len(heads) == 1:
        print("\n✅ Single head found - ready for upgrade")
    else:
        print("\n❌ ERROR: No heads found")
    
    print("\n=== All Revisions ===")
    for rev in script.walk_revisions():
        parents = rev.down_revision if isinstance(rev.down_revision, (list, tuple)) else [rev.down_revision] if rev.down_revision else []
        print(f"  {rev.revision}: {rev.doc.split(chr(10))[0] if rev.doc else 'no doc'}")
        if parents and parents[0]:
            print(f"    └── parents: {', '.join(str(p) for p in parents if p)}")

if __name__ == "__main__":
    main()
