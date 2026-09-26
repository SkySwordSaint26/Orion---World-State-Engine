import re
from typing import List, Tuple, Dict, Any

def split_into_chapters(text: str) -> List[Tuple[int, str, str]]:
    """
    Detects chapter boundaries in text.
    Returns a list of tuples: (chapter_number, title, content).
    If no chapter markers are found, returns a single chapter with the full text.
    """
    if not text.strip():
        return [(1, "Chapter 1", "")]

    # Common chapter heading patterns
    chapter_pattern = re.compile(
        r'(?:^|\n\n+)(?:[#*]{0,3}\s*)?(CHAPTER|Chapter|ACT|Act|PROLOGUE|Prologue|EPILOGUE|Epilogue)\s+([0-9IVXLCDMivxlcdm]+|[A-Za-z]+)?(?:\s*[:.\-—]\s*([^\n]+))?',
        re.MULTILINE
    )

    matches = list(chapter_pattern.finditer(text))

    if not matches or len(matches) <= 1:
        # Fallback: single chapter
        return [(1, "Chapter 1", text.strip())]

    chapters = []
    for i, match in enumerate(matches):
        chapter_num = i + 1
        heading_type = match.group(1) or "Chapter"
        number_str = match.group(2) or str(chapter_num)
        title_suffix = match.group(3)

        if title_suffix:
            title = f"{heading_type} {number_str}: {title_suffix.strip()}"
        else:
            title = f"{heading_type} {number_str}"

        start_pos = match.start()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start_pos:end_pos].strip()

        chapters.append((chapter_num, title, content))

    return chapters


def chunk_text(text: str, max_chars: int = 8000, overlap: int = 500) -> List[Dict[str, Any]]:
    """
    Split chapter text into manageable overlapping chunks for the LLM.
    Returns list of dicts with 'chunk_id', 'text', 'start_pos', 'end_pos'.

    DEPRECATED - no longer used by extraction (see app/preprocessing: sentence-aligned chunks with exact
    offsets). Kept only for backward compatibility. Known defects: cuts mid-sentence, 'text' is stripped so
    start_pos/end_pos do not match it, and it never terminates when overlap >= chunk progress.
    """
    chunks = []
    start = 0
    text_length = len(text)
    chunk_index = 0

    while start < text_length:
        end = min(start + max_chars, text_length)

        # Prefer ending at a paragraph boundary
        if end < text_length:
            paragraph_break = text.rfind("\n\n", start, end)
            if paragraph_break > start + (max_chars * 0.5):
                end = paragraph_break

        chunk_str = text[start:end].strip()
        if chunk_str:
            chunks.append({
                "chunk_id": f"chunk_{chunk_index:04d}",
                "text": chunk_str,
                "start_pos": start,
                "end_pos": end
            })
            chunk_index += 1

        if end >= text_length:
            break

        start = max(0, end - overlap)

    return chunks
