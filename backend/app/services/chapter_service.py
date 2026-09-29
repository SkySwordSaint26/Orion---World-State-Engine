from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.processing_job import ProcessingJob
from app.models.extraction_run import ExtractionRun
from app.core.constants import JobType, JobStatus, ExtractionRunStatus
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.job_repo import JobRepository
from app.repositories.manuscript_repo import ManuscriptRepository
from app.utils.file_handler import save_file_content, read_file_text
from app.utils.hashing import compute_file_sha256
from app.config.logging import get_logger

logger = get_logger(__name__)

class ChapterService:
    def __init__(self, db: Session):
        self.db = db
        self.chapter_repo = ChapterRepository(db)
        self.job_repo = JobRepository(db)
        self.manuscript_repo = ManuscriptRepository(db)

    def get_chapter(self, chapter_id: str) -> Optional[Chapter]:
        return self.chapter_repo.get(chapter_id)

    def get_chapter_content(self, chapter_id: str) -> Optional[str]:
        version = self.chapter_repo.get_latest_version(chapter_id)
        if version and version.content_path:
            try:
                return read_file_text(version.content_path)
            except Exception:
                return ""
        return ""

    def list_chapters(self, manuscript_id: str) -> List[Chapter]:
        return self.chapter_repo.get_by_manuscript(manuscript_id)

    def create_chapter(self, manuscript_id: str, title: str, content: str = "") -> Chapter:
        existing = self.list_chapters(manuscript_id)
        next_num = max([ch.chapter_number for ch in existing], default=0) + 1
        
        chapter = self.chapter_repo.create({
            "manuscript_id": manuscript_id,
            "chapter_number": next_num,
            "title": title
        })
        
        if content:
            content_bytes = content.encode("utf-8")
            ch_hash = compute_file_sha256(content_bytes)
            ch_path = save_file_content(content_bytes, f"ch_{next_num}.txt", subfolder=f"chapters/{manuscript_id}")
            self.chapter_repo.create_version(chapter.id, ch_path, ch_hash, 1)
            
        return chapter

    def delete_chapter(self, chapter_id: str) -> None:
        chapter = self.chapter_repo.get(chapter_id)
        if not chapter:
            return
        manuscript_id = chapter.manuscript_id
        self.chapter_repo.delete(chapter_id)
        if manuscript_id:
            remaining = self.chapter_repo.get_by_manuscript(manuscript_id)
            if len(remaining) == 0:
                self.manuscript_repo.delete(manuscript_id)

    def get_chapter_versions(self, chapter_id: str) -> List[ChapterVersion]:
        chapter = self.chapter_repo.get(chapter_id)
        if not chapter:
            return []
        # Return versions sorted by version number descending
        return sorted(chapter.versions, key=lambda v: v.version_number, reverse=True)

    def update_chapter_content(
        self,
        chapter_id: str,
        content_text: str,
        user_id: Optional[str] = None
    ) -> Tuple[ChapterVersion, ProcessingJob, ExtractionRun]:
        chapter = self.chapter_repo.get(chapter_id)
        if not chapter:
            raise ValueError(f"Chapter {chapter_id} not found")

        manuscript = self.manuscript_repo.get(chapter.manuscript_id)
        world_id = manuscript.world_id if manuscript else None
        if not world_id:
            raise ValueError(f"World associated with chapter {chapter_id} not found")

        content_bytes = content_text.encode("utf-8")
        ch_hash = compute_file_sha256(content_bytes)
        ch_path = save_file_content(content_bytes, f"ch_{chapter.chapter_number}_rev.txt", subfolder=f"chapters/{chapter.manuscript_id}")

        # 1. Create new ChapterVersion
        version = self.chapter_repo.create_version(
            chapter_id=chapter.id,
            content_path=ch_path,
            content_hash=ch_hash
        )

        # 2. Create RE_EXTRACTION ProcessingJob
        job = self.job_repo.create({
            "world_id": world_id,
            "manuscript_id": chapter.manuscript_id,
            "job_type": JobType.RE_EXTRACTION.value,
            "status": JobStatus.QUEUED.value,
            "chapters_total": 1,
            "chapters_completed": 0
        })

        # 3. Create ExtractionRun
        run = ExtractionRun(
            chapter_version_id=version.id,
            processing_job_id=job.id,
            status=ExtractionRunStatus.PENDING.value,
            extractor_version="llama3.1:8b",
            created_by=user_id
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        return version, job, run
