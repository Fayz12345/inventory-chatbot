import pyodbc
from datetime import date, timedelta
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


def _prev_business_day(today=None):
    """Return the previous business day. Monday -> Friday, otherwise yesterday."""
    today = today or date.today()
    if today.weekday() == 0:  # Monday
        return today - timedelta(days=3)
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)
    else:
        return today - timedelta(days=1)


# ---------------------------------------------------------------------------
# Inventory queries
# ---------------------------------------------------------------------------

def fetch_new_ecommerce_products(prev_bday=None):
    """Primary query: devices placed into Ecommerce Storefront on the previous business day."""
    prev_bday = prev_bday or _prev_business_day()
    sql = """
        SELECT Manufacturer, Model, Colour, Grade, COUNT(*) AS Quantity
        FROM ReportingInventoryFlat
        WHERE Product_Place = 'Ecommerce Storefront'
          AND CAST(Product_Placement_Created AS DATE) = ?
        GROUP BY Manufacturer, Model, Colour, Grade
        ORDER BY Quantity DESC
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (prev_bday,))
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def fetch_unlisted_ecommerce_products():
    """Fallback query: devices in Ecommerce Storefront with no active listing record."""
    sql = """
        SELECT Manufacturer, Model, Colour, Grade, COUNT(*) AS Quantity
        FROM ReportingInventoryFlat r
        WHERE Product_Place = 'Ecommerce Storefront'
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


def fetch_all_pending_products():
    """Merge primary + fallback queries, deduplicated by product group key."""
    primary = fetch_new_ecommerce_products()
    fallback = fetch_unlisted_ecommerce_products()

    seen = set()
    merged = []
    for row in primary + fallback:
        key = (row['Manufacturer'], row['Model'], row['Colour'], row['Grade'])
        if key not in seen:
            seen.add(key)
            merged.append(row)
    return merged


def fetch_device_cost(manufacturer, model, grade):
    """Get the average DeviceCost for a product group (used for margin sanity check)."""
    sql = """
        SELECT AVG(DeviceCost) AS AvgCost
        FROM ReportingInventoryFlat
        WHERE Manufacturer = ? AND Model = ? AND Grade = ?
          AND Product_Place = 'Ecommerce Storefront'
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
        SELECT AmazonASIN, UPC, EbayEPID, Storage
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
        'storage': row.Storage,
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
                AND r.Product_Place = 'Ecommerce Storefront'
          )
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows
