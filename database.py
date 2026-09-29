import sqlite3
import json
import math
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "policy_runs.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# CLEAN VALUES FOR JSON
# ============================================================

def clean_value(value):
    """
    Convert values that cannot be safely returned as JSON
    into JSON-compatible values.
    """

    # Handle float NaN
    if isinstance(value, float) and math.isnan(value):
        return None

    return value


def clean_record(record):
    """
    Recursively clean a record before returning it through API.
    """

    cleaned = {}

    for key, value in record.items():

        if isinstance(value, dict):
            cleaned[key] = clean_record(value)

        elif isinstance(value, list):
            cleaned[key] = [
                clean_value(item) for item in value
            ]

        else:
            cleaned[key] = clean_value(value)

    return cleaned


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_number INTEGER NOT NULL,
            run_date TEXT NOT NULL,
            policy_name TEXT,
            dataset_name TEXT NOT NULL,
            total_records INTEGER NOT NULL,
            pass_count INTEGER NOT NULL,
            flag_count INTEGER NOT NULL,
            block_count INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS run_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            record_id TEXT NOT NULL,
            record_data TEXT NOT NULL,
            outcome TEXT NOT NULL,
            triggered_rules TEXT,
            reason TEXT,
            remediation TEXT,

            FOREIGN KEY (run_id)
                REFERENCES runs(id)
                ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# SAVE RUN
# ============================================================

def save_run(
    records,
    dataset_name,
    policy_name="AI Training Data PII Policy"
):

    conn = get_connection()
    cursor = conn.cursor()

    # Generate next run number
    cursor.execute("""
        SELECT COALESCE(MAX(run_number), 0) + 1
        FROM runs
    """)

    run_number = cursor.fetchone()[0]

    # Calculate summary
    total_records = len(records)

    pass_count = sum(
        1
        for record in records
        if record.get("outcome") == "PASS"
    )

    flag_count = sum(
        1
        for record in records
        if record.get("outcome") == "FLAG"
    )

    block_count = sum(
        1
        for record in records
        if record.get("outcome") == "BLOCK"
    )

    run_date = datetime.now().isoformat(timespec="seconds")

    # Insert run
    cursor.execute("""
        INSERT INTO runs (
            run_number,
            run_date,
            policy_name,
            dataset_name,
            total_records,
            pass_count,
            flag_count,
            block_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_number,
        run_date,
        policy_name,
        dataset_name,
        total_records,
        pass_count,
        flag_count,
        block_count
    ))

    run_id = cursor.lastrowid

    # Insert individual records
    for record in records:

        record_data = dict(record)

        # Remove evaluation metadata from raw record data
        record_data.pop("outcome", None)
        record_data.pop("triggered_rules", None)
        record_data.pop("reason", None)
        record_data.pop("remediation", None)

        # Convert NaN to None
        record_data = clean_record(record_data)

        cursor.execute("""
            INSERT INTO run_records (
                run_id,
                record_id,
                record_data,
                outcome,
                triggered_rules,
                reason,
                remediation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            str(record.get("record_id")),
            json.dumps(
                record_data,
                default=str,
                ensure_ascii=False
            ),
            record.get("outcome", "PASS"),
            json.dumps(
                record.get("triggered_rules", []),
                default=str,
                ensure_ascii=False
            ),
            record.get("reason", ""),
            record.get("remediation", "")
        ))

    conn.commit()
    conn.close()

    return run_id


# ============================================================
# GET ALL RUNS
# ============================================================

def get_runs():

    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM runs
        ORDER BY run_number DESC
    """).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# GET ONE COMPLETE RUN
# ============================================================

def get_run(run_id):

    conn = get_connection()

    # Get run information
    run = conn.execute("""
        SELECT *
        FROM runs
        WHERE id = ?
    """, (run_id,)).fetchone()

    if run is None:
        conn.close()
        return None

    # Get all records belonging to this run
    records = conn.execute("""
        SELECT *
        FROM run_records
        WHERE run_id = ?
        ORDER BY CAST(record_id AS INTEGER)
    """, (run_id,)).fetchall()

    conn.close()

    run_data = dict(run)

    run_data["records"] = []

    for row in records:

        # Restore original record data
        record = json.loads(
            row["record_data"]
        )

        record["record_id"] = row["record_id"]

        record["expected_outcome"] = (
            row["outcome"]
        )

        record["expected_rule_triggers"] = (
            row["triggered_rules"] or ""
        )

        record["expected_reason"] = (
            row["reason"] or ""
        )

        record["suggested_remediation"] = (
            row["remediation"] or ""
        )

        # Make sure NaN/null values are JSON safe
        record = clean_record(record)

        run_data["records"].append(record)

    return run_data


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    initialize_database()

    print("=" * 50)
    print("DATABASE INITIALIZED")
    print("=" * 50)

    print("\nDatabase:")
    print(DB_PATH)