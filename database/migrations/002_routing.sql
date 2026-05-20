-- ════════════════════════════════════════════════════════
-- Pulse-Chennai: Database Schema for Road-Aware Routing
-- ════════════════════════════════════════════════════════

-- ── Routes: Master Registry ──
CREATE TABLE IF NOT EXISTS routes (
    route_id        VARCHAR(10) PRIMARY KEY,
    route_name      VARCHAR(100) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Seed existing routes if not present
INSERT INTO routes (route_id, route_name) VALUES
    ('23C', 'Thiruvanmiyur - T Nagar'),
    ('47A', 'Anna Nagar - Koyambedu'),
    ('21B', 'Chennai Central - Tambaram'),
    ('M70', 'Adyar Signal - Chrompet')
ON CONFLICT (route_id) DO NOTHING;

-- ── Route Polylines: Complete route geometries ──
CREATE TABLE IF NOT EXISTS route_polylines (
    route_id        VARCHAR(10) PRIMARY KEY REFERENCES routes(route_id) ON DELETE CASCADE,
    polyline        TEXT NOT NULL, -- Encoded Google Polyline (precision 5) representing the road-following geometry
    stops_hash      VARCHAR(32) NOT NULL, -- MD5 hash of stop sequence to detect changes
    length_meters   INT DEFAULT 0,
    duration_seconds INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Cached Route Segments: Leg-by-leg segments for route building ──
CREATE TABLE IF NOT EXISTS cached_route_segments (
    start_stop_id   VARCHAR(20) NOT NULL,
    end_stop_id     VARCHAR(20) NOT NULL,
    polyline        TEXT NOT NULL, -- Encoded Google Polyline for the path between these two stops
    distance_meters INT NOT NULL,
    duration_seconds INT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (start_stop_id, end_stop_id)
);

CREATE INDEX IF NOT EXISTS idx_segments_start ON cached_route_segments (start_stop_id);
