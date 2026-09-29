from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json
import math
from pathlib import Path

app = FastAPI(title="Policy-as-Code API")

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "policy_runs.db"

RULES_FILE = (
    BASE_DIR
    / "Policy_Automation"
    / "output"
    / "policy_rules.json"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# JSON HELPERS
# ============================================================

def parse_json(value, default=None):
    if value is None or value == "":
        return default if default is not None else []

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


def clean_for_json(value):
    """
    Convert NaN / Infinity values to None so FastAPI
    can safely serialize the response as JSON.
    """

    if isinstance(value, float):

        if math.isnan(value) or math.isinf(value):
            return None

        return value

    if isinstance(value, dict):
        return {
            key: clean_for_json(val)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [
            clean_for_json(item)
            for item in value
        ]

    return value


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Policy-as-Code API is running"
    }


# ============================================================
# GET ALL RUNS
# ============================================================

@app.get("/api/runs")
def get_runs():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            run_number,
            run_date,
            policy_name,
            dataset_name,
            total_records,
            pass_count,
            flag_count,
            block_count
        FROM runs
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()

    conn.close()

    runs = []

    for row in rows:

        runs.append({
            "id": row["id"],
            "run_number": row["run_number"],
            "run_date": row["run_date"],
            "policy_name": row["policy_name"],
            "dataset_name": row["dataset_name"],
            "total_records": row["total_records"],
            "pass_count": row["pass_count"],
            "flag_count": row["flag_count"],
            "block_count": row["block_count"]
        })

    return runs


# ============================================================
# GET SINGLE RUN
# ============================================================

@app.get("/api/runs/{run_id}")
def get_run(run_id: int):

    conn = get_connection()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # GET RUN
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            run_number,
            run_date,
            policy_name,
            dataset_name,
            total_records,
            pass_count,
            flag_count,
            block_count
        FROM runs
        WHERE id = ?
    """, (run_id,))

    run = cursor.fetchone()

    if run is None:

        conn.close()

        raise HTTPException(
            status_code=404,
            detail="Run not found"
        )

    # --------------------------------------------------------
    # GET RECORDS
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            record_id,
            record_data,
            outcome,
            triggered_rules,
            reason,
            remediation
        FROM run_records
        WHERE run_id = ?
        ORDER BY id
    """, (run_id,))

    record_rows = cursor.fetchall()

    conn.close()

    # --------------------------------------------------------
    # BUILD RECORDS
    # --------------------------------------------------------

    records = []

    for row in record_rows:

        record_data = parse_json(
            row["record_data"],
            {}
        )

        triggered_rules = parse_json(
            row["triggered_rules"],
            []
        )

        record = dict(record_data)

        record["record_id"] = str(row["record_id"])

        record["outcome"] = row["outcome"] or "PASS"

        record["triggered_rules"] = triggered_rules

        record["reason"] = row["reason"] or ""

        record["remediation"] = row["remediation"] or ""

        records.append(
            clean_for_json(record)
        )

    # --------------------------------------------------------
    # RETURN RUN
    # --------------------------------------------------------

    response = {
        "id": run["id"],
        "run_number": run["run_number"],
        "run_date": run["run_date"],
        "policy_name": run["policy_name"],
        "dataset_name": run["dataset_name"],
        "total_records": run["total_records"],
        "pass_count": run["pass_count"],
        "flag_count": run["flag_count"],
        "block_count": run["block_count"],
        "records": records
    }

    return clean_for_json(response)


# ============================================================
# GET POLICY RULES
# ============================================================

@app.get("/api/rules")
def get_rules():

    if not RULES_FILE.exists():

        raise HTTPException(
            status_code=404,
            detail="Policy rules file not found"
        )

    try:

        with open(
            RULES_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Could not read policy rules: {str(e)}"
        )

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and "rules" in data:
        return data["rules"]

    raise HTTPException(
        status_code=500,
        detail="Invalid policy_rules.json format"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
def health_check():

    return {
        "status": "ok",
        "database": str(DB_PATH),
        "database_exists": DB_PATH.exists(),
        "rules_file": str(RULES_FILE),
        "rules_file_exists": RULES_FILE.exists()
    }