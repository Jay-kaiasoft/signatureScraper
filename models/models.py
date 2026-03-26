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
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey ,Boolean

class Base(DeclarativeBase):
    pass

class Customers(Base):
    __tablename__ = "customers"

    cus_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(25), nullable=True)
    email_address: Mapped[str] = mapped_column(String(50), nullable=True)

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
# models.py  (add the 3 fields shown)
class SignatureResult(Base):
    __tablename__ = "temp_mail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("email_scraping_requests.id"), index=True)

    # NEW: identifiers for later deletion
    message_uid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # IMAP UID
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)  # RFC822 Message-ID
    mailbox: Mapped[str | None] = mapped_column(String(128), default="INBOX", nullable=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
      # ✅ use SQLAlchemy Boolean, not Python bool
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,            # Python-side default
        # server_default=sa.text("0"),  # uncomment in migration for MySQL
    )

    created_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[int] = mapped_column(ForeignKey("customers.cus_id"), index=True)

    request: Mapped[EmailFetchRequest] = relationship(back_populates="results")

class TeamDetails(Base):
    __tablename__ = "team_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Todo(Base):
    __tablename__ = "todo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, name="todo_id")
    related_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("customers.cus_id"), nullable=True)
    complected_work: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    creator: Mapped["Customers"] = relationship(foreign_keys=[created_by])
    assignees: Mapped[list["TodoAssign"]] = relationship(back_populates="todo_rel")

class TodoAssign(Base):
    __tablename__ = "todo_assignees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, name="todo_ass_id")
    todo_id: Mapped[int | None] = mapped_column(ForeignKey("todo.todo_id"), nullable=True)
    cus_id_assignee: Mapped[int | None] = mapped_column(ForeignKey("customers.cus_id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("team_details.id"), nullable=True)
    assign_by: Mapped[int | None] = mapped_column(ForeignKey("customers.cus_id"), nullable=True)
    complected_work: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    todo_rel: Mapped["Todo"] = relationship(back_populates="assignees")
    assignee: Mapped["Customers"] = relationship(foreign_keys=[cus_id_assignee])
    assigner: Mapped["Customers"] = relationship(foreign_keys=[assign_by])
    team: Mapped["TeamDetails"] = relationship()

