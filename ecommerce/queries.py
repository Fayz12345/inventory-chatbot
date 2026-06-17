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
    def lookup_product_catalog_query(self):
        """Look up ASIN, UPC, and eBay EPID from EcommerceProductCatalog."""
        return """
            SELECT AmazonASIN, UPC, EbayEPID
            FROM EcommerceProductCatalog
            WHERE Manufacturer = ? AND Model = ? AND Colour = ?
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