import pyodbc
from ecommerce import config


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
    sql = """
        SELECT Manufacturer, Model, Colour, Grade, COUNT(*) AS Quantity
        FROM ReportingInventoryFlat r
        WHERE Product_Place = 'E-Commerce Store Front'
          AND NOT EXISTS (
              SELECT 1 FROM EcommerceListingsLog l
              WHERE l.Manufacturer = r.Manufacturer
                AND l.Model = r.Model
                AND l.Grade = r.Grade
                AND l.Colour = r.Colour
                AND l.Status = 'active'
          )
        GROUP BY Manufacturer, Model, Colour, Grade
        ORDER BY Quantity DESC
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def fetch_device_cost(manufacturer, model, grade):
    """Get the average DeviceCost for a product group (used for margin sanity check)."""
    sql = """
        SELECT AVG(DeviceCost) AS AvgCost
        FROM ReportingInventoryFlat
        WHERE Manufacturer = ? AND Model = ? AND Grade = ?
          AND Product_Place = 'E-Commerce Store Front'
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (manufacturer, model, grade))
    row = cursor.fetchone()
    conn.close()
    return float(row.AvgCost) if row and row.AvgCost else 0.0


# ---------------------------------------------------------------------------
# Product catalog lookup
# ---------------------------------------------------------------------------

def lookup_product_catalog(manufacturer, model, colour):
    """Look up ASIN, UPC, and eBay EPID from EcommerceProductCatalog."""
    sql = """
        SELECT AmazonASIN, UPC, EbayEPID
        FROM EcommerceProductCatalog
        WHERE Manufacturer = ? AND Model = ? AND Colour = ?
    """
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
    sql = """
        INSERT INTO EcommerceListingsLog
            (Manufacturer, Model, Colour, Grade, Quantity, Platform,
             ListingPrice, FloorPriceAtListing, PlatformListingID, Status, ApprovedBy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (
        product['Manufacturer'], product['Model'], product['Colour'],
        product['Grade'], product['Quantity'], platform,
        listing_price, floor_price, platform_listing_id, approved_by,
    ))
    conn.commit()
    listing_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
    conn.close()
    return int(listing_id)


def update_listing_status(listing_id, status):
    """Update the status of a listing (e.g. 'ended', 'sold', 'rejected')."""
    sql = """
        UPDATE EcommerceListingsLog
        SET Status = ?, EndedAt = CASE WHEN ? IN ('ended', 'sold') THEN GETDATE() ELSE EndedAt END
        WHERE ID = ?
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (status, status, listing_id))
    conn.commit()
    conn.close()


def get_active_listings():
    """Return all active listings for reconciliation."""
    sql = """
        SELECT ID, Manufacturer, Model, Colour, Grade, Platform, PlatformListingID
        FROM EcommerceListingsLog
        WHERE Status = 'active'
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_listing_by_id(listing_id):
    """Fetch a single listing record by ID."""
    sql = "SELECT * FROM EcommerceListingsLog WHERE ID = ?"
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
    sql = """
        INSERT INTO EcommercePricingBatch (Status)
        VALUES ('pending')
    """
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
    sql = """
        INSERT INTO EcommercePricingRecommendation
            (BatchID, Manufacturer, Model, Colour, Grade, Quantity,
             RecommendedMarketplace, RecommendedPrice,
             AmazonFloor, EbayFloor, BestBuyFloor, ReebeloFloor,
             DeviceCost, MarginOK, SkipReason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
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
    sql = "UPDATE EcommercePricingBatch SET Status = ? WHERE ID = ?"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (status, batch_id))
    conn.commit()
    conn.close()


def get_latest_batch():
    """Return the most recent pricing batch."""
    sql = """
        SELECT TOP 1 ID, CreatedAt, Status
        FROM EcommercePricingBatch
        ORDER BY CreatedAt DESC
    """
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
    sql = "SELECT ID, CreatedAt, Status FROM EcommercePricingBatch WHERE ID = ?"
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
    sql = """
        SELECT ID, BatchID, Manufacturer, Model, Colour, Grade, Quantity,
               RecommendedMarketplace, RecommendedPrice,
               AmazonFloor, EbayFloor, BestBuyFloor, ReebeloFloor,
               DeviceCost, MarginOK, SkipReason, Decision, DecidedAt
        FROM EcommercePricingRecommendation
        WHERE BatchID = ?
        ORDER BY ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (batch_id,))
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recommendation_by_id(rec_id):
    """Return a single recommendation."""
    sql = """
        SELECT ID, BatchID, Manufacturer, Model, Colour, Grade, Quantity,
               RecommendedMarketplace, RecommendedPrice,
               AmazonFloor, EbayFloor, BestBuyFloor, ReebeloFloor,
               DeviceCost, MarginOK, SkipReason, Decision, DecidedAt
        FROM EcommercePricingRecommendation
        WHERE ID = ?
    """
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
    sql = """
        UPDATE EcommercePricingRecommendation
        SET Decision = ?, DecidedAt = GETDATE()
        WHERE ID = ?
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (decision, rec_id))
    conn.commit()
    conn.close()


def get_all_batches():
    """Return all pricing batches, newest first."""
    sql = """
        SELECT ID, CreatedAt, Status
        FROM EcommercePricingBatch
        ORDER BY CreatedAt DESC
    """
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
    sql = """
        SELECT l.ID, l.Manufacturer, l.Model, l.Colour, l.Grade,
               l.Platform, l.PlatformListingID
        FROM EcommerceListingsLog l
        WHERE l.Status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM ReportingInventoryFlat r
              WHERE r.Manufacturer = l.Manufacturer
                AND r.Model = l.Model
                AND r.Grade = l.Grade
                AND r.Colour = l.Colour
                AND r.Product_Place = 'E-Commerce Store Front'
          )
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows
