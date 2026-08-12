import csv, io, json, time
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware
from .auth import verify_password
from .config import APP_PASSWORD_HASH, APP_USERNAME, DATA_DIR, SESSION_SECRET
from .database import Base, engine, get_db
from .models import Book, UserBook
from .services import import_goodreads
from .views import environment
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
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
    user(request); entries = db.query(UserBook).options(joinedload(UserBook.book)).all(); current = [e for e in entries if e.status == "currently_reading"]; recent = sorted([e for e in entries if e.status == "read"], key=lambda e:e.date_read or e.updated_at, reverse=True)[:6]
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
    user(request); data=await csv_file.read(); rows=list(csv.DictReader(io.StringIO(data.decode("utf-8-sig",errors="replace")))); request.session["import_csv"]=data.decode("utf-8-sig",errors="replace"); return render(request,"import.html",preview=rows[:8],total=len(rows))
@app.post("/import/commit",response_class=HTMLResponse)
def import_commit(request:Request,db:Session=Depends(get_db)):
    user(request); contents=request.session.pop("import_csv","").encode()
    if not contents: return RedirectResponse("/import",303)
    summary=import_goodreads(db,contents); db.commit(); return render(request,"import.html",summary=summary)
@app.get("/export/{format}")
def export_library(format:str,request:Request,db:Session=Depends(get_db)):
    user(request); records=[{"title":e.book.title,"authors":e.book.authors,"status":e.status,"rating":e.rating,"notes":e.private_notes,"date_read":str(e.date_read or "")} for e in db.query(UserBook).options(joinedload(UserBook.book)).all()]
    if format=="json": return Response(json.dumps(records,indent=2),media_type="application/json",headers={"Content-Disposition":"attachment; filename=readtrackr.json"})
    if format=="csv":
        out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=["title","authors","status","rating","notes","date_read"]); writer.writeheader(); writer.writerows(records); return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=readtrackr.csv"})
    raise HTTPException(404)
