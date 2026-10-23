from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.utils.hashing import generate_uuid

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    world_id = Column(String(36), ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False)
    manuscript_id = Column(String(36), ForeignKey("manuscripts.id", ondelete="SET NULL"), nullable=True)
    job_type = Column(String(50), default="INITIAL_EXTRACTION", nullable=False)
    status = Column(String(50), default="queued", nullable=False)
    chapters_total = Column(Integer, default=0, nullable=False)
    chapters_completed = Column(Integer, default=0, nullable=False)
    progress_percent = Column(Integer, default=0, nullable=False)
    current_stage = Column(String(100), nullable=True)
    current_chapter = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    world = relationship("World", back_populates="processing_jobs")
    manuscript = relationship("Manuscript", back_populates="processing_jobs")
    extraction_runs = relationship("ExtractionRun", back_populates="processing_job", cascade="all, delete-orphan")
