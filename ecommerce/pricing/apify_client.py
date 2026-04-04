"""
Apify Cloud API client.

Wraps the Apify Python SDK to run actors (scrapers), poll for completion,
and retrieve structured results. Replaces the Octoparse client.
"""

import logging
from apify_client import ApifyClient

from ecommerce import config

log = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazily initialize the Apify client."""
    global _client
    if _client is None:
        _client = ApifyClient(config.APIFY_API_TOKEN)
    return _client


def run_actor(actor_id, run_input, timeout_secs=600):
    """
    Run an Apify actor and return the results.

    Args:
        actor_id: actor slug (e.g. 'automation-lab/amazon-scraper')
        run_input: dict of input parameters for the actor
        timeout_secs: max wait time in seconds (default 10 min)

    Returns:
        list of dicts (result items), or empty list on failure.
    """
    client = _get_client()

    try:
        log.info("Starting Apify actor '%s'...", actor_id)
        run = client.actor(actor_id).call(
            run_input=run_input,
            timeout_secs=timeout_secs,
        )

        status = run.get('status')
        if status != 'SUCCEEDED':
            log.error("Actor '%s' finished with status: %s", actor_id, status)
            return []

        dataset_id = run.get('defaultDatasetId')
        if not dataset_id:
            log.error("No dataset returned from actor '%s'", actor_id)
            return []

        items = client.dataset(dataset_id).list_items().items
        log.info("Actor '%s' returned %d items.", actor_id, len(items))
        return items

    except Exception as e:
        log.error("Apify actor '%s' failed: %s", actor_id, e)
        return []
