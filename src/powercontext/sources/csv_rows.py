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

"""Row-level CSV source: parse an offline CSV into one captured Source per row.

Every physical data row becomes an independently-addressable Source whose
identity is derived from ``(document_id, primary_key_value)`` and whose
``powercontext.text-evidence`` projection reproduces the original row as a
compact JSON object in header order.
"""

from __future__ import annotations

import csv
import io
import json
from urllib.parse import quote

from pydantic import BaseModel, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

CSV_ROW_SOURCE_NAME = "csv-row"
_SOURCE_ID_PREFIX = "csv:"


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Build the stable, delimiter-safe Source identity for one CSV row.

    Both components are percent-encoded with ``safe=""`` so that ``:`` and any
    other delimiter characters cannot collide between documents or keys.
    """

    if not isinstance(document_id, str) or not document_id or document_id != document_id.strip():
        raise ValueError("document_id must be a non-empty string without surrounding whitespace")  # noqa: TRY003
    identity = f"{_SOURCE_ID_PREFIX}{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError("csv row source_id exceeds the 256 character limit")  # noqa: TRY003
    return identity


class CSVDocumentInput(BaseModel):
    """A complete offline CSV document handed to :func:`parse_csv_document`."""

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """One parsed CSV row, in original header order, captured as a Source."""

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    """A captured CSV row whose identity is ``(document_id, primary_key_value)``."""

    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def _row_mapping(columns: tuple[str, ...], values: tuple[str, ...]) -> dict[str, str]:
    return dict(zip(columns, values, strict=True))


class CSVRowSourceAdapter:
    """Resolve and read :class:`CSVRowInput` as a captured :class:`CSVRowSource`."""

    input_class = CSVRowInput
    name = CSV_ROW_SOURCE_NAME
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            definition_version="1",
            materialization=SourceMaterialization.CAPTURED,
            source_id=source_id,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=source.columns,
            values=source.values,
        )


class CSVRowTextEvidenceProjection:
    """Project a captured CSV row into the canonical text-evidence shape."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = _row_mapping(source.columns, source.values)
        content = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        metadata: dict[str, JsonValue] = {
            "document_id": source.document_id,
            "primary_key": source.primary_key,
            "primary_key_value": source.primary_key_value,
            "columns": list(source.columns),
            "row": row,
        }
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.source_id,
            content=content,
            metadata=metadata,
        )


CSV_ROW_SOURCE_ADAPTER = CSVRowSourceAdapter()
CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(
    CSV_ROW_SOURCE_ADAPTER,
    projections=(CSVRowTextEvidenceProjection(),),
)


def parse_csv_document(document: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    """Parse and fully validate one offline CSV document into row inputs.

    The whole document is decoded and validated atomically: any encoding, CSV
    formatting or data validation error raises :class:`ValueError` and no rows
    are returned.
    """

    if not isinstance(document.document_id, str) or not document.document_id or document.document_id != document.document_id.strip():
        raise ValueError("document_id must be a non-empty string without surrounding whitespace")  # noqa: TRY003
    if not isinstance(document.primary_key, str) or not document.primary_key or not document.primary_key.strip():
        raise ValueError("primary_key must be a non-empty, non-blank column name")  # noqa: TRY003

    try:
        text = document.content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("csv document must be strict UTF-8") from error

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        records = list(reader)
    except csv.Error as error:
        raise ValueError(f"malformed csv record: {error}") from error

    if not records:
        raise ValueError("csv document is empty: a header row is required")  # noqa: TRY003

    header = tuple(records[0])
    for column in header:
        if not column or not column.strip():
            raise ValueError("csv header must not contain empty or blank cells")  # noqa: TRY003
    if len(set(header)) != len(header):
        raise ValueError("csv header column names must be unique")  # noqa: TRY003
    if document.primary_key not in header:
        raise ValueError(f"primary_key {document.primary_key!r} is not a header column")  # noqa: TRY003
    pk_index = header.index(document.primary_key)

    rows: list[CSVRowInput] = []
    seen_keys: set[str] = set()
    for record in records[1:]:
        # A completely empty physical record ([]) is ignored; every other row
        # must match the header width.
        if len(record) == 0:
            continue
        if len(record) != len(header):
            raise ValueError("csv data row width must match the header")  # noqa: TRY003
        pk_value = record[pk_index]
        if not pk_value or not pk_value.strip():
            raise ValueError("primary key value must not be empty or blank")  # noqa: TRY003
        if pk_value in seen_keys:
            raise ValueError(f"duplicate primary key value {pk_value!r} in document")  # noqa: TRY003
        seen_keys.add(pk_value)
        rows.append(
            CSVRowInput(
                document_id=document.document_id,
                primary_key=document.primary_key,
                primary_key_value=pk_value,
                columns=header,
                values=tuple(record),
            )
        )
    return tuple(rows)


__all__ = [
    "CSVRowInput",
    "CSVRowSource",
    "CSVRowSourceAdapter",
    "CSV_ROW_SOURCE_ADAPTER",
    "CSV_ROW_SOURCE_DEFINITION",
    "CSV_ROW_SOURCE_NAME",
    "CSVDocumentInput",
    "CSVRowTextEvidenceProjection",
    "csv_row_source_id",
    "parse_csv_document",
]
