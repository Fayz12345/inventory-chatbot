"""
Class to handle all query
"""
class Queries:

    @property
    def fetch_all_pending_products_query(self):
        """Fetch all products in Ecommerce Storefront that don't have an active listing."""
        return """
            SELECT Manufacturer, Model, Colour, Grade, COUNT(*) AS Quantity
                FROM ReportingInventoryFlat r
                WHERE Product_Place = 'E-Commerce Store Front'
                AND NOT EXISTS (
                    SELECT 1 
                    FROM EcommerceListingsLog l
                    WHERE l.Manufacturer = r.Manufacturer
                        AND l.Model = r.Model
                        AND l.Grade = r.Grade
                        AND l.Colour = r.Colour
                        AND l.Status = 'active'
                )
                GROUP BY Manufacturer, Model, Colour, Grade
                ORDER BY Quantity DESC;
        """
    
    @property
    def fetch_device_costs_query(self):
        """Get the average DeviceCost for a product group (used for margin sanity check)."""
        return """
            SELECT AVG(DeviceCost) AS AvgCost
            FROM ReportingInventoryFlat
            WHERE Manufacturer = ? AND Model = ? AND Grade = ?
            AND Product_Place = 'E-Commerce Store Front'
        """

    @property
    def lookup_device_category_query(self):
        """Look up a model's device category (Handset/Tablet/Smart Watch/Laptop/
        Modem/Phone) from the Telus pricing master — used to pick the Amazon
        productType (#198/1D.10 #3). Keyed by Model; ~half of storefront models
        have no row, so callers must default."""
        return """
            SELECT TOP 1 DeviceType
            FROM TelusWeeklyPricingMaster
            WHERE Model = ?
        """

    # -- Scrape-scope settings (single row, Id = 1) -------------------------
    @property
    def create_scrape_settings_table_query(self):
        """DDL for the scrape-scope settings table. Run ONCE on the bridge SQL
        Server (the app has no local DB). A single row (Id = 1) holds which
        product categories the weekly pipeline scrapes + all-vs-top-N-by-model."""
        return """
            CREATE TABLE EcommerceScrapeSettings (
                Id         INT           NOT NULL PRIMARY KEY DEFAULT 1,
                Categories NVARCHAR(200) NOT NULL,   -- JSON, e.g. ["phone","wearable","tablet"]
                ScopeMode  VARCHAR(10)   NOT NULL DEFAULT 'all',   -- 'all' | 'top'
                TopN       INT           NOT NULL DEFAULT 30,
                UpdatedAt  DATETIME      NOT NULL DEFAULT GETDATE(),
                UpdatedBy  NVARCHAR(100) NULL,
                CONSTRAINT CK_EcommerceScrapeSettings_Single CHECK (Id = 1)
            );
        """

    @property
    def get_scrape_settings_query(self):
        return """
            SELECT TOP 1 Categories, ScopeMode, TopN, UpdatedAt, UpdatedBy
            FROM EcommerceScrapeSettings
            WHERE Id = 1
        """

    @property
    def update_scrape_settings_query(self):
        return """
            UPDATE EcommerceScrapeSettings
            SET Categories = ?, ScopeMode = ?, TopN = ?, UpdatedAt = GETDATE(), UpdatedBy = ?
            WHERE Id = 1
        """

    @property
    def insert_scrape_settings_query(self):
        return """
            INSERT INTO EcommerceScrapeSettings (Id, Categories, ScopeMode, TopN, UpdatedAt, UpdatedBy)
            VALUES (1, ?, ?, ?, GETDATE(), ?)
        """

    @property
    def lookup_product_catalog_query(self):
        """Look up ASIN, UPC, and eBay EPID from EcommerceProductCatalog.

        Match is space- and case-insensitive: catalog Model strings drift from the
        storefront spelling (e.g. catalog "iPhone 16 Pro Max 256GB" vs inventory
        "256 GB", or "R895(Galaxy..." vs "R895 (Galaxy..."), and an exact `=` join
        silently orphans those rows. Stripping spaces + uppercasing both sides makes
        the seeded UPC/ASIN findable regardless of spacing/case. The table is tiny
        (catalog seeding), so the non-sargable comparison is fine."""
        return """
            SELECT AmazonASIN, UPC, EbayEPID
            FROM EcommerceProductCatalog
            WHERE REPLACE(UPPER(Manufacturer), ' ', '') = REPLACE(UPPER(?), ' ', '')
              AND REPLACE(UPPER(Model), ' ', '')        = REPLACE(UPPER(?), ' ', '')
              AND REPLACE(UPPER(Colour), ' ', '')       = REPLACE(UPPER(?), ' ', '')
        """
    
    @property
    def create_listing_record_query(self):
        """Insert a new listing record after a successful marketplace post."""
        return """
            INSERT INTO EcommerceListingsLog
                (Manufacturer, Model, Colour, Grade, Quantity, Platform,
                ListingPrice, FloorPriceAtListing, PlatformListingID, Status, ApprovedBy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """
    
    @property
    def update_listing_status_query(self):
        """Update the status of a listing (e.g. 'ended', 'sold', 'rejected')."""
        return """
            UPDATE EcommerceListingsLog
            SET Status = ?, EndedAt = CASE WHEN ? IN ('ended', 'sold') THEN GETDATE() ELSE EndedAt END
            WHERE ID = ?
        """
        
    @property
    def get_active_listings_query(self):
        """Return all active listings for reconciliation."""
        return """
            SELECT ID, Manufacturer, Model, Colour, Grade, Platform, PlatformListingID
            FROM EcommerceListingsLog
            WHERE Status = 'active'
        """
        
    @property
    def get_listing_by_id_query(self):
        """Fetch a single listing record by ID."""
        return "SELECT * FROM EcommerceListingsLog WHERE ID = ?"
    
    @property
    def create_pricing_batch_query(self):
        """Create a new pricing batch and return its ID."""
        return """
            INSERT INTO EcommercePricingBatch (Status)
            VALUES ('pending')
        """

    @property
    def create_pricing_batch_returning_id_query(self):
        """Create a pricing batch and return its new ID in one round-trip.
        OUTPUT INSERTED.ID is reliable regardless of scope/commit ordering (unlike
        a separate SELECT SCOPE_IDENTITY() after a commit)."""
        return """
            INSERT INTO EcommercePricingBatch (Status)
            OUTPUT INSERTED.ID
            VALUES ('pending')
        """
        
    @property
    def insert_recommendation_query(self):
        """Insert a single pricing recommendation into the database."""
        return """
            INSERT INTO EcommercePricingRecommendation
                (BatchID, Manufacturer, Model, Colour, Grade, Quantity,
                RecommendedMarketplace, RecommendedPrice,
                AmazonFloor, EbayFloor, BestBuyFloor, ReebeloFloor,
                DeviceCost, MarginOK, SkipReason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
    @property
    def update_batch_status_query(self):
        """Update a batch status (e.g. 'ready', 'completed')."""
        return "UPDATE EcommercePricingBatch SET Status = ? WHERE ID = ?"
    
    @property
    def get_latest_batch_query(self):
        """Return the most recent pricing batch."""
        return """
            SELECT TOP 1 ID, CreatedAt, Status
            FROM EcommercePricingBatch
            ORDER BY CreatedAt DESC
        """
        
    @property
    def get_batch_by_id_query(self):
        """Return a specific pricing batch."""
        return "SELECT ID, CreatedAt, Status FROM EcommercePricingBatch WHERE ID = ?"
        
    @property
    def get_recommendations_for_batch_query(self):
        """Return all recommendations for a batch, ordered by ID."""
        return """
            SELECT ID, BatchID, Manufacturer, Model, Colour, Grade, Quantity,
                RecommendedMarketplace, RecommendedPrice,
                AmazonFloor, EbayFloor, BestBuyFloor, ReebeloFloor,
                DeviceCost, MarginOK, SkipReason, Decision, DecidedAt
            FROM EcommercePricingRecommendation
            WHERE BatchID = ?
            ORDER BY ID
        """
        
    @property
    def get_recommendation_by_id_query(self):
        """Return a single recommendation."""
        return """
            SELECT ID, BatchID, Manufacturer, Model, Colour, Grade, Quantity,
                RecommendedMarketplace, RecommendedPrice,
                AmazonFloor, EbayFloor, BestBuyFloor, ReebeloFloor,
                DeviceCost, MarginOK, SkipReason, Decision, DecidedAt
            FROM EcommercePricingRecommendation
            WHERE ID = ?
        """
        
    @property
    def update_recommendation_decision_query(self):
        """Set the decision ('approved' or 'rejected') on a recommendation."""
        return """
            UPDATE EcommercePricingRecommendation
            SET Decision = ?, DecidedAt = GETDATE()
            WHERE ID = ?
        """

    @property
    def claim_recommendation_query(self):
        """Atomically claim an undecided recommendation (race guard, #198/1D.10).
        Only succeeds if Decision IS NULL — caller checks rowcount == 1."""
        return """
            UPDATE EcommercePricingRecommendation
            SET Decision = ?, DecidedAt = GETDATE()
            WHERE ID = ? AND Decision IS NULL
        """

    @property
    def release_recommendation_query(self):
        """Release a claimed recommendation back to undecided (rollback path)."""
        return """
            UPDATE EcommercePricingRecommendation
            SET Decision = NULL, DecidedAt = NULL
            WHERE ID = ?
        """
        
    @property
    def get_all_batches_query(self):
        """Return all pricing batches, newest first."""
        return """
            SELECT ID, CreatedAt, Status
            FROM EcommercePricingBatch
            ORDER BY CreatedAt DESC
        """
        
    @property
    def find_stale_listings_query(self):
        """Find active listings whose product group is no longer in Ecommerce Storefront."""
        return """
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