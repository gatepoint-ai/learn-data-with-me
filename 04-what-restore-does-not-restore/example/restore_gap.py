"""What restore doesn't restore: every byte is back, and the app still can't see its tables.

pg_restore brings back schemas, tables, data and the GRANTs on each object. It does
NOT bring back cluster-wide role state, which lives outside the database dump:
  - per-role settings, such as   ALTER ROLE app_user SET search_path TO ...
  - role memberships, such as    GRANT sales_rw TO app_user
Those are only in `pg_dumpall --globals-only`.

This script models a small catalog before and after a restore, replays what the
application does, and prints the exact statements to put back. Names are made up.

Python standard library only, no installs.
"""

# --- the catalog -------------------------------------------------------------
TABLES = {"sales.orders", "sales.customers", "ref.products"}          # all restored, with data
OBJECT_GRANTS = {                                                      # restored with the objects
    "sales.orders":    {"sales_rw", "sales_ro"},
    "sales.customers": {"sales_rw", "sales_ro"},
    "ref.products":    {"ref_ro"},
}

SOURCE_ROLES = {   # what the source cluster had (from pg_dumpall --globals-only)
    "app_user":    {"search_path": ["$user", "sales", "ref", "public"], "member_of": {"sales_rw", "ref_ro"}},
    "report_user": {"search_path": ["$user", "sales", "public"],        "member_of": {"sales_ro"}},
}
TARGET_ROLES = {   # what the target has after pg_restore: roles exist, their state doesn't
    "app_user":    {"search_path": ["$user", "public"], "member_of": set()},
    "report_user": {"search_path": ["$user", "public"], "member_of": set()},
}

# The queries, exactly as the code issues them: the app uses unqualified names, the report
# tool qualifies them with the schema.
APP_QUERIES = [("app_user", "orders"), ("app_user", "products"), ("report_user", "sales.customers")]


def run(role: str, table: str, roles: dict) -> str:
    """Resolve the name the way PostgreSQL does (search_path if unqualified), then check privileges."""
    state = roles[role]
    candidates = [table] if "." in table else []
    for schema in state["search_path"]:
        schema = role if schema == "$user" else schema
        if "." not in table:
            candidates.append(f"{schema}.{table}")
    for qualified in candidates:
        if qualified in TABLES:
            if OBJECT_GRANTS[qualified] & state["member_of"]:
                return f"ok ({qualified})"
            return f'ERROR: permission denied for table {qualified.split(".")[1]}'
    return f'ERROR: relation "{table}" does not exist'


def replay(source: dict, target: dict) -> list[str]:
    statements = []
    for role, wanted in source.items():
        if target[role]["search_path"] != wanted["search_path"]:
            path = ", ".join(f'"{s}"' if s == "$user" else s for s in wanted["search_path"])
            statements.append(f"ALTER ROLE {role} SET search_path TO {path};")
        for group in sorted(wanted["member_of"] - target[role]["member_of"]):
            statements.append(f"GRANT {group} TO {role};")
    return statements


def main() -> None:
    print(f"After pg_restore: {len(TABLES)} of {len(TABLES)} tables present, every row restored.\n")
    print("What the application sees:")
    for role, table in APP_QUERIES:
        print(f"   {role:<12} SELECT ... FROM {table:<16} -> {run(role, table, TARGET_ROLES)}")

    statements = replay(SOURCE_ROLES, TARGET_ROLES)
    print("\nMissing role state, taken from the globals dump (run as the role that holds ADMIN OPTION):")
    for s in statements:
        print(f"   {s}")

    fixed = {role: {"search_path": SOURCE_ROLES[role]["search_path"],
                    "member_of": set(SOURCE_ROLES[role]["member_of"])} for role in TARGET_ROLES}
    print("\nAfter replaying those lines and recycling the connection pool:")
    for role, table in APP_QUERIES:
        print(f"   {role:<12} SELECT ... FROM {table:<16} -> {run(role, table, fixed)}")
    print("\nNo data was lost at any point. The symptoms only looked like it.")


if __name__ == "__main__":
    main()
