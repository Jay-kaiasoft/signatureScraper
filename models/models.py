# models.py
"""
SQLAlchemy ORM models for EmailFetchRequest and SignatureResult.

Status semantics for EmailFetchRequest:
  0 = pending
  2 = running
  1 = done
 -1 = failed (optional, helpful for observability)
"""

from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey

class Base(DeclarativeBase):
    pass

class Customers(Base):
    __tablename__ = "customers"

    cus_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

class EmailFetchRequest(Base):
    __tablename__ = "email_scraping_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)  # Consider using app passwords
    protocol: Mapped[str] = mapped_column(String(16), default="imaps")  # kept for future flexibility
    imap_host: Mapped[str] = mapped_column(String(255), nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    max_messages: Mapped[int] = mapped_column(Integer, default=10)

    status: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 0=pending,2=running,1=done,-1=failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[int] = mapped_column(ForeignKey("customers.cus_id"), index=True)

    results: Mapped[list["SignatureResult"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )

class SignatureResult(Base):
    __tablename__ = "temp_mail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("email_scraping_requests.id"), index=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[int] = mapped_column(ForeignKey("customers.cus_id"), index=True)
    
    request: Mapped[EmailFetchRequest] = relationship(back_populates="results")
