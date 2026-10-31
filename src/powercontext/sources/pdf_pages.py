# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Full-document PDF parsing into page-level Sources and page retrieval.

Every physical page of an offline PDF becomes a CAPTURED Source identified by
``(document_id, document_sha256, page_number)``. ``search_pdf_pages`` runs the
question through the scoped Memory FTS index and returns exact citations for up
to ``limit`` distinct pages.
"""

from __future__ import annotations

import hashlib
import io
import re
from urllib.parse import quote, unquote

from pydantic import BaseModel
from pypdf import PdfReader

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    TextEvidence,
)
from powercontext.sources.models import Source, SourceMaterialization

PDF_PAGE_SOURCE_NAME = "pdf-page"
_SOURCE_ID_PREFIX = "pdf:"


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    """Build the stable identity for one physical PDF page."""

    if not isinstance(document_id, str) or not document_id or not document_id.strip():
        raise ValueError("document_id must be a non-empty, non-blank string")  # noqa: TRY003
    identity = f"{_SOURCE_ID_PREFIX}{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError("pdf page source_id exceeds the 256 character limit")  # noqa: TRY003
    return identity


class PDFDocumentInput(BaseModel):
    """A complete offline PDF document to parse page by page."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical page extracted from a parsed PDF document."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """A captured physical PDF page."""

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageAdapter:
    """Resolve and read :class:`PDFPageInput` as a captured :class:`PDFPageSource`."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = pdf_page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            definition_version="1",
            materialization=SourceMaterialization.CAPTURED,
            source_id=source_id,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Project a captured PDF page into the canonical text-evidence shape."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_ADAPTER = PDFPageAdapter()
PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDF_PAGE_SOURCE_ADAPTER,
    projections=(PDFPageTextEvidenceProjection(),),
)


def parse_pdf_document(document: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page of a PDF, in order, from page 1.

    Empty, non-PDF, truncated or otherwise unreadable files raise
    :class:`ValueError` atomically and never return partial pages.
    """

    if not isinstance(document.document_id, str) or not document.document_id or not document.document_id.strip():
        raise ValueError("document_id must be a non-empty, non-blank string")  # noqa: TRY003
    content = document.content
    if not content:
        raise ValueError("pdf document is empty")  # noqa: TRY003

    document_sha256 = hashlib.sha256(content).hexdigest()

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            # PDFs with an empty user-password permission marker must be readable.
            if reader.decrypt("") == 0:
                raise ValueError("pdf requires a password and cannot be read offline")  # noqa: TRY003
        pages: list[PDFPageInput] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(
                PDFPageInput(
                    document_id=document.document_id,
                    document_sha256=document_sha256,
                    page_number=index,
                    text=text,
                )
            )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"cannot parse pdf document: {error}") from error

    if not pages:
        raise ValueError("pdf document contains no pages")  # noqa: TRY003
    return tuple(pages)


async def search_pdf_pages(memory, question: str, limit: int = 20):
    """Return exact Memory citations for up to ``limit`` distinct evidence pages.

    The question is tokenized offline into significant terms and run through the
    scoped Memory FTS index as an OR query to widen recall; hits are resolved
    back to their page identity and deduplicated on ``(document_id, page_number)``
    so no page is returned twice.
    """

    from powercontext.builtin.artifacts.memory.models import MemoryCitation
    from powercontext.builtin.runtime import GetMemoryEntryRequest, SearchMemoryRequest

    fetch = max(limit * 5, limit + 30, 100)
    fts_query = _build_fts_query(question) or question
    page = await memory.search(SearchMemoryRequest(query=fts_query, mode="fts", limit=fetch))

    seen: set[tuple[str, int]] = set()
    citations: list[MemoryCitation] = []
    for hit in page.hits:
        citation = MemoryCitation(
            memory_ref=hit.memory_ref,
            entry_id=hit.entry_id,
            entry_version_id=hit.entry_version_id,
        )
        entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
        for reference in entry.sources:
            key = _page_key_from_source_id(reference.source_id)
            if key is None or key in seen:
                continue
            seen.add(key)
            citations.append(citation)
            break
        if len(citations) >= limit:
            break
    return tuple(citations)


def _page_key_from_source_id(source_id: str) -> tuple[str, int] | None:
    """Decode ``pdf:{doc}:{sha256}:{page}`` into the dedup key without a catalog."""

    if not source_id.startswith(_SOURCE_ID_PREFIX):
        return None
    body = source_id[len(_SOURCE_ID_PREFIX) :]
    try:
        encoded_document, _sha256, page_text = body.rsplit(":", 2)
    except ValueError:
        return None
    return (unquote(encoded_document), int(page_text))


_FTS_STOPWORDS = frozenset(
    {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "the", "that", "this", "these", "those", "a", "an", "and", "or", "but",
        "if", "then", "than", "as", "of", "in", "on", "at", "to", "for", "with",
        "by", "from", "is", "are", "was", "were", "be", "been", "being",
        "it", "its", "its", "i", "we", "you", "they", "he", "she", "them",
        "his", "her", "their", "our", "your", "my", "me", "not", "no", "do",
        "does", "did", "done", "have", "has", "had", "can", "could", "would",
        "should", "will", "shall", "may", "might", "must", "per", "via",
        "using", "use", "used", "based", "define", "defined", "definition",
        "respond", "response", "answer", "state", "give", "given", "assume",
        "question", "details", "shown", "shown", "within", "about", "into",
    }
)


def _build_fts_query(question: str) -> str:
    """Tokenize a natural-language question into an OR-ed FTS query.

    Long finance questions must not require every filler token to appear on a
    page; we keep significant alphanumeric terms and OR them so relevant pages
    surface in the FTS ranking.
    """

    tokens = re.findall(r"[a-z0-9]+", question.lower())
    terms = []
    seen = set()
    for token in tokens:
        if len(token) < 3 or token in _FTS_STOPWORDS:
            continue
        if token not in seen:
            seen.add(token)
            terms.append(f'"{token}"')
    return " OR ".join(terms)


__all__ = [
    "PDFPageInput",
    "PDFPageSource",
    "PDFPageAdapter",
    "PDF_PAGE_SOURCE_ADAPTER",
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDF_PAGE_SOURCE_NAME",
    "PDFDocumentInput",
    "PDFPageTextEvidenceProjection",
    "parse_pdf_document",
    "pdf_page_source_id",
    "search_pdf_pages",
]
