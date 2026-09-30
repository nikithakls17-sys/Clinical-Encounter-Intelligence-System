"""Re-evaluate anomaly rules for all patients.

Usage (from backend/):
    python -m app.rules.run
"""

from sqlalchemy.orm import Session

from app.db import engine
from app.rules.engine import run_rules

if __name__ == "__main__":
    with Session(engine) as session:
        r = run_rules(session)
    print(f"flags created={r.created} updated={r.updated} auto_resolved={r.auto_resolved}")
