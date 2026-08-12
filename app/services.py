import csv, io, re
from datetime import datetime
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from .models import Book, UserBook

def clean(value): return (value or "").strip()
def norm(value): return re.sub(r"[^a-z0-9]", "", clean(value).lower())
def date_value(value):
    value = clean(value)
    for pattern in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
        try: return datetime.strptime(value, pattern).date()
        except ValueError: pass
    return None
def find_book(db: Session, isbn13, isbn10, title, authors):
    if isbn13:
        found = db.scalar(db.select(Book).where(Book.isbn13 == isbn13)) if False else None
    query = db.query(Book)
    if isbn13:
        found = query.filter(Book.isbn13 == isbn13).first()
        if found: return found
    if isbn10:
        found = query.filter(Book.isbn10 == isbn10).first()
        if found: return found
    return query.filter(func.lower(Book.title) == clean(title).lower(), func.lower(Book.authors) == clean(authors).lower()).first()
def import_goodreads(db: Session, contents: bytes):
    reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig", errors="replace")))
    summary = {"added": 0, "updated": 0, "skipped": 0, "possible_duplicates": 0}
    for row in reader:
        title, authors = clean(row.get("Title")), clean(row.get("Author"))
        if not title: summary["skipped"] += 1; continue
        isbn13 = clean(row.get("ISBN13")).strip('="')
        isbn10 = clean(row.get("ISBN")).strip('="')
        book = find_book(db, isbn13, isbn10, title, authors)
        created = book is None
        if created:
            book = Book(title=title, authors=authors, isbn13=isbn13 or None, isbn10=isbn10 or None)
            db.add(book); db.flush()
        entry = book.entry
        if not entry:
            entry = UserBook(book_id=book.id); db.add(entry)
        rating = clean(row.get("My Rating"))
        entry.rating = int(rating) if rating.isdigit() and 1 <= int(rating) <= 5 else None
        shelves = clean(row.get("Exclusive Shelf"))
        entry.status = {"read":"read", "currently-reading":"currently_reading", "to-read":"want_to_read"}.get(shelves, "want_to_read")
        entry.date_added, entry.date_read = date_value(row.get("Date Added")), date_value(row.get("Date Read"))
        entry.review, entry.private_notes = clean(row.get("My Review")) or None, clean(row.get("Private Notes")) or None
        entry.goodreads_book_id, entry.goodreads_shelves = clean(row.get("Book Id")) or None, clean(row.get("Bookshelves")) or None
        entry.read_count = int(row.get("Read Count") or 0) if clean(row.get("Read Count")).isdigit() else 0
        entry.source = "goodreads"
        summary["added" if created else "updated"] += 1
    return summary
