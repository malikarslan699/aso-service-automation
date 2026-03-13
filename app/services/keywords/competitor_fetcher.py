"""Competitor app metadata fetcher for keyword discovery."""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Default VPN competitors on Google Play
COMPETITORS: dict[str, list[str]] = {
    "vpn": [
        "com.expressvpn.vpn",
        "com.nordvpn.android",
        "com.surfshark.vpnclient.android",
        "ch.protonvpn.android",
        "free.vpn.unblock.proxy.turbovpn",
        "vpn.thunder.free",
        "com.privateinternetaccess.android",
        "com.hotspotshield.android.vpn",
    ]
}


def fetch_competitor_metadata(package_name: str) -> dict | None:
    """Fetch metadata for a single competitor app.

    Returns:
        dict with package_name, title, short_description, long_description,
        rating, installs, category — or None on failure.
    """
    try:
        from google_play_scraper import app as gps_app

        result = gps_app(package_name, lang="en", country="us")
        return {
            "package_name": package_name,
            "title": result.get("title", ""),
            "short_description": result.get("summary", ""),
            "long_description": result.get("description", ""),
            "rating": result.get("score", 0.0),
            "installs": result.get("installs", "0"),
            "category": result.get("genre", ""),
        }
    except Exception as exc:
        logger.warning(f"Could not fetch competitor {package_name}: {exc}")
        return None


def fetch_all_competitors(category: str = "vpn", max_workers: int = 4) -> list[dict]:
    """Fetch metadata for all competitors in the given category in parallel.

    Args:
        category: category key in COMPETITORS dict (default "vpn")
        max_workers: parallel fetch workers

    Returns:
        list of competitor metadata dicts (failed fetches excluded)
    """
    package_names = COMPETITORS.get(category, [])
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_competitor_metadata, pkg): pkg
            for pkg in package_names
        }
        for future in as_completed(futures):
            data = future.result()
            if data is not None:
                results.append(data)

    logger.info(f"Fetched {len(results)}/{len(package_names)} competitors for category={category!r}")
    return results
