import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BenchmarkData(Base):
    __tablename__ = "benchmark_data"
    __table_args__ = (UniqueConstraint("language", "dimension"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    avg_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
