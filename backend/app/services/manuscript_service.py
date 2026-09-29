from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models.manuscript import Manuscript
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.processing_job import ProcessingJob
from app.models.extraction_run import ExtractionRun
from app.core.constants import JobType, JobStatus, ExtractionRunStatus
from app.repositories.manuscript_repo import ManuscriptRepository
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.job_repo import JobRepository
from app.utils.file_handler import save_file_content
from app.utils.hashing import compute_file_sha256
from app.utils.text_splitter import split_into_chapters
from app.config.logging import get_logger

logger = get_logger(__name__)

class ManuscriptService:
    def __init__(self, db: Session):
        self.db = db
        self.manuscript_repo = ManuscriptRepository(db)
        self.chapter_repo = ChapterRepository(db)
        self.job_repo = JobRepository(db)

    def upload_manuscript(
        self,
        world_id: str,
        filename: str,
        file_bytes: bytes,
        file_type: str = "text/plain",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingests a manuscript:
        1. Saves original file to storage.
        2. Splits into chapters (auto-detects headings or defaults to 1 chapter).
        3. Creates Manuscript, Chapter, and ChapterVersion records.
        4. Initializes parent ProcessingJob and child ExtractionRuns.
        """
        # Save physical file
        saved_path = save_file_content(file_bytes, filename, subfolder=f"worlds/{world_id}")
        
        lower_filename = filename.lower()
        if lower_filename.endswith(".docx"):
            import io
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            content_text = "\n".join([p.text for p in doc.paragraphs])
        elif lower_filename.endswith(".pdf"):
            import io
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            content_text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
        else:
            content_text = file_bytes.decode("utf-8", errors="replace")

        # 1. Create Manuscript record
        manuscript = self.manuscript_repo.create({
            "world_id": world_id,
            "title": filename,
            "original_file_path": saved_path,
            "file_type": file_type
        })

        # 2. Split into chapters
        detected_chapters = split_into_chapters(content_text)
        total_chapters = len(detected_chapters)

        # 3. Create parent ProcessingJob
        job = self.job_repo.create({
            "world_id": world_id,
            "manuscript_id": manuscript.id,
            "job_type": JobType.INITIAL_EXTRACTION.value,
            "status": JobStatus.QUEUED.value,
            "chapters_total": total_chapters,
            "chapters_completed": 0
        })

        created_chapters = []
        extraction_runs = []

        for ch_num, ch_title, ch_text in detected_chapters:
            # Save chapter text version
            ch_bytes = ch_text.encode("utf-8")
            ch_hash = compute_file_sha256(ch_bytes)
            ch_path = save_file_content(ch_bytes, f"ch_{ch_num}_{filename}", subfolder=f"chapters/{manuscript.id}")

            # Chapter record
            chapter = self.chapter_repo.create({
                "manuscript_id": manuscript.id,
                "chapter_number": ch_num,
                "title": ch_title
            })

            # ChapterVersion record
            version = self.chapter_repo.create_version(
                chapter_id=chapter.id,
                content_path=ch_path,
                content_hash=ch_hash,
                version_number=1
            )

            # ExtractionRun record
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

            created_chapters.append(chapter)
            extraction_runs.append((run.id, ch_text, chapter.id, version.id))

        return {
            "manuscript_id": manuscript.id,
            "job_id": job.id,
            "chapters_count": total_chapters,
            "extraction_runs": extraction_runs
        }

    def get_manuscript(self, manuscript_id: str) -> Optional[Manuscript]:
        return self.manuscript_repo.get_with_chapters(manuscript_id)

    def list_manuscripts(self, world_id: str) -> List[Manuscript]:
        return self.manuscript_repo.get_by_world(world_id)
