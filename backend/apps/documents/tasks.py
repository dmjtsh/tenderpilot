import hashlib
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from qdrant_client.models import Filter, FieldCondition, MatchAny

from apps.documents.eis_docs import download_file_from_url, fetch_document_links
from apps.documents.models import TenderDocument
from apps.documents.parsers import (
    can_parse,
    detect_file_type,
    detect_file_type_by_content,
    extract_archive,
    is_archive,
    parse_doc,
    parse_docx,
    parse_pdf,
)
from apps.documents.services import classify_documents_priority, detect_content_priority
from apps.documents.storage import delete_prefix, upload_file
from apps.tenders.models import Tender

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def download_and_parse_documents(self, tender_id: int) -> str:
    try:
        tender = Tender.objects.get(id=tender_id)
    except Tender.DoesNotExist:
        return f"tender {tender_id} not found"

    links = fetch_document_links(tender.number)

    if not links:
        return f"no documents for tender {tender.number}"

    created_ids: list[int] = []
    for link in links:
        url = link["url"]
        filename = link["filename"]
        data = download_file_from_url(url)
        if not data:
            continue

        file_type = detect_file_type(filename) or detect_file_type_by_content(data)

        file_hash = hashlib.md5(data).hexdigest()

        s3_key = f"original/{tender.number}/{filename}"

        existing = TenderDocument.objects.filter(tender=tender, s3_key=s3_key).first()
        if existing:
            if existing.file_hash == file_hash:
                logger.info("Skipping duplicate %s (hash=%s)", filename, file_hash)
                if existing.parse_status == TenderDocument.ParseStatus.PENDING:
                    created_ids.append(existing.id)
                continue
            existing.file_hash = file_hash
            existing.file_size = len(data)
            existing.file_type = file_type
            existing.parse_status = TenderDocument.ParseStatus.PENDING
            existing.parsed_text = ""
            existing.save(update_fields=["file_hash", "file_size", "file_type", "parse_status", "parsed_text"])
            upload_file(s3_key, data)
            created_ids.append(existing.id)
            continue

        if TenderDocument.objects.filter(tender=tender, file_hash=file_hash).exists():
            logger.info("Skipping duplicate %s (hash=%s)", filename, file_hash)
            continue

        upload_file(s3_key, data)

        doc = TenderDocument.objects.create(
            tender=tender,
            filename=filename,
            file_type=file_type,
            s3_key=s3_key,
            file_size=len(data),
            file_hash=file_hash,
            content_priority=detect_content_priority(filename),
        )
        created_ids.append(doc.id)

    if created_ids:
        all_docs = TenderDocument.objects.filter(tender=tender)
        filenames = list(all_docs.values_list("filename", flat=True))
        priorities = classify_documents_priority(filenames)
        for doc in all_docs:
            if doc.filename in priorities:
                new_p = priorities[doc.filename]
                if new_p != doc.content_priority:
                    doc.content_priority = new_p
                    doc.save(update_fields=["content_priority"])

        for doc_id in created_ids:
            parse_document.delay(doc_id)

    return f"tender {tender.number}: {len(created_ids)} documents queued"


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def parse_document(self, document_id: int) -> str:
    try:
        doc = TenderDocument.objects.select_related("tender").get(id=document_id)
    except TenderDocument.DoesNotExist:
        return f"document {document_id} not found"

    doc.parse_status = TenderDocument.ParseStatus.PROCESSING
    doc.save(update_fields=["parse_status"])

    try:
        from apps.documents.storage import download_file
        data = download_file(doc.s3_key)

        if not doc.file_type:
            doc.file_type = detect_file_type_by_content(data)
            if doc.file_type:
                doc.save(update_fields=["file_type"])
                logger.info("Detected file type %s for %s by content", doc.file_type, doc.filename)

        if is_archive(doc.file_type):
            _handle_archive(doc, data)
            doc.parse_status = TenderDocument.ParseStatus.DONE
            doc.parsed_at = timezone.now()
            doc.save(update_fields=["parse_status", "parsed_at"])
            return f"archive {doc.filename}: extracted"

        if not can_parse(doc.file_type):
            doc.parse_status = TenderDocument.ParseStatus.SKIPPED
            doc.save(update_fields=["parse_status"])
            return f"skipped {doc.filename} (type={doc.file_type})"

        if doc.file_type == "pdf":
            text, is_scanned = parse_pdf(data)
            doc.is_scanned = is_scanned
            if is_scanned:
                doc.parse_status = TenderDocument.ParseStatus.SKIPPED
                doc.save(update_fields=["parse_status", "is_scanned"])
                return f"skipped scan {doc.filename}"
            doc.parsed_text = text

        elif doc.file_type == "docx":
            doc.parsed_text = parse_docx(data)

        elif doc.file_type == "doc":
            doc.parsed_text = parse_doc(data)

        doc.parse_status = TenderDocument.ParseStatus.DONE
        doc.parsed_at = timezone.now()
        doc.save(update_fields=["parsed_text", "parse_status", "parsed_at", "is_scanned"])

        if doc.parsed_text:
            index_document_chunks.delay(doc.id)

        return f"parsed {doc.filename} ({len(doc.parsed_text)} chars)"

    except Exception as exc:
        doc.parse_status = TenderDocument.ParseStatus.FAILED
        doc.parse_error = str(exc)[:2000]
        doc.save(update_fields=["parse_status", "parse_error"])
        logger.exception("Failed to parse document %d (%s)", doc.id, doc.filename)
        return f"failed {doc.filename}: {exc}"


def _handle_archive(parent_doc: TenderDocument, data: bytes) -> None:
    entries = extract_archive(data, parent_doc.file_type)
    child_ids: list[int] = []
    for entry_filename, entry_data in entries:
        file_type = detect_file_type(entry_filename)
        file_hash = hashlib.md5(entry_data).hexdigest()

        if TenderDocument.objects.filter(
            tender=parent_doc.tender, file_hash=file_hash,
        ).exists():
            continue

        s3_key = f"extracted/{parent_doc.tender.number}/{entry_filename}"
        upload_file(s3_key, entry_data)

        child = TenderDocument.objects.create(
            tender=parent_doc.tender,
            filename=entry_filename,
            file_type=file_type,
            s3_key=s3_key,
            file_size=len(entry_data),
            file_hash=file_hash,
            parent_document=parent_doc,
            archive_path=entry_filename,
            content_priority=detect_content_priority(entry_filename),
        )
        child_ids.append(child.id)

    if child_ids:
        children = TenderDocument.objects.filter(id__in=child_ids)
        filenames = list(children.values_list("filename", flat=True))
        priorities = classify_documents_priority(filenames)
        for child in children:
            if child.filename in priorities:
                new_p = priorities[child.filename]
                if new_p != child.content_priority:
                    child.content_priority = new_p
                    child.save(update_fields=["content_priority"])
            parse_document.delay(child.id)


CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def index_document_chunks(self, document_id: int) -> str:
    try:
        doc = TenderDocument.objects.get(id=document_id)
    except TenderDocument.DoesNotExist:
        return f"document {document_id} not found"

    if not doc.parsed_text or doc.parsed_text.strip() == "":
        return f"document {document_id} has no text"

    from apps.documents.services import clean_text
    from apps.search.embedder import Embedder
    from apps.search.services import qdrant

    qdrant.delete_doc_chunks(document_id)

    text = clean_text(doc.parsed_text)
    if not text:
        return f"document {document_id} empty after cleaning"

    words = text.split()
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + CHUNK_SIZE])
        chunks.append(chunk)
        i += CHUNK_SIZE - CHUNK_OVERLAP

    embedder = Embedder()
    vectors = embedder.embed_passages(chunks)

    import uuid
    points = []
    for idx, (chunk_text, vector) in enumerate(zip(chunks, vectors)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"doc:{document_id}:chunk:{idx}"))
        payload = {
            "tender_id": doc.tender_id,
            "document_id": document_id,
            "chunk_index": idx,
            "text": chunk_text,
            "filename": doc.filename,
            "content_priority": doc.content_priority,
        }
        points.append((point_id, vector, payload))

    qdrant.upsert_doc_chunks(points)
    Tender.objects.filter(id=doc.tender_id).update(docs_indexed_at=timezone.now())
    return f"indexed {len(chunks)} chunks for document {document_id} ({doc.filename})"


DOC_CHUNKS_TTL_HOURS = 48


@shared_task
def cleanup_doc_chunks() -> str:
    cutoff = timezone.now() - timedelta(hours=DOC_CHUNKS_TTL_HOURS)

    stale_tenders = Tender.objects.filter(
        docs_indexed_at__isnull=False,
        docs_indexed_at__lt=cutoff,
    )
    if not stale_tenders.exists():
        return "nothing to clean"

    stale_ids = list(stale_tenders.values_list("id", flat=True))

    from apps.search.services import qdrant_service, COLLECTION_DOC_CHUNKS

    try:
        qdrant_service.client.delete(
            collection_name=COLLECTION_DOC_CHUNKS,
            points_selector=Filter(
                must=[FieldCondition(key="tender_id", match=MatchAny(any=stale_ids))]
            ),
        )
    except Exception as exc:
        logger.warning("Qdrant chunk cleanup error: %s", exc)

    cleaned = TenderDocument.objects.filter(
        tender_id__in=stale_ids,
        parse_status=TenderDocument.ParseStatus.DONE,
    ).exclude(parsed_text="").update(parsed_text="")

    stale_tenders.update(docs_indexed_at=None)

    return f"cleaned chunks for {len(stale_ids)} tenders, {cleaned} docs text cleared"


@shared_task
def cleanup_old_documents() -> str:
    cutoff = timezone.now() - timedelta(days=730)

    old_ids = list(
        Tender.objects.filter(deadline_at__lt=cutoff).values_list("id", flat=True)
    )
    if not old_ids:
        return "nothing to clean"

    from apps.search.services import qdrant_service, COLLECTION_DOC_CHUNKS

    try:
        qdrant_service.client.delete(
            collection_name=COLLECTION_DOC_CHUNKS,
            points_selector=Filter(
                must=[FieldCondition(key="tender_id", match=MatchAny(any=old_ids))]
            ),
        )
    except Exception as exc:
        logger.warning("Qdrant cleanup error: %s", exc)

    for tender in Tender.objects.filter(id__in=old_ids).only("number"):
        delete_prefix(f"original/{tender.number}/")
        delete_prefix(f"extracted/{tender.number}/")

    cleaned_count = TenderDocument.objects.filter(tender_id__in=old_ids).update(
        parsed_text="",
        parse_status=TenderDocument.ParseStatus.CLEANED,
    )

    return f"cleaned {len(old_ids)} tenders, {cleaned_count} documents"
