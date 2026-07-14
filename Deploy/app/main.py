"""
BigProject demo app.

Connects to Postgres (with the TimescaleDB extension), creates a small
"sensor readings" hypertable on startup, seeds a few sample rows if empty,
and exposes endpoints to prove the whole stack is working end to end.

Adds Azure AD login: /login redirects to Microsoft's sign-in page,
/auth/callback receives the result and sets a signed session cookie
containing the user's name and App Role (Admin / Viewer). /sensors is
gated behind login; Admins see the full dataset, Viewers see a limited
summary.
"""
import os
import random
from datetime import datetime, timedelta, timezone

import msal
import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from itsdangerous import URLSafeSerializer, BadSignature

app = FastAPI(title="BigProject Demo App")

# --- Database connection settings ---
DB_HOST = os.environ.get("DB_HOST", "bigproject-pg-server.postgres.database.azure.com")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "pgadmin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_PORT = os.environ.get("DB_PORT", "5432")

# --- Azure AD login settings ---
AAD_CLIENT_ID = os.environ.get("AAD_CLIENT_ID", "")
AAD_CLIENT_SECRET = os.environ.get("AAD_CLIENT_SECRET", "")
AAD_TENANT_ID = os.environ.get("AAD_TENANT_ID", "")
AAD_AUTHORITY = f"https://login.microsoftonline.com/{AAD_TENANT_ID}"
AAD_REDIRECT_URI = os.environ.get("AAD_REDIRECT_URI", "https://4.154.208.121/auth/callback")

SESSION_SIGNING_KEY = AAD_CLIENT_SECRET or "dev-only-fallback-key"
serializer = URLSafeSerializer(SESSION_SIGNING_KEY, salt="bigproject-session")

msal_app = msal.ConfidentialClientApplication(
    AAD_CLIENT_ID,
    authority=AAD_AUTHORITY,
    client_credential=AAD_CLIENT_SECRET,
)


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        sslmode="require",
    )


def setup_database():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            time        TIMESTAMPTZ NOT NULL,
            sensor_id   TEXT NOT NULL,
            temperature DOUBLE PRECISION,
            pressure    DOUBLE PRECISION
        );
    """)

    cur.execute("""
        SELECT create_hypertable('sensor_readings', 'time', if_not_exists => TRUE);
    """)

    cur.execute("SELECT COUNT(*) FROM sensor_readings;")
    row_count = cur.fetchone()[0]

    if row_count == 0:
        now = datetime.now(timezone.utc)
        rows = []
        for minutes_ago in range(0, 24 * 60, 10):
            ts = now - timedelta(minutes=minutes_ago)
            for sensor_id in ["sensor-1", "sensor-2", "sensor-3"]:
                rows.append((
                    ts,
                    sensor_id,
                    round(random.uniform(18.0, 24.0), 2),
                    round(random.uniform(100.0, 105.0), 2),
                ))

        cur.executemany(
            "INSERT INTO sensor_readings (time, sensor_id, temperature, pressure) "
            "VALUES (%s, %s, %s, %s);",
            rows,
        )

    conn.commit()
    cur.close()
    conn.close()


@app.on_event("startup")
def on_startup():
    setup_database()


def get_current_user(request: Request):
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        return serializer.loads(cookie)
    except BadSignature:
        return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root(request: Request):
    user = get_current_user(request)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sensor_readings;")
    row_count = cur.fetchone()[0]
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';")
    ts_version = cur.fetchone()
    cur.close()
    conn.close()

    return {
        "status": "connected",
        "database_host": DB_HOST,
        "sensor_reading_rows": row_count,
        "timescaledb_version": ts_version[0] if ts_version else "not installed",
        "logged_in": user is not None,
        "user": user["name"] if user else None,
        "role": user["role"] if user else None,
    }


@app.get("/login")
def login():
    auth_url = msal_app.get_authorization_request_url(
        scopes=[],
        redirect_uri=AAD_REDIRECT_URI,
    )
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
def auth_callback(request: Request, code: str = None, error: str = None):
    if error:
        return JSONResponse({"error": error}, status_code=400)

    if not code:
        return JSONResponse({"error": "missing authorization code"}, status_code=400)

    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=[],
        redirect_uri=AAD_REDIRECT_URI,
    )

    if "id_token_claims" not in result:
        return JSONResponse(
            {"error": result.get("error_description", "login failed")},
            status_code=401,
        )

    claims = result["id_token_claims"]
    name = claims.get("name", "unknown")
    roles = claims.get("roles", [])
    role = "Admin" if "Admin" in roles else ("Viewer" if "Viewer" in roles else "Viewer")

    session_value = serializer.dumps({"name": name, "role": role})

    response = RedirectResponse("/sensors")
    response.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/")
    response.delete_cookie("session")
    return response


@app.get("/sensors")
def sensors(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    conn = get_connection()
    cur = conn.cursor()

    if user["role"] == "Admin":
        cur.execute("""
            SELECT
                sensor_id,
                time_bucket('1 hour', time) AS hour,
                AVG(temperature) AS avg_temp,
                AVG(pressure) AS avg_pressure
            FROM sensor_readings
            WHERE time > NOW() - INTERVAL '24 hours'
            GROUP BY sensor_id, hour
            ORDER BY hour DESC, sensor_id;
        """)
    else:
        cur.execute("""
            SELECT
                sensor_id,
                time_bucket('1 day', time) AS day,
                AVG(temperature) AS avg_temp,
                AVG(pressure) AS avg_pressure
            FROM sensor_readings
            WHERE time > NOW() - INTERVAL '24 hours'
            GROUP BY sensor_id, day
            ORDER BY day DESC, sensor_id;
        """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "viewed_as": user["name"],
        "role": user["role"],
        "data": [
            {
                "sensor_id": r[0],
                "period": r[1].isoformat(),
                "avg_temperature": round(r[2], 2),
                "avg_pressure": round(r[3], 2),
            }
            for r in rows
        ],
    }
