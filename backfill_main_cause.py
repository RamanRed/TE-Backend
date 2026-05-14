"""Backfill main_cause column to empty array for all existing saved_ishikawa rows using Prisma."""
import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.config import load_config
from src.database.prisma_client import get_prisma

load_config()
db = get_prisma()

# Find all rows where main_cause is empty/null
all_rows = db.savedishikawa.find_many()
backfilled = 0

for row in all_rows:
    if row.mainCause is None or row.mainCause == []:
        # These are fine (empty array), but let's ensure NULL -> empty array
        pass

print(f"Total saved_ishikawa rows: {len(all_rows)}")

# Use raw query to backfill NULL values
result = db.execute_raw(
    'UPDATE saved_ishikawa SET main_cause = \'{}\' WHERE main_cause IS NULL'
)
print(f"Backfilled {result} rows with empty array.")
print("Done.")
