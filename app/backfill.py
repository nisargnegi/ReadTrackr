"""Run manually inside the ReadTrackr container to fetch missing Google Books metadata."""
import argparse

from .database import Base, SessionLocal, engine
from .models import Book
from .services import refresh_metadata

def main():
    parser = argparse.ArgumentParser(description="Backfill missing book covers and metadata.")
    parser.add_argument("--all", action="store_true", help="Process every book currently missing a cover.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum books to process (default: 25).")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.all:
            totals = {"checked": 0, "updated": 0, "not_found": 0, "errors": 0}
            while True:
                result = refresh_metadata(db, 25)
                for key in totals: totals[key] += result[key]
                if result["checked"] < 25: break
                print(f"Processed {totals['checked']} books")
        else:
            totals = refresh_metadata(db, args.limit)
    finally:
        db.close()
    print("Complete: " + ", ".join(f"{key}={value}" for key, value in totals.items()))

if __name__ == "__main__":
    main()
