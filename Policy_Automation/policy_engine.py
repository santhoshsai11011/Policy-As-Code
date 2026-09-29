import json
import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RULES_FILE = BASE_DIR / "output" / "policy_rules.json"
DATA_FILE = BASE_DIR / "input" / "synthetic_data.xlsx"

# Use the same database as FastAPI
DB_FILE = BASE_DIR.parent / "policy_runs.db"


# ============================================================
# LOAD POLICY RULES
# ============================================================

def load_rules():
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Supports:
    # 1. [{"rule_id": ...}, ...]
    # 2. {"rules": [{"rule_id": ...}, ...]}

    if isinstance(data, list):
        rules = data

    elif isinstance(data, dict) and "rules" in data:
        rules = data["rules"]

    else:
        raise ValueError("Invalid policy_rules.json format")

    return rules


# ============================================================
# LOAD DATASET
# ============================================================

def load_dataset():
    df = pd.read_excel(DATA_FILE)

    df.columns = [
        str(column).strip().lower()
        for column in df.columns
    ]

    return df


# ============================================================
# VALUE CHECK
# ============================================================

def is_populated(value):
    if pd.isna(value):
        return False

    value = str(value).strip()

    if value == "":
        return False

    if value.lower() in {
        "nan",
        "none",
        "null",
        "n/a",
        "na"
    }:
        return False

    return True


# ============================================================
# FIELD NORMALIZATION
# ============================================================

def normalize_field(field):
    return (
        str(field)
        .strip()
        .lower()
        .replace(" ", "_")
    )


# ============================================================
# FIND MATCHING DATASET FIELDS
# ============================================================

def get_matching_fields(row, trigger_fields):

    dataset_fields = {
        normalize_field(column): column
        for column in row.index
    }

    matching_fields = []

    for field in trigger_fields:

        normalized_field = normalize_field(field)

        if normalized_field not in dataset_fields:
            continue

        actual_column = dataset_fields[normalized_field]

        if is_populated(row[actual_column]):
            matching_fields.append(actual_column)

    return matching_fields


# ============================================================
# EVALUATE ONE RULE
# ============================================================

def evaluate_rule(row, rule):

    rule_id = rule.get("rule_id")
    category = rule.get("category")
    description = rule.get("description", "")
    trigger_fields = rule.get("trigger_fields", [])
    outcome = rule.get("outcome")

    # The extractor currently stores condition_type.
    # If it isn't present, derive it.

    condition_type = rule.get("condition_type")

    if not condition_type:

        if category == "CPII":
            condition_type = "ALL"

        else:
            condition_type = "ANY"

    # --------------------------------------------------------
    # SPECIAL CASE: CPII-107
    # --------------------------------------------------------

    if rule_id == "CPII-107":

        if "free_text" not in [
            normalize_field(column)
            for column in row.index
        ]:
            return None

        actual_column = None

        for column in row.index:

            if normalize_field(column) == "free_text":
                actual_column = column
                break

        if actual_column is None:
            return None

        if not is_populated(row[actual_column]):
            return None

        # Content-level semantic rule.
        # The actual semantic detection will be added later.
        # For now, only identify that free_text exists.
        return None

    # --------------------------------------------------------
    # NORMAL FIELD-BASED RULE
    # --------------------------------------------------------

    matching_fields = get_matching_fields(
        row,
        trigger_fields
    )

    if condition_type == "ALL":

        triggered = (
            len(trigger_fields) > 0
            and len(matching_fields) == len(trigger_fields)
        )

    else:

        triggered = len(matching_fields) > 0

    if not triggered:
        return None

    return {
        "rule_id": rule_id,
        "category": category,
        "description": description,
        "outcome": outcome,
        "matched_fields": matching_fields
    }


# ============================================================
# EVALUATE ONE RECORD
# ============================================================

def evaluate_record(row, rules):

    triggered_rules = []

    for rule in rules:

        result = evaluate_rule(
            row,
            rule
        )

        if result:
            triggered_rules.append(result)

    # --------------------------------------------------------
    # NO RULE TRIGGERED
    # --------------------------------------------------------

    if not triggered_rules:

        return {
            "outcome": "PASS",
            "triggered_rules": [],
            "reason": "No PII, SPII or CPII rule was triggered.",
            "remediation": "No remediation required."
        }

    # --------------------------------------------------------
    # DETERMINE FINAL OUTCOME
    # --------------------------------------------------------

    # BLOCK has priority over FLAG.

    if any(
        rule["outcome"] == "BLOCK"
        for rule in triggered_rules
    ):

        final_outcome = "BLOCK"

    elif any(
        rule["outcome"] == "FLAG"
        for rule in triggered_rules
    ):

        final_outcome = "FLAG"

    else:

        final_outcome = "PASS"

    # --------------------------------------------------------
    # RULE IDS
    # --------------------------------------------------------

    rule_ids = [
        rule["rule_id"]
        for rule in triggered_rules
    ]

    descriptions = [
        rule["description"]
        for rule in triggered_rules
    ]

    # --------------------------------------------------------
    # REMEDIATION
    # --------------------------------------------------------

    if final_outcome == "BLOCK":

        remediation = (
            "Remove or transform the personal data before use, "
            "or use an approved exception where permitted."
        )

    else:

        remediation = (
            "Apply appropriate remediation such as removal, masking, "
            "tokenisation, generalisation, pseudonymisation "
            "or anonymisation."
        )

    # --------------------------------------------------------
    # REASON
    # --------------------------------------------------------

    reason = (
        f"Triggered rules: {', '.join(rule_ids)}. "
        f"Detected: {'; '.join(descriptions)}."
    )

    return {
        "outcome": final_outcome,
        "triggered_rules": triggered_rules,
        "reason": reason,
        "remediation": remediation
    }


# ============================================================
# DATABASE
# ============================================================

def create_database():

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_number INTEGER,
            run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            policy_name TEXT,
            dataset_name TEXT,
            total_records INTEGER,
            pass_count INTEGER,
            flag_count INTEGER,
            block_count INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS run_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            record_id TEXT,
            record_data TEXT,
            outcome TEXT,
            triggered_rules TEXT,
            reason TEXT,
            remediation TEXT,
            FOREIGN KEY(run_id)
                REFERENCES runs(id)
        )
    """)

    conn.commit()

    return conn


# ============================================================
# SAVE RESULTS TO SQLITE
# ============================================================

def save_results(
    results,
    dataset_name,
    policy_name
):

    conn = create_database()

    cursor = conn.cursor()

    # --------------------------------------------------------
    # RUN NUMBER
    # --------------------------------------------------------

    cursor.execute("""
        SELECT COALESCE(MAX(run_number), 0) + 1
        FROM runs
    """)

    run_number = cursor.fetchone()[0]

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    total_records = len(results)

    pass_count = sum(
        1
        for result in results
        if result["outcome"] == "PASS"
    )

    flag_count = sum(
        1
        for result in results
        if result["outcome"] == "FLAG"
    )

    block_count = sum(
        1
        for result in results
        if result["outcome"] == "BLOCK"
    )

    # --------------------------------------------------------
    # SAVE RUN
    # --------------------------------------------------------

    run_date = datetime.now().isoformat(
        timespec="seconds"
    )

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

    # --------------------------------------------------------
    # SAVE RECORDS
    # --------------------------------------------------------

    for result in results:

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
            str(result["record_id"]),
            json.dumps(
                result["record_data"],
                default=str,
                ensure_ascii=False
            ),
            result["outcome"],
            json.dumps(
                result["triggered_rules"],
                default=str,
                ensure_ascii=False
            ),
            result["reason"],
            result["remediation"]
        ))

    conn.commit()

    conn.close()

    return run_id


# ============================================================
# EXPORT EXCEL RESULTS
# ============================================================

def export_results(results):

    output_rows = []

    for result in results:

        output_rows.append({
            "record_id":
                result["record_id"],

            "outcome":
                result["outcome"],

            "triggered_rules":
                ", ".join(
                    rule["rule_id"]
                    for rule in result["triggered_rules"]
                ),

            "reason":
                result["reason"],

            "remediation":
                result["remediation"]
        })

    output_file = (
        BASE_DIR /
        "output" /
        "policy_results.xlsx"
    )

    pd.DataFrame(
        output_rows
    ).to_excel(
        output_file,
        index=False
    )

    return output_file


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 50)
    print("DYNAMIC POLICY ENGINE")
    print("=" * 50)

    # --------------------------------------------------------
    # LOAD RULES
    # --------------------------------------------------------

    print("\nLoading policy rules...")

    rules = load_rules()

    print(
        f"Rules loaded: {len(rules)}"
    )

    # --------------------------------------------------------
    # RULE SUMMARY
    # --------------------------------------------------------

    category_counts = {}

    for rule in rules:

        category = rule.get(
            "category",
            "UNKNOWN"
        )

        category_counts[category] = (
            category_counts.get(
                category,
                0
            ) + 1
        )

    print("\nRules by category:")

    for category, count in category_counts.items():

        print(
            f"  {category}: {count}"
        )

    # --------------------------------------------------------
    # LOAD DATASET
    # --------------------------------------------------------

    print("\nLoading synthetic dataset...")

    df = load_dataset()

    print(
        f"Records loaded: {len(df)}"
    )

    print(
        f"Columns loaded: {len(df.columns)}"
    )

    print("\nDataset columns:")

    for column in df.columns:

        print(
            f"  - {column}"
        )

    # --------------------------------------------------------
    # EVALUATE
    # --------------------------------------------------------

    print("\nEvaluating records...")

    results = []

    for _, row in df.iterrows():

        evaluation = evaluate_record(
            row,
            rules
        )

        record_id = row.get(
            "record_id",
            str(len(results) + 1)
        )

        record_data = row.to_dict()

        results.append({
            "record_id": record_id,
            "record_data": record_data,
            **evaluation
        })

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    pass_count = sum(
        result["outcome"] == "PASS"
        for result in results
    )

    flag_count = sum(
        result["outcome"] == "FLAG"
        for result in results
    )

    block_count = sum(
        result["outcome"] == "BLOCK"
        for result in results
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("\n" + "=" * 50)
    print("EVALUATION COMPLETE")
    print("=" * 50)

    print(
        f"Total records : {len(results)}"
    )

    print(
        f"PASS          : {pass_count}"
    )

    print(
        f"FLAG          : {flag_count}"
    )

    print(
        f"BLOCK         : {block_count}"
    )

    # --------------------------------------------------------
    # SAMPLE RESULTS
    # --------------------------------------------------------

    print("\nSample results:")

    for result in results[:10]:

        print(
            f"\nRecord: {result['record_id']}"
        )

        print(
            f"Outcome: {result['outcome']}"
        )

        print(
            "Triggered:",
            [
                rule["rule_id"]
                for rule in result["triggered_rules"]
            ]
        )

        print(
            f"Reason: {result['reason']}"
        )

    # --------------------------------------------------------
    # SQLITE
    # --------------------------------------------------------

    print("\nSaving results to SQLite...")

    run_id = save_results(
        results,
        DATA_FILE.name,
        "Extracted Policy"
    )

    print(
        f"SQLite run ID: {run_id}"
    )

    # --------------------------------------------------------
    # EXCEL OUTPUT
    # --------------------------------------------------------

    output_file = export_results(
        results
    )

    print(
        f"Excel output: {output_file}"
    )

    print("\n" + "=" * 50)
    print("DONE")
    print("=" * 50)


if __name__ == "__main__":
    main()