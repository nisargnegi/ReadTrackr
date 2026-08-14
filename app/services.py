import csv, io, json, re
from datetime import datetime
import httpx
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from .models import Book, UserBook
from .config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL, GOOGLE_BOOKS_API_KEY

NO_COVER_SENTINEL = "__readtrackr_no_cover__"

def clean(value): return (value or "").strip()
def norm(value): return re.sub(r"[^a-z0-9]", "", clean(value).lower())
def rating_value(value):
    try:
        rating = int(float(clean(value)))
        return rating if 1 <= rating <= 5 else None
    except ValueError:
        return None
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
        entry.rating = rating_value(row.get("My Rating"))
        shelves = clean(row.get("Exclusive Shelf"))
        entry.status = {"read":"read", "currently-reading":"currently_reading", "to-read":"want_to_read"}.get(shelves, "want_to_read")
        entry.date_added, entry.date_read = date_value(row.get("Date Added")), date_value(row.get("Date Read"))
        entry.review, entry.private_notes = clean(row.get("My Review")) or None, clean(row.get("Private Notes")) or None
        entry.goodreads_book_id, entry.goodreads_shelves = clean(row.get("Book Id")) or None, clean(row.get("Bookshelves")) or None
        entry.read_count = int(row.get("Read Count") or 0) if clean(row.get("Read Count")).isdigit() else 0
        entry.source = "goodreads"
        summary["added" if created else "updated"] += 1
    return summary

def google_lookup(book: Book):
    query = f"isbn:{book.isbn13 or book.isbn10}" if book.isbn13 or book.isbn10 else f'intitle:"{book.title}" inauthor:"{book.authors}"'
    params = {"q": query, "maxResults": 1, "printType": "books"}
    if GOOGLE_BOOKS_API_KEY: params["key"] = GOOGLE_BOOKS_API_KEY
    response = httpx.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=10)
    response.raise_for_status(); items = response.json().get("items", [])
    if not items: return False
    item, info = items[0], items[0].get("volumeInfo", {})
    images = info.get("imageLinks", {}); thumbnail = images.get("thumbnail") or images.get("smallThumbnail")
    book.google_books_id = item.get("id"); book.title = info.get("title") or book.title
    book.subtitle = info.get("subtitle"); book.authors = ", ".join(info.get("authors", [])) or book.authors
    book.description = info.get("description"); book.thumbnail_url = thumbnail.replace("http://", "https://") if thumbnail else book.thumbnail_url
    book.published_date = info.get("publishedDate"); book.publisher = info.get("publisher")
    book.page_count = info.get("pageCount"); book.categories = ", ".join(info.get("categories", [])) or None
    book.language = info.get("language"); book.preview_link = info.get("previewLink")
    for identifier in info.get("industryIdentifiers", []):
        if identifier.get("type") == "ISBN_13": book.isbn13 = identifier.get("identifier")
        if identifier.get("type") == "ISBN_10": book.isbn10 = identifier.get("identifier")
    return True

def open_library_cover(book: Book):
    """Find a cover through Open Library when Google Books has none."""
    identifier = book.isbn13 or book.isbn10
    if identifier:
        cover_url = f"https://covers.openlibrary.org/b/isbn/{identifier}-M.jpg?default=false"
        response = httpx.get(cover_url, timeout=10, follow_redirects=True)
        if response.status_code == 200 and response.headers.get("content-type", "").startswith("image/"):
            book.thumbnail_url = cover_url
            return True
    params = {"title": book.title, "author": book.authors, "limit": 1, "fields": "cover_i"}
    response = httpx.get("https://openlibrary.org/search.json", params=params, timeout=10)
    response.raise_for_status()
    cover_id = next((item.get("cover_i") for item in response.json().get("docs", []) if item.get("cover_i")), None)
    if not cover_id:
        return False
    book.thumbnail_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
    return True

def refresh_metadata(db: Session, limit: int = 25):
    books = db.query(Book).filter(Book.thumbnail_url.is_(None), or_(Book.google_books_id.is_(None), Book.google_books_id != NO_COVER_SENTINEL)).order_by(Book.id).limit(limit).all()
    summary = {"checked": len(books), "updated": 0, "not_found": 0, "errors": 0}
    for book in books:
        try:
            google_lookup(book)
            if not book.thumbnail_url:
                open_library_cover(book)
            if book.thumbnail_url:
                summary["updated"] += 1
            else:
                book.google_books_id = NO_COVER_SENTINEL
                summary["not_found"] += 1
        except httpx.HTTPError: summary["errors"] += 1
    db.commit(); return summary

def deepseek_rank(profile, candidates):
    if not DEEPSEEK_API_KEY: raise ValueError("Add DEEPSEEK_API_KEY in GitHub Actions secrets, then deploy before refreshing recommendations.")
    prompt = {"profile": profile, "candidates": candidates, "instruction": "Return JSON only with a recommendations array of up to 24 diverse recommendations, ordered strongest first. Use public_rating and ratings_count as quality signals, but prioritize fit to the profile. Detect series even when a series hint is not explicit: for any series, return at most one title. Return its highest public-rated title only if it is the first book or clearly works as a standalone; otherwise omit that series. Do not invent books. Every result must have title, author, score (0-1), reason (spoiler-free, max two sentences), and matched_preferences (array)."}
    response = httpx.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, json={"model": DEEPSEEK_MODEL, "messages": [{"role":"system","content":"You are a careful book recommendation engine. Respond with valid JSON."}, {"role":"user","content":json.dumps(prompt)}], "response_format":{"type":"json_object"}, "max_tokens":4000}, timeout=60)
    response.raise_for_status(); return json.loads(response.json()["choices"][0]["message"]["content"]).get("recommendations", [])

def google_candidates(authors, excluded_titles):
    return google_candidates_for_profile(authors, [], excluded_titles)

def series_hint(title):
    """Extract a conservative series label and number from common book-title forms."""
    match = re.search(r"\(([^()]+?)(?:,|\s)(?:book\s*)?#\s*(\d+)\)", title, re.I)
    if not match:
        return None, None
    return norm(match.group(1)), int(match.group(2))

def filter_series_candidates(candidates):
    """Keep one safe candidate per detected series before the AI ranking call."""
    standalone, series = [], {}
    for candidate in candidates:
        key, number = series_hint(candidate["title"])
        if not key:
            standalone.append(candidate); continue
        series.setdefault(key, []).append((number, candidate))
    for entries in series.values():
        best_number, best = max(entries, key=lambda pair: (pair[1].get("public_rating") or 0, pair[1].get("ratings_count") or 0))
        # A later volume can be a good book, but is not a safe starting point for a new reader.
        if best_number == 1:
            standalone.append(best)
    return standalone

def google_candidates_for_profile(authors, categories, excluded_titles):
    candidates, seen = [], set()
    queries = [(f'inauthor:"{author}"', 20) for author in authors[:5]] + [(f'subject:"{category}"', 12) for category in categories[:4]]
    for query, max_results in queries:
        params = {"q": query, "maxResults": max_results, "printType": "books"}
        if GOOGLE_BOOKS_API_KEY: params["key"] = GOOGLE_BOOKS_API_KEY
        try:
            items = httpx.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=10).json().get("items", [])
        except (httpx.HTTPError, ValueError): continue
        for item in items:
            info = item.get("volumeInfo", {}); title = info.get("title", ""); candidate_author = ", ".join(info.get("authors", []))
            key = norm(title)
            if not title or key in seen or key in excluded_titles: continue
            seen.add(key); candidates.append({"google_books_id":item.get("id"), "title":title, "author":candidate_author, "thumbnail_url":(info.get("imageLinks", {}).get("thumbnail") or "").replace("http://", "https://"), "categories":info.get("categories", []), "description":info.get("description", "")[:700], "published_date":info.get("publishedDate"), "page_count":info.get("pageCount")})
            candidates[-1]["public_rating"] = info.get("averageRating")
            candidates[-1]["ratings_count"] = info.get("ratingsCount", 0)
    return filter_series_candidates(candidates)[:80]
