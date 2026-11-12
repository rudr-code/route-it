from __future__ import annotations
import json, logging, os, sqlite3, threading, time
from pathlib import Path
from typing import Any
from uuid import uuid4
from api.security import (
    MAX_OTP_ATTEMPTS,
    OTP_TTL_SECONDS,
    compute_otp_hmac,
    encrypt_customer_otp_for_portal,
    generate_six_digit_otp,
    hash_password,
    verify_otp_hmac,
)

logger = logging.getLogger(__name__)

# Configurable storage directory (ideal for Render free tier or containerized volume mounts)
DATA_DIR = os.environ.get("DATA_DIR")
if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    DEFAULT_DB_PATH = os.environ.get("ROUTEIT_DB_PATH", os.path.join(DATA_DIR, "routeit_delivery.db"))
else:
    DEFAULT_DB_PATH = os.environ.get("ROUTEIT_DB_PATH", str(Path(__file__).resolve().parent.parent / "routeit_delivery.db"))

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"OPTIMIZED", "PENDING_DISPATCH"},
    "OPTIMIZED": {"PENDING_DISPATCH", "ASSIGNED"},
    "PENDING_DISPATCH": {"ASSIGNED", "ACCEPTED", "CREATED"},
    "ASSIGNED": {"ACCEPTED", "IN_TRANSIT", "PENDING_DISPATCH"},
    "ACCEPTED": {"IN_TRANSIT", "ARRIVED"},
    "IN_TRANSIT": {"ARRIVED", "DELIVERED", "NOT_DELIVERED"},
    "ARRIVED": {"DELIVERED", "NOT_DELIVERED"},
    "DELIVERED": set(),
    "NOT_DELIVERED": {"RETURNED_TO_HUB"},
    "RETURNED_TO_HUB": set(),
}

class DeliveryDatabase:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._init_schema()
            self._seed_initial_data()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                '''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'DRIVER')),
                    full_name TEXT NOT NULL,
                    phone TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drivers (
                    id TEXT PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    full_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    license_number TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'AVAILABLE',
                    assigned_vehicle_id TEXT,
                    current_lat REAL DEFAULT 22.3072,
                    current_lon REAL DEFAULT 73.1812,
                    completed_deliveries INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vehicles (
                    id TEXT PRIMARY KEY,
                    registration_number TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    capacity REAL NOT NULL CHECK(capacity > 0),
                    status TEXT NOT NULL DEFAULT 'AVAILABLE',
                    assigned_driver_id TEXT,
                    current_batch_id TEXT,
                    shift_start REAL DEFAULT 25200.0,
                    shift_end REAL DEFAULT 64800.0,
                    cost_per_km REAL DEFAULT 15.0,
                    fixed_cost REAL DEFAULT 250.0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS delivery_locations (
                    id TEXT PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL,
                    customer_email TEXT DEFAULT '',
                    address TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    demand REAL NOT NULL CHECK(demand >= 0),
                    priority INTEGER NOT NULL DEFAULT 1 CHECK(priority >= 1),
                    ready_time REAL NOT NULL DEFAULT 28800.0,
                    due_time REAL NOT NULL DEFAULT 54000.0,
                    service_time REAL NOT NULL DEFAULT 600.0,
                    is_batched INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS delivery_batches (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    problem_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'CREATED',
                    total_distance_m REAL DEFAULT 0.0,
                    total_duration_sec REAL DEFAULT 0.0,
                    total_cost REAL DEFAULT 0.0,
                    num_vehicles_used INTEGER DEFAULT 0,
                    num_stops INTEGER DEFAULT 0,
                    geojson_str TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    optimized_at REAL
                );
                CREATE TABLE IF NOT EXISTS dispatch_jobs (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES delivery_batches(id) ON DELETE CASCADE,
                    vehicle_id TEXT NOT NULL REFERENCES vehicles(id),
                    driver_id TEXT REFERENCES drivers(id),
                    status TEXT NOT NULL DEFAULT 'PENDING_DISPATCH',
                    stop_count INTEGER NOT NULL DEFAULT 0,
                    total_load REAL NOT NULL DEFAULT 0.0,
                    vehicle_capacity REAL NOT NULL DEFAULT 80.0,
                    planned_distance_m REAL NOT NULL DEFAULT 0.0,
                    planned_duration_sec REAL NOT NULL DEFAULT 0.0,
                    estimated_cost_inr REAL NOT NULL DEFAULT 0.0,
                    route_color TEXT DEFAULT '#6366f1',
                    created_at REAL NOT NULL,
                    accepted_at REAL,
                    completed_at REAL
                );
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES delivery_batches(id) ON DELETE CASCADE,
                    dispatch_job_id TEXT REFERENCES dispatch_jobs(id) ON DELETE SET NULL,
                    location_id TEXT NOT NULL REFERENCES delivery_locations(id),
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL,
                    address TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    demand REAL NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 1,
                    ready_time REAL NOT NULL,
                    due_time REAL NOT NULL,
                    service_time REAL NOT NULL,
                    vehicle_id TEXT,
                    driver_id TEXT,
                    stop_sequence INTEGER DEFAULT 0,
                    eta_seconds REAL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'CREATED',
                    tracking_token TEXT UNIQUE NOT NULL,
                    failure_reason TEXT,
                    hub_verified INTEGER DEFAULT 0,
                    hub_verified_at REAL,
                    delivered_at REAL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS delivery_otps (
                    delivery_id TEXT PRIMARY KEY REFERENCES deliveries(id) ON DELETE CASCADE,
                    otp_hmac TEXT NOT NULL,
                    portal_cipher TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    is_used INTEGER NOT NULL DEFAULT 0,
                    verified_at REAL,
                    verified_by_driver_id TEXT
                );
                CREATE TABLE IF NOT EXISTS delivery_history (
                    id TEXT PRIMARY KEY,
                    delivery_id TEXT,
                    batch_id TEXT,
                    actor_role TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT,
                    details TEXT NOT NULL,
                    timestamp REAL NOT NULL
                );
                '''
            )

    def _seed_initial_data(self) -> None:
        now = time.time()
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        if cur.fetchone()["cnt"] == 0:
            self._conn.execute(
                "INSERT INTO users (id, username, password_hash, role, full_name, phone, email, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("usr_admin_01", "admin", hash_password("admin123"), "ADMIN", "Rudransh Mishra (Fleet Admin)", "+91-9876543210", "admin@routeit.in", now),
            )
            default_drivers = [
                ("usr_drv_01", "driver1", "driver123", "drv_01", "Vikram Solanki", "+91-9825011001", "GJ-06-DL-2021001", "V_1"),
                ("usr_drv_02", "driver2", "driver123", "drv_02", "Harshil Patel", "+91-9825011002", "GJ-06-DL-2021002", "V_2"),
                ("usr_drv_03", "driver3", "driver123", "drv_03", "Karan Parmar", "+91-9825011003", "GJ-06-DL-2021003", "V_3"),
                ("usr_drv_04", "driver4", "driver123", "drv_04", "Mayur Desai", "+91-9825011004", "GJ-06-DL-2021004", "V_4"),
            ]
            for u_id, uname, pwd, d_id, fname, phone, lic, v_id in default_drivers:
                self._conn.execute(
                    "INSERT INTO users (id, username, password_hash, role, full_name, phone, email, created_at) VALUES (?, ?, ?, 'DRIVER', ?, ?, ?, ?)",
                    (u_id, uname, hash_password(pwd), fname, phone, f"{uname}@routeit.in", now),
                )
                self._conn.execute(
                    "INSERT INTO drivers (id, user_id, full_name, phone, license_number, status, assigned_vehicle_id, created_at) VALUES (?, ?, ?, ?, ?, 'AVAILABLE', ?, ?)",
                    (d_id, u_id, fname, phone, lic, v_id, now),
                )

        cur.execute("SELECT COUNT(*) as cnt FROM vehicles")
        if cur.fetchone()["cnt"] == 0:
            default_vehicles = [
                ("V_1", "GJ-06-AX-1001", "Tata Ace EV #1", 80.0, "AVAILABLE", "drv_01"),
                ("V_2", "GJ-06-AX-1002", "Tata Ace EV #2", 80.0, "AVAILABLE", "drv_02"),
                ("V_3", "GJ-06-AX-1003", "Mahindra Zor Grand #3", 80.0, "AVAILABLE", "drv_03"),
                ("V_4", "GJ-06-AX-1004", "Mahindra Zor Grand #4", 80.0, "AVAILABLE", "drv_04"),
                ("V_5", "GJ-06-AX-1005", "Ashok Leyland Dost #5", 80.0, "AVAILABLE", None),
                ("V_6", "GJ-06-AX-1006", "Piaggio Ape E-Xtra #6", 80.0, "AVAILABLE", None),
            ]
            for v_id, reg, name, cap, st, drv_id in default_vehicles:
                self._conn.execute(
                    "INSERT INTO vehicles (id, registration_number, name, capacity, status, assigned_driver_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (v_id, reg, name, cap, st, drv_id, now),
                )

        cur.execute("SELECT COUNT(*) as cnt FROM delivery_locations")
        if cur.fetchone()["cnt"] == 0:
            seeded = False
            vadodara_path = Path(__file__).resolve().parent.parent / "benchmarks" / "instances" / "vadodara_30.json"
            if vadodara_path.is_file():
                try:
                    raw = json.loads(vadodara_path.read_text(encoding="utf-8"))
                    customers = raw.get("customers", [])
                    if customers:
                        for idx, c in enumerate(customers[:15], start=1):
                            loc_id = c.get("id", f"C{idx:02d}")
                            name = c.get("name", f"Vadodara Hub {loc_id}")
                            self._conn.execute(
                                '''
                                INSERT INTO delivery_locations
                                (id, customer_name, customer_phone, customer_email, address, lat, lon, demand, priority, ready_time, due_time, service_time, is_batched, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                                ''',
                                (
                                    loc_id,
                                    f"{name} Logistics Receiver",
                                    f"+91-97240{idx:05d}",
                                    f"contact.{loc_id.lower()}@vadodaracorp.in",
                                    f"Sector {idx}, {name}, Vadodara, Gujarat",
                                    float(c["lat"]),
                                    float(c["lon"]),
                                    float(c["demand"]),
                                    int(c.get("priority", 1)),
                                    float(c["ready_time"]),
                                    float(c["due_time"]),
                                    float(c["service_time"]),
                                    now,
                                ),
                            )
                        seeded = True
                except Exception as e:
                    logger.warning(f"Could not load vadodara_30.json: {e}")

            if not seeded:
                # Fallback demo stops C01-C06 around Vadodara
                fallback_stops = [
                    ("C01", "Alkapuri Logistics Receiver", "+91-9724000001", "Sector 1, Alkapuri, Vadodara, Gujarat", 22.3105, 73.1667, 8.0, 1, 28800.0, 39600.0, 600.0),
                    ("C02", "Fatehgunj Logistics Receiver", "+91-9724000002", "Sector 2, Fatehgunj, Vadodara, Gujarat", 22.3242, 73.1816, 5.0, 2, 32400.0, 43200.0, 600.0),
                    ("C03", "Sayajiganj Logistics Receiver", "+91-9724000003", "Sector 3, Sayajiganj, Vadodara, Gujarat", 22.3166, 73.1780, 12.0, 3, 28800.0, 36000.0, 600.0),
                    ("C04", "Manjalpur Logistics Receiver", "+91-9724000004", "Sector 4, Manjalpur, Vadodara, Gujarat", 22.2721, 73.1823, 7.0, 1, 36000.0, 50400.0, 600.0),
                    ("C05", "Waghodia Logistics Receiver", "+91-9724000005", "Sector 5, Waghodia, Vadodara, Gujarat", 22.3288, 73.2350, 9.0, 4, 28800.0, 46800.0, 600.0),
                    ("C06", "Makarpura Logistics Receiver", "+91-9724000006", "Sector 6, Makarpura, Vadodara, Gujarat", 22.2598, 73.1756, 6.0, 5, 36000.0, 54000.0, 600.0),
                ]
                for s_id, s_name, s_phone, s_addr, s_lat, s_lon, s_dem, s_prio, s_rdy, s_due, s_srv in fallback_stops:
                    self._conn.execute(
                        '''
                        INSERT INTO delivery_locations
                        (id, customer_name, customer_phone, customer_email, address, lat, lon, demand, priority, ready_time, due_time, service_time, is_batched, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                        ''',
                        (s_id, s_name, s_phone, f"info.{s_id.lower()}@routeit.in", s_addr, s_lat, s_lon, s_dem, s_prio, s_rdy, s_due, s_srv, now),
                    )
        self._conn.commit()

    def log_history(
        self,
        actor_role: str,
        actor_id: str,
        event_type: str,
        details: str,
        delivery_id: str | None = None,
        batch_id: str | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                '''
                INSERT INTO delivery_history
                (id, delivery_id, batch_id, actor_role, actor_id, event_type, old_status, new_status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (f"hist_{uuid4().hex[:10]}", delivery_id, batch_id, actor_role, actor_id, event_type, old_status, new_status, details, time.time()),
            )

    def create_or_refresh_otp(self, delivery_id: str) -> str:
        otp_plain = generate_six_digit_otp()
        otp_hmac = compute_otp_hmac(delivery_id, otp_plain)
        portal_cipher = encrypt_customer_otp_for_portal(delivery_id, otp_plain)
        expires_at = time.time() + OTP_TTL_SECONDS
        with self._lock, self._conn:
            self._conn.execute(
                '''
                INSERT OR REPLACE INTO delivery_otps
                (delivery_id, otp_hmac, portal_cipher, expires_at, attempts, max_attempts, is_used, verified_at, verified_by_driver_id)
                VALUES (?, ?, ?, ?, 0, ?, 0, NULL, NULL)
                ''',
                (delivery_id, otp_hmac, portal_cipher, expires_at, MAX_OTP_ATTEMPTS),
            )
        return otp_plain

    def verify_delivery_otp_atomic(
        self, delivery_id: str, driver_id: str, otp_code: str
    ) -> tuple[bool, str, dict[str, Any] | None]:
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
            deliv = cur.fetchone()
            if deliv is None:
                return False, "Delivery not found", None
            if deliv["status"] == "DELIVERED":
                return False, "Delivery is already confirmed as DELIVERED", None
            if deliv["status"] not in ("IN_TRANSIT", "ARRIVED", "ACCEPTED", "ASSIGNED"):
                return False, f"Delivery cannot be verified in current status '{deliv['status']}'", None
            if deliv["driver_id"] and deliv["driver_id"] != driver_id:
                return False, "Unauthorized: Delivery is assigned to a different driver", None

            cur.execute("SELECT * FROM delivery_otps WHERE delivery_id = ?", (delivery_id,))
            otp_row = cur.fetchone()
            if otp_row is None:
                return False, "No OTP record found for this delivery", None
            if otp_row["is_used"]:
                return False, "OTP has already been used", None
            if now > otp_row["expires_at"]:
                return False, "OTP has expired", None
            if otp_row["attempts"] >= otp_row["max_attempts"]:
                return False, "Maximum failed OTP attempts exceeded. Locked.", None

            if not verify_otp_hmac(delivery_id, otp_code, otp_row["otp_hmac"]):
                new_attempts = otp_row["attempts"] + 1
                self._conn.execute("UPDATE delivery_otps SET attempts = ? WHERE delivery_id = ?", (new_attempts, delivery_id))
                self._conn.commit()
                remaining = max(0, otp_row["max_attempts"] - new_attempts)
                return False, f"Invalid OTP code ({remaining} attempts remaining)", None

            old_status = deliv["status"]
            self._conn.execute(
                "UPDATE delivery_otps SET is_used = 1, verified_at = ?, verified_by_driver_id = ? WHERE delivery_id = ?",
                (now, driver_id, delivery_id),
            )
            self._conn.execute(
                "UPDATE deliveries SET status = 'DELIVERED', delivered_at = ?, updated_at = ? WHERE id = ?",
                (now, now, delivery_id),
            )
            if driver_id:
                self._conn.execute("UPDATE drivers SET completed_deliveries = completed_deliveries + 1 WHERE id = ?", (driver_id,))

            job_id = deliv["dispatch_job_id"]
            if job_id:
                cur.execute(
                    "SELECT COUNT(*) as rem FROM deliveries WHERE dispatch_job_id = ? AND status NOT IN ('DELIVERED', 'NOT_DELIVERED', 'RETURNED_TO_HUB')",
                    (job_id,),
                )
                if cur.fetchone()["rem"] == 0:
                    self._conn.execute("UPDATE dispatch_jobs SET status = 'DELIVERED', completed_at = ? WHERE id = ?", (now, job_id))
                    if deliv["vehicle_id"]:
                        self._conn.execute("UPDATE vehicles SET status = 'AVAILABLE', current_batch_id = NULL WHERE id = ?", (deliv["vehicle_id"],))

            self._conn.commit()
            self.log_history(
                actor_role="DRIVER",
                actor_id=driver_id,
                event_type="OTP_VERIFIED_DELIVERED",
                old_status=old_status,
                new_status="DELIVERED",
                delivery_id=delivery_id,
                batch_id=deliv["batch_id"],
                details=f"Delivery {delivery_id} verified via 6-digit OTP by driver {driver_id}.",
            )
            cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
            return True, "Delivery verified and marked DELIVERED", dict(cur.fetchone())

_db_instance: DeliveryDatabase | None = None

def get_db() -> DeliveryDatabase:
    global _db_instance
    if _db_instance is None:
        _db_instance = DeliveryDatabase()
    return _db_instance
