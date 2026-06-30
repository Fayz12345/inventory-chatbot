import pyodbc
from ecommerce import config
from .queries import Queries

qrery = Queries()

def get_db_connection():
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={config.DB_SERVER};"
        f"DATABASE={config.DB_NAME};"
        f"UID={config.DB_USER};"
        f"PWD={config.DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    return conn


# ---------------------------------------------------------------------------
# Inventory queries
# ---------------------------------------------------------------------------

def fetch_all_pending_products():
    """Fetch all products in Ecommerce Storefront that don't have an active listing."""
    sql = qrery.fetch_all_pending_products_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def fetch_device_cost(manufacturer, model, grade):
    """Get the average DeviceCost for a product group (used for margin sanity check)."""
    sql = qrery.fetch_device_costs_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (manufacturer, model, grade))
    row = cursor.fetchone()
    conn.close()
    return float(row.AvgCost) if row and row.AvgCost else 0.0


# ---------------------------------------------------------------------------
# Product catalog lookup
# ---------------------------------------------------------------------------

def lookup_device_category(model):
    """Return a model's device category (e.g. 'Handset', 'Tablet', 'Smart Watch')
    from TelusWeeklyPricingMaster, or None if the model isn't listed there."""
    sql = qrery.lookup_device_category_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (model,))
    row = cursor.fetchone()
    conn.close()
    return row.DeviceType if row else None


def lookup_product_catalog(manufacturer, model, colour):
    """Look up ASIN, UPC, and eBay EPID from EcommerceProductCatalog."""
    sql = qrery.lookup_product_catalog_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (manufacturer, model, colour))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'asin': row.AmazonASIN,
        'upc': row.UPC,
        'epid': row.EbayEPID,
    }


# ---------------------------------------------------------------------------
# EcommerceListingsLog CRUD
# ---------------------------------------------------------------------------

def create_listing_record(product, platform, listing_price, floor_price,
                          platform_listing_id, approved_by=None):
    """Insert a new listing record after a successful marketplace post."""
    sql = qrery.create_listing_record_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (
        product['Manufacturer'], product['Model'], product['Colour'],
        product['Grade'], product['Quantity'], platform,
        listing_price, floor_price, platform_listing_id, approved_by,
    ))
    # @@IDENTITY is session-scoped (works in this separate batch); SCOPE_IDENTITY()
    # after the insert's batch returns NULL. The caller doesn't use the value, so
    # never let identity retrieval fail an already-successful insert.
    row = cursor.execute("SELECT @@IDENTITY").fetchone()
    conn.commit()
    conn.close()
    return int(row[0]) if row and row[0] is not None else None


def update_listing_status(listing_id, status):
    """Update the status of a listing (e.g. 'ended', 'sold', 'rejected')."""
    sql = qrery.update_listing_status_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (status, status, listing_id))
    conn.commit()
    conn.close()


def get_active_listings():
    """Return all active listings for reconciliation."""
    sql = qrery.get_active_listings_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_listing_by_id(listing_id):
    """Fetch a single listing record by ID."""
    sql = qrery.get_listing_by_id_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (listing_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    columns = [col[0] for col in cursor.description]
    conn.close()
    return dict(zip(columns, row))


# ---------------------------------------------------------------------------
# Pricing batches & recommendations (dashboard persistence)
# ---------------------------------------------------------------------------

def create_pricing_batch():
    """Create a new pricing batch and return its ID."""
    sql = qrery.create_pricing_batch_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    batch_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
    conn.close()
    return int(batch_id)


def insert_recommendation(batch_id, rec):
    """Insert a single pricing recommendation into the database."""
    product = rec['product']
    sql = qrery.insert_recommendation_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (
        batch_id,
        product['Manufacturer'], product['Model'],
        product['Colour'], product['Grade'], product['Quantity'],
        rec.get('marketplace'), rec.get('price'),
        rec.get('amazon_price'), rec.get('ebay_price'),
        rec.get('bestbuy_price'), rec.get('reebelo_price'),
        rec.get('device_cost'),
        1 if rec.get('margin_ok') else 0,
        rec.get('skip_reason'),
    ))
    conn.commit()
    conn.close()


def update_batch_status(batch_id, status):
    """Update a batch status (e.g. 'ready', 'completed')."""
    sql = qrery.update_batch_status_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (status, batch_id))
    conn.commit()
    conn.close()


def get_latest_batch():
    """Return the most recent pricing batch."""
    sql = qrery.get_latest_batch_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {'ID': row.ID, 'CreatedAt': row.CreatedAt, 'Status': row.Status}


def get_batch_by_id(batch_id):
    """Return a specific pricing batch."""
    sql = qrery.get_batch_by_id_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (batch_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {'ID': row.ID, 'CreatedAt': row.CreatedAt, 'Status': row.Status}


def get_recommendations_for_batch(batch_id):
    """Return all recommendations for a batch, ordered by ID."""
    sql = qrery.get_recommendations_for_batch_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (batch_id,))
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recommendation_by_id(rec_id):
    """Return a single recommendation."""
    sql = qrery.get_recommendation_by_id_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (rec_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def update_recommendation_decision(rec_id, decision):
    """Set the decision ('approved' or 'rejected') on a recommendation."""
    sql = qrery.update_recommendation_decision_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (decision, rec_id))
    conn.commit()
    conn.close()


def claim_recommendation(rec_id, decision):
    """Atomically claim an undecided recommendation, setting it to `decision`
    (e.g. 'processing' or 'rejected'). Returns True iff this call won the row
    (Decision was NULL). Prevents double-post on concurrent approves (#198)."""
    sql = qrery.claim_recommendation_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (decision, rec_id))
    claimed = cursor.rowcount == 1
    conn.commit()
    conn.close()
    return claimed


def release_recommendation(rec_id):
    """Release a claimed recommendation back to undecided (rollback path)."""
    sql = qrery.release_recommendation_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (rec_id,))
    conn.commit()
    conn.close()


def get_all_batches():
    """Return all pricing batches, newest first."""
    sql = qrery.get_all_batches_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def find_stale_listings():
    """Find active listings whose product group is no longer in Ecommerce Storefront."""
    sql = qrery.find_stale_listings_query
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows
