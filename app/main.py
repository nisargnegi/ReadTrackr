import csv, io, json, time
from datetime import datetime, time as clock_time
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware
from .auth import verify_password
from .config import APP_PASSWORD_HASH, APP_USERNAME, DATA_DIR, SESSION_SECRET
from .database import Base, engine, get_db
from .models import Book, Recommendation, RecommendationBatch, UserBook
from .services import deepseek_rank, google_candidates_for_profile, import_goodreads, refresh_metadata
from .views import environment
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
IMPORT_STAGING_FILE = Path(DATA_DIR) / ".goodreads-import-preview.csv"
Base.metadata.create_all(bind=engine)
app = FastAPI(title="ReadTrackr")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=False, same_site="lax")
attempts = {}
def user(request: Request):
    if request.session.get("user") != APP_USERNAME: raise HTTPException(401)
def render(request, name, **context): return HTMLResponse(environment.get_template(name).render(request=request, **context))
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
@app.get("/health")
def health(): return {"status": "ok"}
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request): return render(request, "login.html")
@app.post("/login")
def login(request: Request, username: str = Form(), password: str = Form()):
    key = request.client.host if request.client else "unknown"; now = time.time(); history = [t for t in attempts.get(key, []) if now-t < 300]; attempts[key] = history
    if len(history) >= 8 or username != APP_USERNAME or not verify_password(password, APP_PASSWORD_HASH):
        history.append(now); return render(request, "login.html", error="Invalid credentials or too many attempts.")
    request.session["user"] = APP_USERNAME; return RedirectResponse("/", 303)
@app.post("/logout")
def logout(request: Request): request.session.clear(); return RedirectResponse("/login", 303)
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user(request); entries = db.query(UserBook).options(joinedload(UserBook.book)).all(); current = [e for e in entries if e.status == "currently_reading"]
    def recent_key(entry):
        return datetime.combine(entry.date_read, clock_time.min) if entry.date_read else entry.updated_at
    recent = sorted([e for e in entries if e.status == "read"], key=recent_key, reverse=True)[:6]
    return render(request, "dashboard.html", entries=entries, current=current, recent=recent)
@app.get("/library", response_class=HTMLResponse)
def library(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db)):
    user(request); query = db.query(UserBook).options(joinedload(UserBook.book))
    if status: query = query.filter(UserBook.status == status)
    if q: query = query.join(Book).filter((Book.title.ilike(f"%{q}%")) | (Book.authors.ilike(f"%{q}%")))
    return render(request, "library.html", entries=query.order_by(UserBook.updated_at.desc()).all(), q=q, selected=status)
@app.get("/books/new", response_class=HTMLResponse)
def new_book(request: Request): user(request); return render(request, "book_form.html", book=None, entry=None)
@app.post("/books/new")
def create_book(request: Request, title: str = Form(), authors: str = Form(""), status: str = Form("want_to_read"), rating: str = Form(""), db: Session = Depends(get_db)):
    user(request); book=Book(title=title.strip(), authors=authors.strip()); db.add(book); db.flush(); db.add(UserBook(book_id=book.id,status=status,rating=int(rating) if rating.isdigit() else None)); db.commit(); return RedirectResponse(f"/books/{book.id}",303)
@app.get("/books/{book_id}", response_class=HTMLResponse)
def book_detail(book_id: int, request: Request, db: Session = Depends(get_db)):
    user(request); book=db.query(Book).options(joinedload(Book.entry)).get(book_id)
    if not book: raise HTTPException(404)
    return render(request,"book.html",book=book,entry=book.entry)
@app.post("/books/{book_id}")
def update_book(book_id:int, request:Request, status:str=Form(), rating:str=Form(""), notes:str=Form(""), db:Session=Depends(get_db)):
    user(request); book=db.get(Book,book_id)
    if not book or not book.entry: raise HTTPException(404)
    book.entry.status=status; book.entry.rating=int(rating) if rating.isdigit() else None; book.entry.private_notes=notes or None; db.commit(); return RedirectResponse(f"/books/{book_id}",303)
@app.get("/import",response_class=HTMLResponse)
def import_page(request:Request): user(request); return render(request,"import.html")
@app.post("/import/preview",response_class=HTMLResponse)
async def import_preview(request:Request,csv_file:UploadFile=File()):
    user(request); data=await csv_file.read(); rows=list(csv.DictReader(io.StringIO(data.decode("utf-8-sig",errors="replace")))); IMPORT_STAGING_FILE.write_bytes(data); return render(request,"import.html",preview=rows[:8],total=len(rows))
@app.post("/import/commit",response_class=HTMLResponse)
def import_commit(request:Request,db:Session=Depends(get_db)):
    user(request); contents=IMPORT_STAGING_FILE.read_bytes() if IMPORT_STAGING_FILE.exists() else b""
    if not contents: return RedirectResponse("/import",303)
    summary=import_goodreads(db,contents); db.commit(); IMPORT_STAGING_FILE.unlink(missing_ok=True); return render(request,"import.html",summary=summary)
@app.get("/export/{format}")
def export_library(format:str,request:Request,db:Session=Depends(get_db)):
    user(request); records=[{"title":e.book.title,"authors":e.book.authors,"status":e.status,"rating":e.rating,"notes":e.private_notes,"date_read":str(e.date_read or "")} for e in db.query(UserBook).options(joinedload(UserBook.book)).all()]
    if format=="json": return Response(json.dumps(records,indent=2),media_type="application/json",headers={"Content-Disposition":"attachment; filename=readtrackr.json"})
    if format=="csv":
        out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=["title","authors","status","rating","notes","date_read"]); writer.writeheader(); writer.writerows(records); return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=readtrackr.csv"})
    raise HTTPException(404)
@app.get("/metadata", response_class=HTMLResponse)
def metadata_page(request: Request, db: Session = Depends(get_db)):
    user(request); total_missing = db.query(Book).filter(Book.thumbnail_url.is_(None)).count(); missing = db.query(Book).filter(Book.thumbnail_url.is_(None), Book.google_books_id != "__readtrackr_no_cover__").count() + db.query(Book).filter(Book.thumbnail_url.is_(None), Book.google_books_id.is_(None)).count()
    return render(request, "metadata.html", missing=missing, unavailable=total_missing-missing)
@app.post("/metadata/refresh", response_class=HTMLResponse)
def metadata_refresh(request: Request, db: Session = Depends(get_db)):
    user(request); summary = refresh_metadata(db)
    total_missing = db.query(Book).filter(Book.thumbnail_url.is_(None)).count(); missing = db.query(Book).filter(Book.thumbnail_url.is_(None), Book.google_books_id != "__readtrackr_no_cover__").count() + db.query(Book).filter(Book.thumbnail_url.is_(None), Book.google_books_id.is_(None)).count()
    return render(request, "metadata.html", missing=missing, unavailable=total_missing-missing, summary=summary)
@app.get("/recommendations", response_class=HTMLResponse)
def recommendations_page(request: Request, db: Session = Depends(get_db)):
    user(request); rows = db.query(Recommendation).options(joinedload(Recommendation.book)).filter(Recommendation.status == "active").order_by(Recommendation.score.desc()).all()
    seen, recs = set(), []
    for row in rows:
        if row.book_id not in seen:
            seen.add(row.book_id); recs.append(row)
    return render(request, "recommendations.html", recs=recs)
@app.post("/recommendations/refresh", response_class=HTMLResponse)
def recommendations_refresh(request: Request, db: Session = Depends(get_db)):
    user(request); entries = db.query(UserBook).options(joinedload(UserBook.book)).all()
    favorites = sorted([e for e in entries if e.rating and e.rating >= 4], key=lambda e:e.rating, reverse=True)
    authors = list(dict.fromkeys(e.book.authors for e in favorites if e.book.authors))
    categories = list(dict.fromkeys(category.strip() for e in favorites for category in (e.book.categories or "").split(",") if category.strip()))
    excluded = {"".join(c for c in e.book.title.lower() if c.isalnum()) for e in entries}
    previous_recommendations = db.query(Recommendation).options(joinedload(Recommendation.book)).filter(Recommendation.status.in_(["dismissed", "not_interested"])).all()
    excluded.update("".join(c for c in recommendation.book.title.lower() if c.isalnum()) for recommendation in previous_recommendations)
    candidates = google_candidates_for_profile(authors, categories, excluded)
    if not candidates: return render(request, "recommendations.html", recs=[], error="No recommendation candidates found. Refresh book metadata first, then try again.")
    profile = {"favorite_books":[{"title":e.book.title,"author":e.book.authors,"rating":e.rating,"categories":e.book.categories or ""} for e in favorites[:20]], "favorite_authors":authors[:8], "favorite_categories":categories[:8], "avoid":[e.book.title for e in entries if e.rating and e.rating <= 2]}
    batch = RecommendationBatch(model="deepseek", status="running", candidate_count=len(candidates), prompt_summary="Ratings and favorite authors")
    db.add(batch); db.flush()
    try: results = deepseek_rank(profile, candidates)
    except Exception as exc:
        batch.status="failed"; batch.error_message=str(exc)[:1000]; db.commit(); return render(request, "recommendations.html", recs=[], error="Could not refresh recommendations: " + str(exc))
    by_title = {"".join(c for c in item["title"].lower() if c.isalnum()):item for item in candidates}
    created, selected_books = 0, set()
    for result in results:
        candidate = by_title.get("".join(c for c in result.get("title", "").lower() if c.isalnum()))
        if not candidate: continue
        book = db.query(Book).filter(Book.google_books_id == candidate["google_books_id"]).first()
        if not book:
            book = Book(title=candidate["title"], authors=candidate["author"], google_books_id=candidate["google_books_id"], thumbnail_url=candidate["thumbnail_url"] or None, categories=", ".join(candidate["categories"]) or None, description=candidate["description"] or None, published_date=candidate["published_date"], page_count=candidate["page_count"]); db.add(book); db.flush()
        if book.id in selected_books: continue
        selected_books.add(book.id)
        db.add(Recommendation(batch_id=batch.id, book_id=book.id, score=float(result.get("score", 0)), reason=result.get("reason", ""), matched_preferences=", ".join(result.get("matched_preferences", []))))
        created += 1
    for recommendation in db.query(Recommendation).filter(Recommendation.status == "active").all():
        if recommendation.batch_id != batch.id: recommendation.status = "superseded"
    batch.status="complete"; batch.result_count=created; db.commit()
    return RedirectResponse("/recommendations", 303)
@app.post("/recommendations/{recommendation_id}/{action}")
def recommendation_action(recommendation_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user(request); rec = db.get(Recommendation, recommendation_id)
    if not rec or action not in {"want_to_read", "dismissed", "not_interested"}: raise HTTPException(404)
    rec.status = action
    if action == "want_to_read":
        if not rec.book.entry: db.add(UserBook(book_id=rec.book_id, status="want_to_read", source="recommendation"))
        else: rec.book.entry.status="want_to_read"
    db.commit(); return RedirectResponse("/recommendations", 303)
