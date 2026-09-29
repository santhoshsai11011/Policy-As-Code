import json
import re
import requests

POLICY_FILE = "output/policy_text.txt"
OUTPUT_FILE = "output/policy_rules.json"

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen3:8b"


def call_ollama(policy_text):
    prompt = f"""
You are extracting policy rules from a policy document.

Extract ONLY explicit rules related to:

- PII
- SPII
- CPII

The policy may contain rules in tables, paragraphs, bullets,
numbered sections, or mixed formats.

Do not depend on section numbers, headings, rule ID patterns,
or table structure.

For every rule return ONLY:

{{
  "rule_id": "exact rule ID from policy",
  "category": "PII or SPII or CPII",
  "description": "description of the rule",
  "trigger_fields": ["fields explicitly stated by the policy"],
  "outcome": "FLAG or BLOCK or PASS"
}}

IMPORTANT FIELD RULE:

If the policy explicitly lists trigger fields, copy them exactly.

Do NOT:
- add synonyms
- add related fields
- add inferred fields
- add fields from your general knowledge
- add fields merely because they sound related

Example:

Policy:
username + email_domain + organisation

Correct:
"trigger_fields": [
  "username",
  "email_domain",
  "organisation"
]

Incorrect:
"trigger_fields": [
  "username",
  "email_domain",
  "organisation",
  "domain"
]

For CPII combination rules, include every attribute explicitly
listed in the combination.

Do not invent rule IDs.

Do not invent rules.

Do not duplicate rules.

Do not extract:
- policy metadata
- policy administration
- review requirements
- testing notes
- general remediation requirements
- unrelated requirements

Return ONLY valid JSON.

The JSON must have exactly this structure:

{{
  "rules": [
    {{
      "rule_id": "PII-001",
      "category": "PII",
      "description": "Example",
      "trigger_fields": ["field"],
      "outcome": "FLAG"
    }}
  ]
}}

POLICY TEXT:
--------------------
{policy_text}
--------------------
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0
            }
        },
        timeout=600
    )

    response.raise_for_status()

    raw = response.json()["response"]

    # Remove thinking blocks if Qwen produces them
    raw = re.sub(
        r"<think>.*?</think>",
        "",
        raw,
        flags=re.DOTALL
    ).strip()

    print("\n===== OLLAMA RESPONSE =====")
    print(raw)
    print("===== END OLLAMA RESPONSE =====\n")

    try:
        return json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"JSON error at position: {e.pos}")
        print(f"JSON error: {e}")

        # Save the raw response for debugging
        with open(
            "output/ollama_raw_response.txt",
            "w",
            encoding="utf-8"
        ) as f:
            f.write(raw)

        raise ValueError(
            "Ollama returned malformed JSON. "
            "Raw response saved to "
            "output/ollama_raw_response.txt"
        )


def validate_rules(result):

    if isinstance(result, dict):
        rules = result.get("rules")

    elif isinstance(result, list):
        rules = result

    else:
        raise ValueError(
            "Unexpected Ollama output format."
        )

    if not isinstance(rules, list):
        raise ValueError(
            "Ollama output does not contain a rules array."
        )

    valid_categories = {
        "PII",
        "SPII",
        "CPII"
    }

    valid_outcomes = {
        "PASS",
        "FLAG",
        "BLOCK"
    }

    validated = []

    for rule in rules:

        if not isinstance(rule, dict):
            continue

        rule_id = rule.get("rule_id")
        category = rule.get("category")
        description = rule.get("description")
        trigger_fields = rule.get("trigger_fields")
        outcome = rule.get("outcome")

        if not rule_id:
            print("Skipping rule without rule_id")
            continue

        if category not in valid_categories:
            print(
                f"Skipping {rule_id}: "
                f"invalid category {category}"
            )
            continue

        if not isinstance(trigger_fields, list):
            print(
                f"Skipping {rule_id}: "
                "trigger_fields is not a list"
            )
            continue

        if outcome not in valid_outcomes:
            print(
                f"Skipping {rule_id}: "
                f"invalid outcome {outcome}"
            )
            continue

        # Python determines this.
        #
        # Direct PII/SPII:
        # any listed field triggers the rule.
        #
        # CPII:
        # all listed fields form the combination.
        if category == "CPII":
            condition_type = "ALL"
        else:
            condition_type = "ANY"

        validated.append({
            "rule_id": str(rule_id),
            "category": category,
            "description": description or "",
            "trigger_fields": [
                str(field)
                for field in trigger_fields
            ],
            "condition_type": condition_type,
            "outcome": outcome
        })

    return validated


def remove_duplicates(rules):

    unique_rules = []
    seen_ids = set()

    for rule in rules:

        rule_id = rule["rule_id"]

        if rule_id in seen_ids:
            print(
                f"Duplicate removed: {rule_id}"
            )
            continue

        seen_ids.add(rule_id)
        unique_rules.append(rule)

    return unique_rules


def save_rules(rules):

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            rules,
            f,
            indent=2,
            ensure_ascii=False
        )


def main():

    print("================================")
    print("POLICY RULE EXTRACTION")
    print("================================")

    print("\nReading policy text...")

    try:

        with open(
            POLICY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            policy_text = f.read()

    except FileNotFoundError:

        raise FileNotFoundError(
            f"Policy text not found: {POLICY_FILE}"
        )

    if not policy_text.strip():

        raise ValueError(
            "Policy text is empty."
        )

    print(
        f"Policy text length: "
        f"{len(policy_text)} characters"
    )

    print("\nSending policy to Ollama...")
    print(f"Model: {MODEL}")
    print(f"Ollama: {OLLAMA_URL}")

    result = call_ollama(policy_text)

    print("Validating extracted rules...")

    rules = validate_rules(result)

    print(
        f"Rules before deduplication: "
        f"{len(rules)}"
    )

    rules = remove_duplicates(rules)

    save_rules(rules)

    print("\n================================")
    print("EXTRACTION COMPLETE")
    print("================================")

    print(
        f"Rules extracted: {len(rules)}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    counts = {
        "PII": 0,
        "SPII": 0,
        "CPII": 0
    }

    for rule in rules:
        counts[rule["category"]] += 1

    print("\nRules by category:")
    print(f"  PII  : {counts['PII']}")
    print(f"  SPII : {counts['SPII']}")
    print(f"  CPII : {counts['CPII']}")

    print("\nExtracted rules:")

    for rule in rules:

        print(
            f"  {rule['rule_id']} "
            f"({rule['category']}) "
            f"→ {rule['condition_type']} "
            f"→ {rule['outcome']}"
        )


if __name__ == "__main__":
    main()