"""Your Terraform state file holds the keys: find them.

Terraform stores every attribute of every resource in its state, including
the secrets it generated: database passwords, service account keys, HMAC keys
for a warehouse that reads object storage. Marking an output `sensitive`
hides it from the terminal. It does not remove it from the state.

Run it on a state file you are allowed to read:

    terraform state pull > state.json
    python scan_state.py state.json

or with no arguments, on a made-up state with fake values.

Python standard library only (json, re), no installs.
"""

import json
import re
import sys

SECRET_NAMES = re.compile(r"(secret|password|private_key|token|credential)", re.I)

SAMPLE_STATE = {
    "version": 4,
    "resources": [
        {"type": "google_storage_hmac_key", "name": "warehouse",
         "instances": [{"attributes": {"access_id": "GOOG1EXAMPLEACCESSID",
                                        "secret": "FAKE+base64+secret+value/example",
                                        "service_account_email": "warehouse-sa@example.iam.gserviceaccount.com"},
                        "sensitive_attributes": [[{"type": "get_attr", "value": "secret"}]]}]},
        {"type": "random_password", "name": "db",
         "instances": [{"attributes": {"length": 24, "result": "FAKE-generated-password"},
                        "sensitive_attributes": [[{"type": "get_attr", "value": "result"}]]}]},
        {"type": "google_service_account_key", "name": "puller",
         "instances": [{"attributes": {"name": "projects/example/serviceAccounts/x/keys/y",
                                        "private_key": "ZmFrZS1rZXktbWF0ZXJpYWw=",
                                        "public_key": "ZmFrZS1wdWJsaWM="}}]},
        {"type": "google_storage_bucket", "name": "landing",
         "instances": [{"attributes": {"name": "example-landing", "location": "EU"}}]},
    ],
}

# attributes that hold a secret even though their name doesn't say so
KNOWN = {("random_password", "result"), ("google_sql_user", "password")}


def findings(state: dict):
    for res in state.get("resources", []):
        for inst in res.get("instances", []):
            marked = {p[0]["value"] for p in inst.get("sensitive_attributes", []) if p and "value" in p[0]}
            for attr, value in inst.get("attributes", {}).items():
                if not value or not isinstance(value, str):
                    continue
                if SECRET_NAMES.search(attr) or (res["type"], attr) in KNOWN:
                    if "public" in attr:
                        continue
                    yield f"{res['type']}.{res['name']}", attr, attr in marked, len(value)


if __name__ == "__main__":
    state = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else SAMPLE_STATE
    rows = list(findings(state))
    print(f"{'resource':38} {'attribute':12} {'marked sensitive':17} stored in state")
    for addr, attr, marked, n in rows:
        print(f"{addr:38} {attr:12} {('yes' if marked else 'NO'):17} yes, {n} chars, plain text")
    print(f"\n{len(rows)} secrets in this state. Marked or not, anyone who can read the state can read them.")
    print("Protect the backend: encryption, versioning, and read access for the pipeline only.")
