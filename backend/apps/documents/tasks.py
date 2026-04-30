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
    extract_archive,
    is_archive,
    parse_docx,
    parse_pdf,
)
from apps.documents.services import detect_content_priority
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

    created = 0
    for link in links:
        url = link["url"]
        filename = link["filename"]
        file_type = detect_file_type(filename)

        data = download_file_from_url(url)
        if not data:
            continue

        file_hash = hashlib.md5(data).hexdigest()

        if TenderDocument.objects.filter(tender=tender, file_hash=file_hash).exists():
            logger.info("Skipping duplicate %s (hash=%s)", filename, file_hash)
            continue

        s3_key = f"original/{tender.number}/{filename}"
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
        created += 1
        parse_document.delay(doc.id)

    return f"tender {tender.number}: {created} documents queued"


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

        doc.parse_status = TenderDocument.ParseStatus.DONE
        doc.parsed_at = timezone.now()
        doc.save(update_fields=["parsed_text", "parse_status", "parsed_at", "is_scanned"])
        return f"parsed {doc.filename} ({len(doc.parsed_text)} chars)"

    except Exception as exc:
        doc.parse_status = TenderDocument.ParseStatus.FAILED
        doc.parse_error = str(exc)[:2000]
        doc.save(update_fields=["parse_status", "parse_error"])
        logger.exception("Failed to parse document %d (%s)", doc.id, doc.filename)
        return f"failed {doc.filename}: {exc}"


def _handle_archive(parent_doc: TenderDocument, data: bytes) -> None:
    entries = extract_archive(data, parent_doc.file_type)
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
        parse_document.delay(child.id)


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
