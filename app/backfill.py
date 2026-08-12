"""Run manually inside the ReadTrackr container to fetch missing Google Books metadata."""
import argparse

from .database import Base, SessionLocal, engine
from .models import Book
from .services import google_lookup

def main():
    parser = argparse.ArgumentParser(description="Backfill missing book covers and metadata.")
    parser.add_argument("--all", action="store_true", help="Process every book currently missing a cover.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum books to process (default: 25).")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    books = db.query(Book).filter(Book.thumbnail_url.is_(None)).order_by(Book.id).all() if args.all else db.query(Book).filter(Book.thumbnail_url.is_(None)).order_by(Book.id).limit(args.limit).all()
    totals = {"checked": len(books), "updated": 0, "not_found": 0, "errors": 0}
    try:
        for index, book in enumerate(books, 1):
            try:
                if google_lookup(book): totals["updated"] += 1
                else: totals["not_found"] += 1
            except Exception as exc:
                totals["errors"] += 1
                print(f"[{index}/{len(books)}] {book.title}: {exc}")
            if index % 10 == 0: db.commit(); print(f"Processed {index}/{len(books)}")
        db.commit()
    finally:
        db.close()
    print("Complete: " + ", ".join(f"{key}={value}" for key, value in totals.items()))

if __name__ == "__main__":
    main()
