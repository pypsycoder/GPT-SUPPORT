#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from app.models import Base

print(f"Total tables in Base.metadata: {len(Base.metadata.tables)}")
for t in sorted(Base.metadata.tables.values(), key=lambda x: x.schema or ""):
    schema = t.schema or "public"
    print(f"  {schema}.{t.name}")
