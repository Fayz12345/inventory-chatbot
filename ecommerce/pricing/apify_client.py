"""
Apify Cloud API client.

Wraps the Apify Python SDK to run actors (scrapers), poll for completion,
and retrieve structured results. Replaces the Octoparse client.
"""

import logging
import time

from apify_client import ApifyClient

from ecommerce import config

log = logging.getLogger(__name__)

_client = None

# Brief backoff between attempts. Long enough to clear a momentary marketplace
# rate-limit on the actor's proxy pool, short enough not to bloat the weekly
# cron's wall-clock budget (worst case: 4 actors × N retries × this delay).
RETRY_BACKOFF_SECONDS = 30


def _get_client():
    """Lazily initialize the Apify client."""
    global _client
    if _client is None:
        _client = ApifyClient(config.APIFY_API_TOKEN)
    return _client


def _run_actor_once(client, actor_id, run_input, timeout_secs):
    """One actor invocation. Returns the dataset items, or None on non-SUCCEEDED."""
    log.info("Starting Apify actor '%s'...", actor_id)
    run = client.actor(actor_id).call(
        run_input=run_input,
        timeout_secs=timeout_secs,
    )

    status = run.get('status')
    if status != 'SUCCEEDED':
        log.error("Actor '%s' finished with status: %s", actor_id, status)
        return None

    dataset_id = run.get('defaultDatasetId')
    if not dataset_id:
        log.error("No dataset returned from actor '%s'", actor_id)
        return None

    items = client.dataset(dataset_id).list_items().items
    log.info("Actor '%s' returned %d items.", actor_id, len(items))
    return items


def run_actor(actor_id, run_input, timeout_secs=600, max_retries=1):
    """
    Run an Apify actor and return the results, with one transient-failure retry.

    Args:
        actor_id: actor slug (e.g. 'automation-lab/amazon-scraper')
        run_input: dict of input parameters for the actor
        timeout_secs: max wait time per attempt in seconds (default 10 min)
        max_retries: retries on non-SUCCEEDED status. Default 1 = one retry
            after RETRY_BACKOFF_SECONDS (handles transient marketplace
            rate-limits, e.g. eBay/Reebelo intermittently 403-ing the proxy
            pool). Set 0 to disable.

    Returns:
        list of dicts (result items), or empty list on failure after all retries.
    """
    client = _get_client()

    for attempt in range(max_retries + 1):
        if attempt > 0:
            log.warning(
                "Retrying Apify actor '%s' (attempt %d of %d) after %ds backoff...",
                actor_id, attempt + 1, max_retries + 1, RETRY_BACKOFF_SECONDS,
            )
            time.sleep(RETRY_BACKOFF_SECONDS)
        try:
            items = _run_actor_once(client, actor_id, run_input, timeout_secs)
            if items is not None:
                return items
        except Exception as e:
            log.error("Apify actor '%s' raised: %s", actor_id, e)

    log.error("Apify actor '%s' failed after %d attempt(s).", actor_id, max_retries + 1)
    return []
