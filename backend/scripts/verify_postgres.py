"""Verify the local PostgreSQL contract, RLS policies, and concurrent job claims.

Usage (PowerShell):
  $env:DATABASE_URL = 'postgresql://...'
  python backend/scripts/verify_postgres.py

The script creates and removes synthetic rows. It never prints the connection
string or credentials.
"""

from __future__ import annotations

import concurrent.futures
import os
import sys
import uuid

import psycopg2
from psycopg2 import sql

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is required; no database connection string was printed or stored.")

    from app.config import database as db

    db.init_db()
    if not db.USE_POSTGRES:
        raise SystemExit("DATABASE_URL did not select PostgreSQL.")

    probe_role = f"evalia_rls_probe_{os.getpid()}"
    org_a = None
    org_b = None
    campaign_a = None
    campaign_b = None
    job_id = None
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(probe_role)))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {} ").format(sql.Identifier(probe_role)))
            cur.execute(sql.SQL("GRANT SELECT ON organizations, campaigns TO {} ").format(sql.Identifier(probe_role)))
            cur.execute("INSERT INTO organizations (name, slug) VALUES (%s, %s) RETURNING id", ("RLS Probe A", f"rls-a-{uuid.uuid4().hex[:8]}"))
            org_a = cur.fetchone()[0]
            cur.execute("INSERT INTO organizations (name, slug) VALUES (%s, %s) RETURNING id", ("RLS Probe B", f"rls-b-{uuid.uuid4().hex[:8]}"))
            org_b = cur.fetchone()[0]
            cur.execute("INSERT INTO campaigns (org_id, name) VALUES (%s, %s) RETURNING id", (org_a, "Campaign A"))
            campaign_a = cur.fetchone()[0]
            cur.execute("INSERT INTO campaigns (org_id, name) VALUES (%s, %s) RETURNING id", (org_b, "Campaign B"))
            campaign_b = cur.fetchone()[0]
            conn.commit()

            cur.execute(sql.SQL("SET ROLE {} ").format(sql.Identifier(probe_role)))
            cur.execute("SELECT set_config('evalia.current_org_id', %s, false)", (str(org_a),))
            cur.execute("SELECT id FROM campaigns ORDER BY id")
            visible_a = [row[0] for row in cur.fetchall()]
            cur.execute("SELECT set_config('evalia.current_org_id', %s, false)", (str(org_b),))
            cur.execute("SELECT id FROM campaigns ORDER BY id")
            visible_b = [row[0] for row in cur.fetchall()]
            cur.execute("RESET ROLE")
            assert visible_a == [campaign_a], f"RLS org A leak: {visible_a}"
            assert visible_b == [campaign_b], f"RLS org B leak: {visible_b}"
            print("RLS isolation: PASS")

            cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = current_schema() AND policyname LIKE 'evalia_rls_%'")
            policy_count = cur.fetchone()[0]
            assert policy_count >= 10, f"Expected RLS policies, found {policy_count}"
            print(f"RLS policy coverage: PASS ({policy_count} policies)")

        db.set_request_db_context(user_id=None, org_id=None)
        job_key = f"postgres-concurrency:{uuid.uuid4().hex}"
        job_id = db.enqueue_job("postgres_probe", {"probe": True}, idempotency_key=job_key, max_attempts=3)

        def claim(worker: str):
            return db.claim_job(job_id, worker, lease_seconds=60)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(claim, ("postgres-worker-a", "postgres-worker-b")))
        claimed = [item for item in claims if item is not None]
        assert len(claimed) == 1, f"Expected one atomic claim, got {len(claimed)}"
        print("Concurrent job claim: PASS (exactly one winner)")
    finally:
        db.clear_request_db_context()
        conn.rollback()
        with conn, conn.cursor() as cur:
            if job_id:
                cur.execute("DELETE FROM background_jobs WHERE id = %s", (job_id,))
            if campaign_a and campaign_b:
                cur.execute("DELETE FROM campaigns WHERE id IN (%s, %s)", (campaign_a, campaign_b))
            if org_a and org_b:
                cur.execute("DELETE FROM organizations WHERE id IN (%s, %s)", (org_a, org_b))
            cur.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {} ").format(sql.Identifier(probe_role)))
            cur.execute(sql.SQL("REVOKE ALL ON organizations, campaigns FROM {} ").format(sql.Identifier(probe_role)))
            cur.execute(sql.SQL("DROP ROLE IF EXISTS {} ").format(sql.Identifier(probe_role)))
        conn.close()

    print("PostgreSQL verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
