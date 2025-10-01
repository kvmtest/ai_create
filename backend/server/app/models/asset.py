"""
Asset models
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(Text, nullable=False)
    file_type = Column(String(10), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    dimensions = Column(JSON)  # {"width": 1920, "height": 1080}
    dpi = Column(Integer)
    ai_metadata = Column(JSON)  # AI analysis results
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="assets")
    generated_assets = relationship("GeneratedAsset", back_populates="original_asset", cascade="all, delete-orphan")


class GeneratedAsset(Base):
    __tablename__ = "generated_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("generation_jobs.id"), nullable=False)
    original_asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    asset_format_id = Column(UUID(as_uuid=True), ForeignKey("asset_formats.id"), nullable=True)
    storage_path = Column(Text, nullable=False)
    file_type = Column(String(10), nullable=False)
    dimensions = Column(JSON, nullable=False)  # {"width": 1080, "height": 1080}
    is_nsfw = Column(Boolean, default=False)
    manual_edits = Column(JSON)  # Manual editing history
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    generation_job = relationship("GenerationJob", back_populates="generated_assets")
    original_asset = relationship("Asset", back_populates="generated_assets")
    asset_format = relationship("AssetFormat", back_populates="generated_assets")