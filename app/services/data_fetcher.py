"""Data fetcher service: fetch app listing and reviews from Google Play."""
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

GOOGLE_ERROR_CODES = {
    "missing_review_id",
    "missing_edit_id",
    "missing_default_language_title",
    "google_api_not_found",
    "google_api_forbidden",
    "google_api_error",
}


def resolve_google_discovery_url(discovery_url: Optional[str]) -> Optional[str]:
    """Normalize Google discovery host/URL into a usable discovery endpoint."""
    if not discovery_url:
        return None

    value = discovery_url.strip()
    if not value:
        return None

    if "://" not in value:
        value = f"https://{value}"

    value = value.rstrip("/")

    if "$discovery" not in value:
        value = f"{value}/$discovery/rest?version=v3"

    return value


def _build_androidpublisher_service(credential_json: str, discovery_url: Optional[str] = None):
    """Build Google Play AndroidPublisher service from service account JSON."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    cred_dict = json.loads(credential_json)
    credentials = service_account.Credentials.from_service_account_info(
        cred_dict,
        scopes=["https://www.googleapis.com/auth/androidpublisher"],
    )

    kwargs = {"cache_discovery": False}
    normalized_discovery_url = resolve_google_discovery_url(discovery_url)
    if normalized_discovery_url:
        kwargs["discoveryServiceUrl"] = normalized_discovery_url

    return build("androidpublisher", "v3", credentials=credentials, **kwargs)


def _build_error_result(
    *,
    error_code: str,
    message: str,
    dry_run: bool = False,
    status: str | None = None,
) -> dict:
    resolved_status = status or ("blocked" if error_code in {"missing_review_id", "missing_default_language_title"} else "failed")
    return {
        "success": False,
        "dry_run": dry_run,
        "status": resolved_status,
        "error_code": error_code,
        "message": f"[{error_code}] {message}",
    }


def _normalize_google_api_error(exc: Exception) -> tuple[str, str]:
    text = str(exc)
    status_code = getattr(getattr(exc, "resp", None), "status", None)
    lowered = text.lower()

    if status_code == 404 or " 404 " in lowered or "not found" in lowered:
        return "google_api_not_found", "Google Play API returned 404 Not Found. Verify package name, review ID, and API endpoint."

    if status_code == 403 or " 403 " in lowered or "forbidden" in lowered:
        if "default language" in lowered and "title" in lowered:
            return "missing_default_language_title", "Google Play default language title is missing. Set title in default language before committing listing edits."
        return "google_api_forbidden", "Google Play API returned 403 Forbidden. Check service-account permissions and Play Console access."

    return "google_api_error", text


def _resolve_default_language(service, package_name: str, edit_id: str) -> str:
    details = service.edits().details().get(packageName=package_name, editId=edit_id).execute()
    language = (details or {}).get("defaultLanguage", "")
    if language:
        return language

    listings = service.edits().listings().list(packageName=package_name, editId=edit_id).execute()
    items = (listings or {}).get("listings", []) or []
    if items:
        first_lang = items[0].get("language", "")
        if first_lang:
            return first_lang

    return ""


def _read_current_listing(service, package_name: str, edit_id: str, language: str) -> dict[str, str]:
    try:
        payload = service.edits().listings().get(
            packageName=package_name,
            editId=edit_id,
            language=language,
        ).execute()
    except Exception:
        # Listing may not exist yet for this locale; keep defaults empty.
        payload = {}

    return {
        "title": (payload or {}).get("title", "") or "",
        "shortDescription": (payload or {}).get("shortDescription", "") or "",
        "fullDescription": (payload or {}).get("fullDescription", "") or "",
    }


def fetch_listing(package_name: str) -> dict:
    """Fetch current app listing from Google Play (public data, no auth needed).

    Returns:
        dict with title, short_description, long_description, rating, installs, score
    """
    try:
        from google_play_scraper import app as gps_app

        result = gps_app(package_name, lang="en", country="us")
        return {
            "title": result.get("title", ""),
            "short_description": result.get("summary", ""),
            "long_description": result.get("description", ""),
            "rating": result.get("score", 0.0),
            "installs": result.get("installs", "0"),
            "ratings_count": result.get("ratings", 0),
            "reviews_count": result.get("reviews", 0),
            "price": result.get("price", 0),
            "free": result.get("free", True),
            "developer": result.get("developer", ""),
            "category": result.get("genre", ""),
        }
    except Exception as exc:
        logger.error(f"Failed to fetch listing for {package_name}: {exc}")
        return {
            "title": "",
            "short_description": "",
            "long_description": "",
            "rating": 0.0,
            "installs": "0",
            "ratings_count": 0,
            "reviews_count": 0,
        }


def fetch_reviews(package_name: str, count: int = 50) -> list[dict]:
    """Fetch recent reviews from Google Play.

    Returns:
        list of dicts with content, score, at (datetime), thumbsUpCount
    """
    try:
        from google_play_scraper import reviews, Sort

        result, _ = reviews(
            package_name,
            lang="en",
            country="us",
            sort=Sort.NEWEST,
            count=count,
        )
        return [
            {
                "review_id": r.get("reviewId", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
                "date": r.get("at").isoformat() if r.get("at") else None,
                "thumbs_up": r.get("thumbsUpCount", 0),
                "reply_content": r.get("replyContent"),
            }
            for r in result
        ]
    except Exception as exc:
        logger.error(f"Failed to fetch reviews for {package_name}: {exc}")
        return []


def get_credential_json(app_id: int, db) -> Optional[str]:
    """Retrieve decrypted service account JSON for an app.

    Returns None if no credential found.
    """
    from sqlalchemy import select
    from app.models.app_credential import AppCredential
    from app.utils.encryption import decrypt_value

    result = db.execute(
        select(AppCredential)
        .where(AppCredential.app_id == app_id)
        .where(AppCredential.credential_type == "service_account_json")
    ).scalar_one_or_none()

    if result is None:
        return None

    try:
        return decrypt_value(result.value)
    except Exception as exc:
        logger.error(f"Failed to decrypt credential for app {app_id}: {exc}")
        return None


def publish_listing(
    package_name: str,
    credential_json: str,
    title: Optional[str] = None,
    short_description: Optional[str] = None,
    long_description: Optional[str] = None,
    dry_run: bool = True,
    commit_edit: bool = True,
) -> dict:
    """Publish updated listing to Google Play via API.

    Args:
        package_name: e.g. "com.NetSafe.VPN"
        credential_json: decrypted service account JSON string
        title: new title (None = keep existing)
        short_description: new short description
        long_description: new long description
        dry_run: if True, log intent but do not call Google API

    Returns:
        dict with success, message
    """
    if dry_run:
        short_preview = repr(short_description[:30]) if short_description else None
        logger.info(
            f"[DRY RUN] Would publish to {package_name}: "
            f"title={title!r} short={short_preview}"
        )
        return {"success": True, "dry_run": True, "status": "dry_run_only", "message": "Dry run — no actual publish"}

    try:
        from app.config import get_settings

        settings = get_settings()
        service = _build_androidpublisher_service(
            credential_json=credential_json,
            discovery_url=settings.google_api_discovery_url or None,
        )

        # Open edit session
        edit = service.edits().insert(packageName=package_name, body={}).execute()
        edit_id = edit["id"]

        default_language = _resolve_default_language(service, package_name, edit_id)
        if not default_language:
            return _build_error_result(
                error_code="missing_default_language_title",
                message="Could not determine default language for Google Play listing edit.",
                dry_run=False,
                status="blocked",
            )

        existing_listing = _read_current_listing(service, package_name, edit_id, default_language)
        merged_listing: dict[str, Any] = {
            "language": default_language,
            "title": str(existing_listing.get("title", "") or ""),
            "shortDescription": str(existing_listing.get("shortDescription", "") or ""),
            "fullDescription": str(existing_listing.get("fullDescription", "") or ""),
        }

        if title is not None:
            merged_listing["title"] = title
        if short_description is not None:
            merged_listing["shortDescription"] = short_description
        if long_description is not None:
            merged_listing["fullDescription"] = long_description

        resolved_title = str(merged_listing.get("title", "") or "")
        resolved_short = str(merged_listing.get("shortDescription", "") or "")
        resolved_long = str(merged_listing.get("fullDescription", "") or "")

        if not resolved_title.strip():
            return _build_error_result(
                error_code="missing_default_language_title",
                message="This app does not have a title set for the default language.",
                dry_run=False,
                status="blocked",
            )

        merged_listing["title"] = resolved_title
        merged_listing["shortDescription"] = resolved_short
        merged_listing["fullDescription"] = resolved_long

        service.edits().listings().update(
            packageName=package_name,
            editId=edit_id,
            language=default_language,
            body=merged_listing,
        ).execute()

        if not commit_edit:
            logger.info("Saved draft listing edit %s for %s (soft publish mode)", edit_id, package_name)
            return {
                "success": True,
                "dry_run": False,
                "status": "soft_published",
                "edit_id": edit_id,
                "message": "Listing saved as draft edit (not committed).",
            }

        # Commit edit for live publish
        service.edits().commit(packageName=package_name, editId=edit_id).execute()

        logger.info(f"Successfully published listing for {package_name}")
        return {
            "success": True,
            "dry_run": False,
            "status": "published",
            "edit_id": edit_id,
            "message": "Published successfully",
        }

    except Exception as exc:
        logger.error(f"Failed to publish listing for {package_name}: {exc}")
        error_code, message = _normalize_google_api_error(exc)
        status = "blocked" if error_code in {"missing_default_language_title", "google_api_forbidden", "google_api_not_found"} else "failed"
        return _build_error_result(error_code=error_code, message=message, dry_run=False, status=status)


def commit_listing_edit(
    package_name: str,
    credential_json: str,
    edit_id: str,
) -> dict:
    if not edit_id:
        return _build_error_result(
            error_code="missing_edit_id",
            message="No Google Play edit_id is available to commit.",
            dry_run=False,
            status="blocked",
        )

    try:
        from app.config import get_settings

        settings = get_settings()
        service = _build_androidpublisher_service(
            credential_json=credential_json,
            discovery_url=settings.google_api_discovery_url or None,
        )
        service.edits().commit(packageName=package_name, editId=edit_id).execute()
        return {
            "success": True,
            "dry_run": False,
            "status": "published",
            "edit_id": edit_id,
            "message": "Draft edit committed to Google Play.",
        }
    except Exception as exc:
        logger.error("Failed to commit listing edit %s for %s: %s", edit_id, package_name, exc)
        error_code, message = _normalize_google_api_error(exc)
        status = "blocked" if error_code in {"google_api_not_found", "google_api_forbidden"} else "failed"
        return _build_error_result(error_code=error_code, message=message, dry_run=False, status=status)


def reply_to_review(
    package_name: str,
    review_id: str,
    reply_text: str,
    credential_json: str,
    dry_run: bool = True,
) -> dict:
    """Reply to a Google Play review.

    Returns:
        dict with success, message
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would reply to review {review_id} on {package_name}: {reply_text[:50]!r}")
        return {"success": True, "dry_run": True, "status": "dry_run_only", "message": "Dry run — no actual reply"}

    clean_review_id = (review_id or "").strip()
    if not clean_review_id or clean_review_id == ":":
        return _build_error_result(
            error_code="missing_review_id",
            message="Review reply is missing review_id metadata. Regenerate this suggestion from a fresh pipeline run.",
            dry_run=False,
            status="blocked",
        )

    try:
        from app.config import get_settings

        settings = get_settings()
        service = _build_androidpublisher_service(
            credential_json=credential_json,
            discovery_url=settings.google_api_discovery_url or None,
        )

        service.reviews().reply(
            packageName=package_name,
            reviewId=clean_review_id,
            body={"replyText": reply_text},
        ).execute()

        return {"success": True, "dry_run": False, "status": "published", "message": "Reply posted"}

    except Exception as exc:
        logger.error(f"Failed to reply to review {review_id}: {exc}")
        error_code, message = _normalize_google_api_error(exc)
        status = "blocked" if error_code in {"google_api_not_found", "google_api_forbidden"} else "failed"
        return _build_error_result(error_code=error_code, message=message, dry_run=False, status=status)


def verify_google_play_connection(
    package_name: str,
    credential_json: str,
    discovery_url: Optional[str] = None,
) -> dict:
    """Check whether Google Play API is reachable and credentials are valid."""
    try:
        service = _build_androidpublisher_service(
            credential_json=credential_json,
            discovery_url=discovery_url,
        )
        service.reviews().list(packageName=package_name, maxResults=1).execute()
        return {"success": True, "message": "Google Play API connection is valid"}
    except Exception as exc:
        logger.error(f"Google Play connection check failed for {package_name}: {exc}")
        return {"success": False, "message": str(exc)}
