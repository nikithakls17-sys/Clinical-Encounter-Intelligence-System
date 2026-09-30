"""Run extraction on every pending encounter.

Usage (from backend/):
    python -m app.ai.extract_all            # all pending encounters
    python -m app.ai.extract_all --limit 3
"""

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.ai.deps import get_retriever
from app.ai.extraction import extract_encounter
from app.ai.llm import OpenAIChat
from app.db import engine


def main(limit: int | None) -> None:
    llm, retriever = OpenAIChat(), get_retriever()
    with Session(engine) as session:
        pending = session.scalars(
            select(models.Encounter)
            .where(models.Encounter.status == models.EncounterStatus.PENDING)
            .order_by(models.Encounter.id)
            .limit(limit)
        ).all()
        for e in pending:
            try:
                s = extract_encounter(session, e, llm, retriever)
            except Exception as exc:
                print(f"encounter {e.id}: FAILED {type(exc).__name__}: {exc}")
                continue
            result = s.error or f"{len(s.entities)} entities"
            print(f"encounter {e.id}: suggestion {s.id}, {result}, {s.latency_ms} ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int)
    main(parser.parse_args().limit)
