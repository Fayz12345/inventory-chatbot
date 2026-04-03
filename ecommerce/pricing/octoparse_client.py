"""
Octoparse Cloud API client.

Handles the full lifecycle: create task from template → poll until done → export JSON.
Uses the Octoparse Advanced API (v2) with token-based auth.
"""

import logging
import time
import requests

from ecommerce import config

log = logging.getLogger(__name__)

BASE_URL = 'https://openapi.octoparse.com'
POLL_INTERVAL = 30  # seconds between status checks
MAX_POLL_TIME = 600  # 10 minutes max wait


def _headers():
    return {
        'Authorization': f'Bearer {config.OCTOPARSE_API_KEY}',
        'Content-Type': 'application/json',
    }


def _get_access_token():
    """Exchange API key for a short-lived access token if needed."""
    # Octoparse Advanced API uses token auth directly via the API key
    # If the API requires OAuth-style token exchange, this method handles it
    resp = requests.post(
        f'{BASE_URL}/token',
        data={
            'username': '',
            'password': '',
            'grant_type': 'apikey',
            'apikey': config.OCTOPARSE_API_KEY,
        },
    )
    if resp.status_code == 200:
        return resp.json().get('access_token')
    # Fall back to using the API key directly as bearer token
    return config.OCTOPARSE_API_KEY


def run_task(template_name, parameters, task_name=None, target_max_rows=50):
    """
    Create and run an Octoparse cloud task from a template.

    Args:
        template_name: Octoparse template identifier (e.g. 'amazon-product-details-scraper')
        parameters: dict of business parameters matching the template's parameterHints
        task_name: optional friendly name for the task
        target_max_rows: stop extraction after this many rows (first-page safety cap)

    Returns:
        task_id (str) if task was created and started, None on failure.
    """
    payload = {
        'templateName': template_name,
        'parameters': parameters,
        'targetMaxRows': target_max_rows,
    }
    if task_name:
        payload['taskName'] = task_name

    try:
        resp = requests.post(
            f'{BASE_URL}/v2/task/execute',
            headers=_headers(),
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get('data', {}).get('taskId') or data.get('taskId')
        if task_id:
            log.info("Octoparse task created: %s (template: %s)", task_id, template_name)
            return task_id

        log.error("No taskId in response: %s", data)
        return None

    except requests.RequestException as e:
        log.error("Failed to create Octoparse task (template: %s): %s", template_name, e)
        return None


def poll_until_done(task_id):
    """
    Poll an Octoparse task until it completes, fails, or times out.

    Returns:
        'completed', 'failed', or 'timeout'
    """
    start = time.time()
    while time.time() - start < MAX_POLL_TIME:
        try:
            resp = requests.get(
                f'{BASE_URL}/v2/task/{task_id}/status',
                headers=_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            status = (
                data.get('data', {}).get('status', '').lower()
                or data.get('status', '').lower()
            )

            if status in ('completed', 'stopped'):
                log.info("Task %s completed.", task_id)
                return 'completed'
            if status == 'failed':
                log.error("Task %s failed.", task_id)
                return 'failed'

            log.debug("Task %s still running (status: %s)...", task_id, status)

        except requests.RequestException as e:
            log.warning("Error polling task %s: %s — retrying", task_id, e)

        time.sleep(POLL_INTERVAL)

    log.warning("Task %s timed out after %ds.", task_id, MAX_POLL_TIME)
    return 'timeout'


def export_data(task_id, file_type='JSON'):
    """
    Export scraped data from a completed Octoparse task.

    Args:
        task_id: the Octoparse task ID
        file_type: export format (JSON, CSV, EXCEL, etc.)

    Returns:
        list of dicts (parsed JSON rows), or empty list on failure.
    """
    try:
        resp = requests.get(
            f'{BASE_URL}/v2/task/{task_id}/export',
            headers=_headers(),
            params={'fileType': file_type},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        rows = data.get('data', {}).get('rows', []) or data.get('rows', [])
        if not rows:
            # Try sampleData fallback
            rows = data.get('data', {}).get('sampleData', []) or []

        log.info("Exported %d rows from task %s.", len(rows), task_id)
        return rows

    except requests.RequestException as e:
        log.error("Failed to export data from task %s: %s", task_id, e)
        return []


def scrape(template_name, parameters, task_name=None, target_max_rows=50):
    """
    Full scraping lifecycle: create task → poll → export.
    Retries once on failure, as per the plan.

    Args:
        template_name: Octoparse template identifier
        parameters: business parameters dict
        task_name: optional friendly name
        target_max_rows: row cap

    Returns:
        list of dicts (scraped rows), or empty list on failure.
    """
    for attempt in range(2):
        task_id = run_task(template_name, parameters, task_name, target_max_rows)
        if not task_id:
            if attempt == 0:
                log.warning("Task creation failed for %s — retrying once", template_name)
                continue
            return []

        status = poll_until_done(task_id)
        if status == 'failed':
            if attempt == 0:
                log.warning("Task %s failed — retrying once", task_id)
                continue
            return []

        # Export even on timeout — partial data may be available
        return export_data(task_id)

    return []
