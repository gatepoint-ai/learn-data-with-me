"""Environments as code: find drift between sandbox, dev and prod.

The same Terraform for every environment, with a small, declared set of
values allowed to differ (sizes, counts, names). Everything else differing is
drift, and drift is how "it worked in dev" happens.

The second check compares what exists in the cloud with what Terraform
manages: anything created by hand is a candidate for an import block.

Python standard library only, made-up configuration, no installs.
"""

ALLOWED_TO_DIFFER = {"prefix", "node_count_max", "db_tier", "machine_type", "deletion_protection"}

ENVS = {
    "sandbox": {"prefix": "x-sbx", "node_count_max": 2, "db_tier": "small", "machine_type": "e2-standard-4",
                "db_version": "POSTGRES_16", "log_lock_waits": "on", "private_ip_only": True,
                "chart_iam": "0.48.5", "deletion_protection": False},
    "dev":     {"prefix": "x-dev", "node_count_max": 3, "db_tier": "small", "machine_type": "e2-standard-4",
                "db_version": "POSTGRES_16", "log_lock_waits": "off", "private_ip_only": True,
                "chart_iam": "0.47.0", "deletion_protection": False},
    "prod":    {"prefix": "x-prd", "node_count_max": 6, "db_tier": "large", "machine_type": "e2-standard-16",
                "db_version": "POSTGRES_16", "log_lock_waits": "on", "private_ip_only": True,
                "chart_iam": "0.48.5", "deletion_protection": True},
}

MANAGED_BY_TERRAFORM = {"vpc", "subnet-gke", "subnet-db", "gke", "cloudsql", "bucket-main"}
EXISTS_IN_CLOUD = {"vpc", "subnet-gke", "subnet-db", "gke", "cloudsql", "bucket-main",
                   "bucket-backlog", "firewall-temp-ssh"}


def drift() -> list[tuple[str, dict]]:
    keys = sorted(set().union(*ENVS.values()) - ALLOWED_TO_DIFFER)
    return [(k, {e: cfg.get(k) for e, cfg in ENVS.items()})
            for k in keys if len({repr(cfg.get(k)) for cfg in ENVS.values()}) > 1]


if __name__ == "__main__":
    print("1) Settings that differ between environments but aren't allowed to:")
    for key, values in drift():
        print(f"   {key:16} " + "   ".join(f"{e}={v}" for e, v in values.items()))
    print("\n2) Resources in the cloud that Terraform doesn't manage (created by hand):")
    for res in sorted(EXISTS_IN_CLOUD - MANAGED_BY_TERRAFORM):
        print(f"   {res:18} -> write an import block, or delete it")
    print("\nSizes may differ. Versions, flags and network posture may not.")
