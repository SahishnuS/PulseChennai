-- ════════════════════════════════════════════════════════
-- Pulse-Chennai: Passengers and Ticketing Schema
-- ════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS passenger_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id VARCHAR(20) UNIQUE NOT NULL,
    passenger_id VARCHAR(50) NOT NULL,
    bus_id VARCHAR(20) NOT NULL,
    route_id VARCHAR(10) NOT NULL,
    boarding_stop VARCHAR(100) NOT NULL,
    alighting_stop VARCHAR(100),
    boarded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alighted_at TIMESTAMPTZ,
    fare_estimate INT,
    final_fare INT,
    status VARCHAR(20) DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_passenger_registrations_passenger_id ON passenger_registrations (passenger_id);
CREATE INDEX IF NOT EXISTS idx_passenger_registrations_status ON passenger_registrations (status);
