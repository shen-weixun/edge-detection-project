import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine(os.environ.get("DATABASE_URL", "postgresql+psycopg://face:face@localhost:5432/face"), pool_pre_ping=True)
Session = sessionmaker(engine)

class Base(DeclarativeBase):
    pass

class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = (UniqueConstraint("dataset", "path"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(20), index=True)
    path: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str] = mapped_column(String(255), default="")
    boxes: Mapped[list] = mapped_column(JSON, default=list)

class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
