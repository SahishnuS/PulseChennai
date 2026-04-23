"""
Ingestion Pipeline
=====================
Kafka-based streaming pipeline that consumes raw GPS pings
from AIS 140 bus units and passenger devices.

Each ping is:
1. Validated (Chennai bounding box)
2. Mapped to H3 cell
3. Scored for hardware reliability (bus pings only)
4. Pushed to Redis Feature Store
5. Buffered for S3 batch writes
"""

import time
import json
import logging
from datetime import datetime
from typing import Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GPSPingMessage:
    """Raw GPS ping from Kafka topic."""
    device_id: str
    lat: float
    lng: float
    timestamp: float          # Unix ms
    ping_type: str            # "bus" | "person"
    trip_id: Optional[str] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    passenger_count: Optional[int] = None


@dataclass
class WriteBuffer:
    """Buffered records awaiting S3 flush."""
    records: list[dict] = field(default_factory=list)
    last_flush: float = field(default_factory=time.time)

    def add(self, record: dict) -> None:
        self.records.append(record)

    def should_flush(self, interval_seconds: int) -> bool:
        return (time.time() - self.last_flush) >= interval_seconds

    def flush(self) -> list[dict]:
        flushed = self.records.copy()
        self.records.clear()
        self.last_flush = time.time()
        return flushed


class IngestionPipeline:
    """
    Kafka → H3 → Redis → S3 streaming pipeline.

    Consumes from two topics:
    - bus_gps_pings:    AIS 140 hardware GPS data
    - person_gps_pings: Collaborative Telemetry from passenger devices

    Design principle: Each ping must be processed in <50ms to maintain
    throughput at 10,000+ buses × 0.1 Hz = 1,000 pings/sec.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        bus_topic: str,
        person_topic: str,
        consumer_group: str,
        feature_store,         # FeatureStoreClient instance
        data_lake,             # DataLakeClient instance
        reliability_scorer,    # HardwareReliabilityScorer instance
        h3_resolution: int = 9,
        flush_interval: int = 30,
        chennai_bounds: Optional[dict] = None,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.bus_topic = bus_topic
        self.person_topic = person_topic
        self.consumer_group = consumer_group
        self.feature_store = feature_store
        self.data_lake = data_lake
        self.reliability_scorer = reliability_scorer
        self.h3_resolution = h3_resolution
        self.flush_interval = flush_interval

        self.bounds = chennai_bounds or {
            "lat_min": 12.8, "lat_max": 13.3,
            "lng_min": 80.1, "lng_max": 80.35,
        }

        self._write_buffer = WriteBuffer()
        self._consumer = None
        self._running = False

        # H3 cell aggregation counters (reset per flush cycle)
        self._cell_bus_counts: dict[str, int] = {}
        self._cell_speeds: dict[str, list[float]] = {}
        self._cell_person_counts: dict[str, int] = {}

    def _create_consumer(self):
        """Initialize Kafka consumer."""
        try:
            from confluent_kafka import Consumer

            self._consumer = Consumer({
                "bootstrap.servers": self.bootstrap_servers,
                "group.id": self.consumer_group,
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
                "max.poll.interval.ms": 300000,
            })
            self._consumer.subscribe([self.bus_topic, self.person_topic])
            logger.info(
                f"Kafka consumer subscribed to "
                f"[{self.bus_topic}, {self.person_topic}]"
            )
        except ImportError:
            logger.warning(
                "confluent_kafka not installed. "
                "Ingestion pipeline running in stub mode."
            )

    def _validate_ping(self, ping: GPSPingMessage) -> bool:
        """Validate GPS ping is within Chennai bounds."""
        return (
            self.bounds["lat_min"] <= ping.lat <= self.bounds["lat_max"]
            and self.bounds["lng_min"] <= ping.lng <= self.bounds["lng_max"]
        )

    def _process_bus_ping(self, ping: GPSPingMessage) -> None:
        """
        Process a single bus GPS ping:
        1. Compute H3 cell
        2. Score hardware reliability
        3. Update Redis (bus state + cell aggregates)
        4. Buffer for S3
        """
        import h3

        h3_l9 = h3.latlng_to_cell(ping.lat, ping.lng, 9)
        h3_l8 = h3.latlng_to_cell(ping.lat, ping.lng, 8)

        # Hardware reliability scoring
        hw_score = self.reliability_scorer.score_ping(
            bus_id=ping.device_id,
            lat=ping.lat,
            lng=ping.lng,
            timestamp=ping.timestamp,
            speed=ping.speed,
        )

        # Determine status based on hardware score
        status = "active" if hw_score >= 0.3 else "ghost_suppressed"

        # Update bus state in Redis
        if ping.trip_id:
            self.feature_store.update_bus_state(
                trip_id=ping.trip_id,
                lat=ping.lat,
                lng=ping.lng,
                h3_cell=h3_l9,
                speed=ping.speed or 0.0,
                heading=ping.heading or 0.0,
                hw_score=hw_score,
                passenger_count=ping.passenger_count or 0,
                status=status,
            )

        # Aggregate cell-level stats
        self._cell_bus_counts[h3_l9] = (
            self._cell_bus_counts.get(h3_l9, 0) + 1
        )
        if ping.speed is not None:
            self._cell_speeds.setdefault(h3_l9, []).append(ping.speed)

        # Buffer for S3 write
        self._write_buffer.add({
            "bus_id": ping.device_id,
            "trip_id": ping.trip_id or "unknown",
            "lat": ping.lat,
            "lon": ping.lng,
            "h3_l8": h3_l8,
            "h3_l9": h3_l9,
            "timestamp": datetime.fromtimestamp(ping.timestamp / 1000),
            "speed": ping.speed,
            "heading": ping.heading,
            "passenger_count": ping.passenger_count,
            "hw_reliability_score": hw_score,
            "source": "ais140",
        })

    def _process_person_ping(self, ping: GPSPingMessage) -> None:
        """
        Process a passenger GPS ping (Collaborative Telemetry).
        These are used to:
        1. Refine bus position when HW is unreliable
        2. Estimate passenger density per H3 cell
        """
        import h3

        h3_l9 = h3.latlng_to_cell(ping.lat, ping.lng, 9)

        # Increment person ping count for this cell
        self._cell_person_counts[h3_l9] = (
            self._cell_person_counts.get(h3_l9, 0) + 1
        )

        # Update node state with person density
        self.feature_store.update_node_state(
            h3_index=h3_l9,
            person_ping_count=self._cell_person_counts[h3_l9],
        )

    def _flush_aggregates(self) -> None:
        """Flush cell-level aggregates to Redis node states."""
        for h3_cell, count in self._cell_bus_counts.items():
            speeds = self._cell_speeds.get(h3_cell, [])
            avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

            # Simple congestion heuristic: low speed + high density = congested
            person_count = self._cell_person_counts.get(h3_cell, 0)
            congestion = 0.0
            if avg_speed > 0:
                congestion = min(1.0, (person_count * 5) / (avg_speed + 1))

            self.feature_store.update_node_state(
                h3_index=h3_cell,
                bus_count=count,
                avg_speed=avg_speed,
                congestion_score=congestion,
                passenger_density=person_count / max(count, 1),
                person_ping_count=person_count,
            )

        # Reset counters
        self._cell_bus_counts.clear()
        self._cell_speeds.clear()
        self._cell_person_counts.clear()

    def process_single_message(self, raw_message: dict) -> None:
        """
        Process a single message (for testing or direct invocation).
        """
        ping = GPSPingMessage(**raw_message)
        if not self._validate_ping(ping):
            logger.debug(f"Ping outside Chennai bounds: {ping.lat}, {ping.lng}")
            return

        if ping.ping_type == "bus":
            self._process_bus_ping(ping)
        elif ping.ping_type == "person":
            self._process_person_ping(ping)

    def run(self, on_message: Optional[Callable] = None) -> None:
        """
        Main consumer loop. Runs indefinitely until stopped.

        Args:
            on_message: Optional callback for each processed message.
        """
        self._create_consumer()
        if not self._consumer:
            logger.error("No Kafka consumer available. Exiting.")
            return

        self._running = True
        logger.info("Ingestion pipeline started.")

        try:
            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    logger.error(f"Kafka error: {msg.error()}")
                    continue

                try:
                    raw = json.loads(msg.value().decode("utf-8"))
                    self.process_single_message(raw)
                    if on_message:
                        on_message(raw)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse message: {e}")
                    continue

                # Periodic flush to S3 + Redis aggregates
                if self._write_buffer.should_flush(self.flush_interval):
                    records = self._write_buffer.flush()
                    if records:
                        self.data_lake.write_trajectories(records)
                    self._flush_aggregates()

        except KeyboardInterrupt:
            logger.info("Ingestion pipeline interrupted.")
        finally:
            self._consumer.close()
            # Final flush
            records = self._write_buffer.flush()
            if records:
                self.data_lake.write_trajectories(records)
            self._flush_aggregates()
            logger.info("Ingestion pipeline stopped.")

    def stop(self) -> None:
        """Signal the consumer loop to stop."""
        self._running = False
