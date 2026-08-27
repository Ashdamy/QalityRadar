import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

analysis_type_enum = ENUM(
    "repository", "url", "combined", name="analysis_type", create_type=False,
)
analysis_status_enum = ENUM(
    "pending", "cloning", "running", "scoring", "completed", "failed", "timeout",
    name="analysis_status", create_type=False,
)
finding_severity_enum = ENUM(
    "critical", "high", "medium", "low", "info", name="finding_severity", create_type=False,
)
finding_type_enum = ENUM(
    "security", "test_coverage", "documentation", "dependency",
    "cicd", "structure", "activity",
    "performance", "accessibility", "seo", "compatibility", "usability",
    name="finding_type", create_type=False,
)


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "(repository_id IS NOT NULL AND app_id IS NULL) OR "
            "(repository_id IS NULL AND app_id IS NOT NULL) OR "
            "(repository_id IS NOT NULL AND app_id IS NOT NULL)",
            name="analyses_target_chk",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True
    )
    app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deployed_apps.id", ondelete="CASCADE"), nullable=True
    )
    analysis_type: Mapped[str] = mapped_column(analysis_type_enum, nullable=False)
    status: Mapped[str] = mapped_column(analysis_status_enum, nullable=False, server_default="pending")
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    confidence_level: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Dimension(Base):
    __tablename__ = "dimensions"
    __table_args__ = (
        UniqueConstraint("analysis_id", "name"),
        CheckConstraint("score >= 0 AND score <= 100"),
        CheckConstraint("weight > 0 AND weight <= 1"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    raw_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(finding_type_enum, nullable=False)
    severity: Mapped[str] = mapped_column(finding_severity_enum, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Discrepancy(Base):
    __tablename__ = "discrepancies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    repo_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    url_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    delta: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnalysisComparison(Base):
    __tablename__ = "analysis_comparisons"
    __table_args__ = (UniqueConstraint("analysis_1_id", "analysis_2_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    analysis_1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    analysis_2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    score_delta: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    improvements_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    regressions_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Improvement(Base):
    __tablename__ = "improvements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_comparisons.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    current_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    delta: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Regression(Base):
    __tablename__ = "regressions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_comparisons.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    current_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    delta: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    severity: Mapped[str] = mapped_column(finding_severity_enum, nullable=False)
