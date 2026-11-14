"""Exact owner-approved v1→v2 transition; no database opened on import."""
import sqlite3
from engine.detection.m4_handoff import DDL

MIGRATION = '''ALTER TABLE m4h_bindings ADD COLUMN rule_plan TEXT NOT NULL DEFAULT '[]';
CREATE TABLE m4h_alerts_v2(
 alert_id TEXT PRIMARY KEY,event_key TEXT NOT NULL,rule_id TEXT NOT NULL,revision TEXT NOT NULL,
 explanation TEXT NOT NULL,matched_values TEXT NOT NULL,demo INTEGER NOT NULL CHECK(demo IN (0,1)),
 severity TEXT NOT NULL CHECK(severity='informational'),created_at TEXT NOT NULL,
 UNIQUE(event_key,rule_id,revision),FOREIGN KEY(event_key,rule_id,revision) REFERENCES m4h_evaluations);
INSERT INTO m4h_alerts_v2 SELECT * FROM m4h_alerts;
DROP TABLE m4h_alerts;
ALTER TABLE m4h_alerts_v2 RENAME TO m4h_alerts;
PRAGMA user_version=2;'''

# SQLite normalizes ALTER/RENAME SQL. Derive the exact accepted fresh/migrated
# schema from known static statements in memory, instead of weakening checks.
def schema_v2():
    db=sqlite3.connect(':memory:')
    try:
        db.executescript(DDL+MIGRATION)
        return '\n'.join(db.execute('SELECT sql FROM sqlite_master WHERE name=?',(name,)).fetchone()[0]+';'
            for name in ('m4h_bindings','m4h_events','m4h_rules','m4h_evaluations','m4h_alerts'))
    finally:db.close()

DDL_V2=schema_v2()
