"""Shared real-data identities and v1 storage; imported identically by CLI/library."""
from pathlib import Path
from engine.detection.m4_handoff import Source,Store,Invalid
from engine.ingestion import m3_storage
from engine.detection.m4_storage import Guard

SOURCE_DIRECTORY = Path('/var/lib/hids/m3')
STATE_DIRECTORY = Path('/var/lib/hids/m4/store')
PAGES = 512
POLICY = m3_storage.defaults(PAGES, 1)


class LiveSource(Source):
    ORIGIN = 'audit_plugin'
    BINDING_DOMAIN = 'hids.m4.live.binding/1'

    def directory_policy(self):
        if self.directory != SOURCE_DIRECTORY or self.directory != Path('/var/lib/hids/m3'):
            raise Invalid('fixed real source required')


class LiveStore(Store):
    GUARD_TYPE = Guard
    APPLICATION_ID = 0x48344c31
    LAB_ONLY = False
    DOMAIN = 'hids.m4.live'

    def __init__(self, directory=STATE_DIRECTORY, *, create=False):
        if directory != STATE_DIRECTORY or directory != Path('/var/lib/hids/m4/store'):
            raise Invalid('fixed real destination required')
        super().__init__(directory, create=create, max_pages=PAGES, storage=dict(POLICY), lab_only=False)

    def import_page(self, source, rules=(), *, limit=64):
        if type(source) is not LiveSource or rules:
            raise Invalid('selected live source and disabled rules required')
        return super().import_page(source, (), limit=limit)

    def evaluate_pending(self, *, limit=64):
        # The approved trial enables no real-data or demo rules.
        for table in ('m4h_rules', 'm4h_evaluations', 'm4h_alerts'):
            if self.db.execute('SELECT count(*) FROM ' + table).fetchone() != (0,):
                raise Invalid('rules disabled for real-data trial')
        return 0


