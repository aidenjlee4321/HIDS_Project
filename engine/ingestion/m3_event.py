"""Versioned sanitized event metadata and bounded rejection diagnostics."""
from engine.ingestion.m1_contract import timestamp,Invalid
import re
from engine.ingestion.m3_progress import ProgressError

PROFILE='linux.audit.aarch64.string/1'
ARCH=0xc00000b7
REASONS=frozenset('''unspecified resource_limit timeout_lifetime timeout_inactivity
auparse_capacity auparse_empty auparse_event_count auparse_field auparse_identity
auparse_ineligible auparse_missing_eoe auparse_missing_event auparse_missing_field
auparse_record auparse_record_count auparse_record_mismatch auparse_unexpected_eoe
incomplete_execution invalid_context_record invalid_execution_fields invalid_path_record
invalid_syscall unsupported_execution_record execve_argument_order execve_incomplete
execve_invalid_argc execve_invalid_argument execve_invalid_field execve_invalid_fragment
execve_invalid_length execve_invalid_record execve_missing_argc execve_unclosed_event
execve_unexpected_field'''.split())


def observation(value):
    if value is None:return (None,None,None)
    if (type(value) is not dict or value.keys()!={'version','arch','profile','first_observed_unix_ns'} or
            type(value['version']) is not int or value['version']!=1 or
            type(value['arch']) is not int or value['arch']!=ARCH or value['profile']!=PROFILE or
            type(value['first_observed_unix_ns']) is not int or not 0<=value['first_observed_unix_ns']<2**63):
        raise ProgressError('invalid observation metadata')
    return value['arch'],value['profile'],value['first_observed_unix_ns']


def stamp(value):
    try:timestamp(value)
    except Invalid:raise ProgressError('invalid backend timestamp') from None
    return value


def reason(value):
    if value is None:return 'unspecified'
    if type(value) is not str or value not in REASONS:raise ProgressError('invalid rejection reason')
    return value


def diagnostics(db):
    available=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m3_rejections'").fetchone())
    if not available:return dict(available=False,items=[],truncated=False)
    rows=db.execute("""SELECT d.identity,r.reason,r.recorded_at FROM m3_disposition d
        LEFT JOIN m3_rejections r USING(identity) WHERE d.state='rejected'
        ORDER BY d.rowid DESC LIMIT 21""").fetchall()
    return dict(available=True,items=[dict(identity=i,reason=r,recorded_at=t) for i,r,t in rows[:20]],truncated=len(rows)>20)


def validate_diagnostics(value):
    if (type(value) is not dict or value.keys()!={'available','items','truncated'} or
            type(value['available']) is not bool or type(value['truncated']) is not bool or
            type(value['items']) is not list or len(value['items'])>20):
        raise ProgressError('invalid diagnostic response')
    if not value['available'] and (value['items'] or value['truncated']):raise ProgressError('unavailable diagnostics have no items')
    for item in value['items']:
        if type(item) is not dict or item.keys()!={'identity','reason','recorded_at'}:raise ProgressError('invalid diagnostic item')
        if type(item['identity']) is not str or not re.fullmatch(r'[0-9]{1,20}\.[0-9]{1,9}:[0-9]{1,20}',item['identity']):raise ProgressError('invalid diagnostic identity')
        if item['reason'] is not None:reason(item['reason'])
        if item['recorded_at'] is not None:stamp(item['recorded_at'])
