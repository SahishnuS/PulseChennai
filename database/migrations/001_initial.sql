-- ════════════════════════════════════════════════════════
-- Pulse-Chennai: PostGIS Database Schema
-- ════════════════════════════════════════════════════════
-- Run against PostgreSQL 15+ with PostGIS 3.3+ extension.
-- Auto-executed by docker-compose on first startup.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Buses: Live fleet registry ──
CREATE TABLE IF NOT EXISTS buses (
    bus_id          VARCHAR(20) PRIMARY KEY,
    route_id        VARCHAR(10) NOT NULL,
    device_health_score FLOAT DEFAULT 1.0,
    is_ghost        BOOLEAN DEFAULT FALSE,
    last_seen       TIMESTAMPTZ,
    current_location GEOGRAPHY(POINT, 4326),
    current_speed_kmph FLOAT DEFAULT 0.0,
    heading         FLOAT DEFAULT 0.0,
    h3_cell_id      VARCHAR(20),
    passenger_count INT DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'offline',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buses_location ON buses USING GIST (current_location);
CREATE INDEX IF NOT EXISTS idx_buses_route ON buses (route_id);
CREATE INDEX IF NOT EXISTS idx_buses_ghost ON buses (is_ghost) WHERE is_ghost = TRUE;
CREATE INDEX IF NOT EXISTS idx_buses_h3 ON buses (h3_cell_id);

-- ── GPS Pings: Partitioned time-series telemetry ──
CREATE TABLE IF NOT EXISTS gps_pings (
    id              BIGSERIAL,
    bus_id          VARCHAR(20) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    raw_lat         FLOAT NOT NULL,
    raw_lon         FLOAT NOT NULL,
    location        GEOGRAPHY(POINT, 4326),
    reported_speed_kmph FLOAT,
    heading         FLOAT,
    jitter_score    FLOAT,
    accuracy_meters FLOAT,
    h3_cell_id      VARCHAR(20),
    source          VARCHAR(20) DEFAULT 'AIS140',
    hw_score_at_ping FLOAT,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Create partitions for current and next month
DO $$
DECLARE
    start_date DATE := DATE_TRUNC('month', CURRENT_DATE);
    end_date DATE := start_date + INTERVAL '1 month';
    next_end DATE := end_date + INTERVAL '1 month';
    part_name TEXT;
    next_part_name TEXT;
BEGIN
    part_name := 'gps_pings_' || TO_CHAR(start_date, 'YYYY_MM');
    next_part_name := 'gps_pings_' || TO_CHAR(end_date, 'YYYY_MM');

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF gps_pings FOR VALUES FROM (%L) TO (%L)',
        part_name, start_date, end_date
    );
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF gps_pings FOR VALUES FROM (%L) TO (%L)',
        next_part_name, end_date, next_end
    );
END $$;

CREATE INDEX IF NOT EXISTS idx_pings_bus_time ON gps_pings (bus_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pings_h3 ON gps_pings (h3_cell_id);

-- ── Ghost Bus Events: Audit trail ──
CREATE TABLE IF NOT EXISTS ghost_bus_events (
    id              BIGSERIAL PRIMARY KEY,
    bus_id          VARCHAR(20) NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    health_score_at_detection FLOAT NOT NULL,
    trigger_reason  TEXT,
    recovered_at    TIMESTAMPTZ,
    recovery_source VARCHAR(20),
    recovery_lat    FLOAT,
    recovery_lon    FLOAT,
    passenger_ping_count INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ghost_bus ON ghost_bus_events (bus_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_ghost_unresolved ON ghost_bus_events (recovered_at) WHERE recovered_at IS NULL;

-- ── Route Stops: Static reference data ──
CREATE TABLE IF NOT EXISTS route_stops (
    stop_id         VARCHAR(20) PRIMARY KEY,
    route_id        VARCHAR(10) NOT NULL,
    stop_name       VARCHAR(100) NOT NULL,
    sequence_order  INT NOT NULL,
    location        GEOGRAPHY(POINT, 4326) NOT NULL,
    h3_cell_id      VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stops_route ON route_stops (route_id, sequence_order);
CREATE INDEX IF NOT EXISTS idx_stops_location ON route_stops USING GIST (location);

-- ── ETA Predictions: Model output log ──
CREATE TABLE IF NOT EXISTS eta_predictions (
    id              BIGSERIAL PRIMARY KEY,
    bus_id          VARCHAR(20) NOT NULL,
    stop_id         VARCHAR(20),
    predicted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    eta_seconds     INT NOT NULL,
    confidence      FLOAT NOT NULL,
    model_version   VARCHAR(20) DEFAULT 'v1',
    was_accurate    BOOLEAN,
    actual_arrival  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_eta_bus ON eta_predictions (bus_id, predicted_at DESC);

-- ── TomTom Traffic Snapshots ──
CREATE TABLE IF NOT EXISTS tomtom_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    segment_label   VARCHAR(100) NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lat             FLOAT NOT NULL,
    lon             FLOAT NOT NULL,
    current_speed_kmph FLOAT,
    free_flow_speed_kmph FLOAT,
    gridlock_ratio  FLOAT,
    confidence      FLOAT,
    road_closure    BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_tomtom_segment ON tomtom_snapshots (segment_label, captured_at DESC);

-- ── Seed Chennai MTC Route Stops ──
INSERT INTO route_stops (stop_id, route_id, stop_name, sequence_order, location, h3_cell_id) VALUES
    ('21G-01', '21G', 'Chennai Central',    1,  ST_GeogFromText('POINT(80.2707 13.0827)'), '894a6ce5a4bffff'),
    ('21G-02', '21G', 'Park Town',          2,  ST_GeogFromText('POINT(80.2676 13.0796)'), '894a6ce5a4bffff'),
    ('21G-03', '21G', 'High Court',         3,  ST_GeogFromText('POINT(80.2562 13.0712)'), '894a6ce5a4bffff'),
    ('21G-04', '21G', 'Saidapet',           4,  ST_GeogFromText('POINT(80.2425 13.0569)'), '894a6ce5a4bffff'),
    ('21G-05', '21G', 'Guindy',             5,  ST_GeogFromText('POINT(80.2206 13.0067)'), '894a6ce5a4bffff'),
    ('5C-01',  '5C',  'Koyambedu',          1,  ST_GeogFromText('POINT(80.1948 13.0694)'), '894a6ce5a4bffff'),
    ('5C-02',  '5C',  'Vadapalani',         2,  ST_GeogFromText('POINT(80.2121 13.0524)'), '894a6ce5a4bffff'),
    ('5C-03',  '5C',  'Ashok Nagar',        3,  ST_GeogFromText('POINT(80.2337 13.0412)'), '894a6ce5a4bffff'),
    ('5C-04',  '5C',  'T. Nagar',           4,  ST_GeogFromText('POINT(80.2376 13.0674)'), '894a6ce5a4bffff'),
    ('12-01',  '12',  'Perambur',           1,  ST_GeogFromText('POINT(80.2400 13.1100)'), '894a6ce5a4bffff'),
    ('12-02',  '12',  'Guindy',             2,  ST_GeogFromText('POINT(80.2206 13.0067)'), '894a6ce5a4bffff'),
    ('12-03',  '12',  'Tambaram',           3,  ST_GeogFromText('POINT(80.1000 12.9249)'), '894a6ce5a4bffff')
ON CONFLICT (stop_id) DO NOTHING;

-- ── Seed Buses ──
INSERT INTO buses (bus_id, route_id, status) VALUES
    ('MTC-21G-001', '21G', 'offline'),
    ('MTC-21G-006', '21G', 'offline'),
    ('MTC-5C-002',  '5C',  'offline'),
    ('MTC-12-003',  '12',  'offline'),
    ('MTC-47-004',  '47',  'offline'),
    ('MTC-29C-005', '29C', 'offline'),
    ('MTC-GHOST-007', '5C', 'offline')
ON CONFLICT (bus_id) DO NOTHING;
