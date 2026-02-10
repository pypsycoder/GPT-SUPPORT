#!/usr/bin/env python3
"""Analyze Alembic revision chain"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Read all migration files
versions_dir = project_root / "alembic" / "versions"

migrations = {}
for py_file in versions_dir.glob("*.py"):
    if py_file.name.startswith("__"):
        continue
    
    content = py_file.read_text()
    
    # Extract revision ID
    for line in content.split("\n"):
        if line.startswith("revision: str"):
            # правая часть после '='
            right = line.split("=", 1)[1].strip()
            # убираем возможные кавычки и пробелы
            rev_id = right.strip().strip("'\"")
            break
    else:
        continue
        
    # Extract down_revision
    for line in content.split('\n'):
        if line.startswith("down_revision:"):
            # Handle both single and multiple parents
            if '(' in line:
                # Multiple parents: ('86a0d2c1f8e3', 'a515d149cfa3')
                down_rev = line.split('=')[1].strip()
            else:
                down_rev = line.split('=')[1].strip().strip("'\"")
            break
    else:
        down_rev = None
    
    # Extract docstring
    doc = content.split('"""')[1].split('\n')[0]
    
    migrations[rev_id] = {
        'doc': doc,
        'down_revision': down_rev,
        'file': py_file.name
    }

print("\n=== Migration Chain Analysis ===\n")

for rev_id, info in sorted(migrations.items()):
    print(f"{rev_id}: {info['doc']}")
    print(f"  down_revision: {info['down_revision']}")
    print(f"  file: {info['file']}\n")

print("\n=== Finding Issues ===\n")

# Find branches (multiple parents)
for rev_id, info in migrations.items():
    down = info['down_revision']
    if down and ('(' in str(down) or ',' in str(down)):
        print(f"⚠️  BRANCH POINT: {rev_id}")
        print(f"   Has multiple parents: {down}\n")

# Find overlaps
for rev_id, info in migrations.items():
    down = info['down_revision']
    if down and '(' in str(down):
        # Extract all parents
        parents_str = str(down).strip('()')
        parents = [p.strip().strip("'\"") for p in parents_str.split(',')]
        print(f"❌ CONFLICT: {rev_id} has {len(parents)} parents:")
        for p in parents:
            if p in migrations:
                print(f"   - {p}: {migrations[p]['doc']}")
        print()
