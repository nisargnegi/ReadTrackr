from datetime import datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    authors: Mapped[str] = mapped_column(String(1000), default="")
    isbn10: Mapped[str | None] = mapped_column(String(20), index=True)
    isbn13: Mapped[str | None] = mapped_column(String(20), index=True)
    google_books_id: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    published_date: Mapped[str | None] = mapped_column(String(50))
    publisher: Mapped[str | None] = mapped_column(String(500))
    page_count: Mapped[int | None]
    categories: Mapped[str | None] = mapped_column(String(1000))
    language: Mapped[str | None] = mapped_column(String(20))
    preview_link: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    entry: Mapped["UserBook"] = relationship(back_populates="book", uselist=False, cascade="all, delete-orphan")

class UserBook(Base):
    __tablename__ = "user_books"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="want_to_read", index=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    date_added: Mapped[datetime | None] = mapped_column(Date)
    date_started: Mapped[datetime | None] = mapped_column(Date)
    date_read: Mapped[datetime | None] = mapped_column(Date)
    review: Mapped[str | None] = mapped_column(Text)
    private_notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    goodreads_book_id: Mapped[str | None] = mapped_column(String(50))
    goodreads_shelves: Mapped[str | None] = mapped_column(String(1000))
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    book: Mapped[Book] = relationship(back_populates="entry")

class RecommendationBatch(Base):
    __tablename__ = "recommendation_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    model: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="complete")
    prompt_summary: Mapped[str | None] = mapped_column(Text)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recommendation_batches.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    matched_preferences: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(50), default="deepseek")
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    book: Mapped[Book] = relationship()
