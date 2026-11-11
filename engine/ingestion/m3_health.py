"""Independently validated, bounded host Audit metadata. Never collects OS data."""
import json
import time

from engine.ingestion.m1_contract import uuid_valid, utc_now
from engine.ingestion.m3_progress import ProgressError

FRESH_NS = 15_000_000_000
DDL = 'CREATE TABLE m3_health (activation TEXT PRIMARY KEY, generation TEXT NOT NULL, observation TEXT NOT NULL, summary TEXT NOT NULL, received_ns INTEGER NOT NULL, received_at TEXT NOT NULL)'
INCIDENTS = ('kernel_loss_increased', 'kernel_counter_reset', 'boot_changed', 'auditd_changed',
             'kernel_not_collecting', 'dispatcher_overflow', 'dispatcher_suspended', 'sampling_gap')


def exact(value, names):
    if type(value) is not dict or value.keys() != set(names.split()):
        raise ProgressError('invalid health shape')


def number(value, maximum=2**63-1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ProgressError('invalid health number')


def validate(value):
    exact(value, 'sample_ns kernel dispatcher')
    number(value['sample_ns'])
    k, d = value['kernel'], value['dispatcher']
    if type(k) is not dict or type(d) is not dict:
        raise ProgressError('invalid health sources')
    if k.get('state') == 'observed':
        exact(k, 'state boot_id auditd_pid lost backlog backlog_limit enabled')
        if not uuid_valid(k['boot_id']):
            raise ProgressError('invalid boot scope')
        for key in ('auditd_pid', 'lost', 'backlog', 'backlog_limit', 'enabled'):
            number(k[key], 2**32-1)
        if k['enabled'] > 2:
            raise ProgressError('invalid Audit enabled state')
    else:
        exact(k, 'state')
        if k['state'] not in ('unavailable', 'timeout', 'invalid'):
            raise ProgressError('invalid kernel observation')
    if d.get('state') in ('observed', 'stale'):
        exact(d, 'state report_mtime_ns age_ns active_plugins queue_depth queue_capacity overflow suspended')
        for key in ('report_mtime_ns', 'age_ns', 'active_plugins', 'queue_depth', 'queue_capacity'):
            number(d[key])
        if type(d['overflow']) is not bool or type(d['suspended']) is not bool:
            raise ProgressError('invalid dispatcher flag')
        if d['queue_depth'] > d['queue_capacity'] or d['report_mtime_ns'] == 0:
            raise ProgressError('inconsistent dispatcher counts')
        if (d['state'] == 'observed') != (d['age_ns'] <= FRESH_NS):
            raise ProgressError('inconsistent report freshness')
    else:
        exact(d, 'state')
        if d['state'] not in ('missing', 'inaccessible', 'invalid', 'clock_uncertain'):
            raise ProgressError('invalid dispatcher observation')
    return value


def record(db, activation, generation, value, *, now_ns=None):
    validate(value)
    now = time.monotonic_ns() if now_ns is None else now_ns
    if not 0 <= now-value['sample_ns'] <= 3_000_000_000:
        raise ProgressError('health sample outside receipt window')
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'))
    db.execute('BEGIN IMMEDIATE')
    try:
        row = db.execute('SELECT generation,observation,summary,received_ns FROM m3_health WHERE activation=?', (activation,)).fetchone()
        summary = {'baseline': None, 'previous': None, 'preexisting_kernel_loss': False,
                   'unavailable_seen': {'kernel': False, 'dispatcher': False},
                   'incidents': dict.fromkeys(INCIDENTS, False)}
        if row:
            if row[0] != generation:
                raise ProgressError('health generation mismatch')
            previous_sample = json.loads(row[1])['sample_ns']
            if value['sample_ns'] <= previous_sample:
                if value['sample_ns'] == previous_sample and row[1] == payload:
                    db.execute('COMMIT')
                    return 'duplicate'
                raise ProgressError('health replay conflict')
            summary = json.loads(row[2])
            summary.setdefault('unavailable_seen', {'kernel': False, 'dispatcher': False})
            summary['incidents']['sampling_gap'] |= now-row[3] > FRESH_NS
        k, d = value['kernel'], value['dispatcher']
        summary['unavailable_seen']['kernel'] |= k['state'] != 'observed'
        summary['unavailable_seen']['dispatcher'] |= d['state'] != 'observed'
        if k['state'] == 'observed':
            previous = summary['previous']
            if summary['baseline'] is None:
                summary['baseline'] = k
                summary['preexisting_kernel_loss'] = k['lost'] > 0
            if previous is not None:
                if previous['boot_id'] != k['boot_id']:
                    summary['incidents']['boot_changed'] = True
                else:
                    summary['incidents']['kernel_loss_increased'] |= k['lost'] > previous['lost']
                    summary['incidents']['kernel_counter_reset'] |= k['lost'] < previous['lost']
                    summary['incidents']['auditd_changed'] |= k['auditd_pid'] != previous['auditd_pid']
            summary['previous'] = k
            summary['incidents']['kernel_not_collecting'] |= k['enabled'] == 0 or k['auditd_pid'] == 0
        if d['state'] == 'observed' and d['active_plugins'] > 0:
            summary['incidents']['dispatcher_overflow'] |= d['overflow']
            summary['incidents']['dispatcher_suspended'] |= d['suspended']
        db.execute('INSERT OR REPLACE INTO m3_health VALUES (?,?,?,?,?,?)',
                   (activation, generation, payload, json.dumps(summary, sort_keys=True, separators=(',', ':')), now, utc_now()))
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    return 'recorded'


def status(db, current, *, now_ns=None):
    if current is None:
        return None
    row = db.execute('SELECT generation,observation,summary,received_ns,received_at FROM m3_health WHERE activation=?', (current['activation'],)).fetchone()
    if row is None:
        return None
    if row[0] != current['generation']:
        raise ProgressError('health history scope mismatch')
    now = time.monotonic_ns() if now_ns is None else now_ns
    age = now-row[3]
    observation = json.loads(row[1])
    active = current['state'] in ('ready', 'streaming')
    freshness = 'historical' if not active else 'fresh' if 0 <= age <= FRESH_NS else 'stale'
    kernel_state = 'sampled' if freshness == 'fresh' and observation['kernel']['state'] == 'observed' else 'unknown'
    d = observation['dispatcher']
    dispatcher_state = 'unknown'
    if freshness == 'fresh' and d['state'] in ('observed', 'stale') and d['age_ns']+age <= FRESH_NS:
        dispatcher_state = 'sampled' if d['active_plugins'] > 0 else 'inactive'
    summary = json.loads(row[2])
    baseline = summary['baseline']
    public_summary = {'baseline': None if baseline is None else
                      {key: baseline[key] for key in ('boot_id', 'auditd_pid', 'lost')},
                      'preexisting_kernel_loss': summary['preexisting_kernel_loss'],
                      'unavailable_seen': summary.get('unavailable_seen', {'kernel': False, 'dispatcher': False}),
                      'incidents': summary['incidents']}
    # Ended intervals may predate a reboot. Even a positive monotonic difference
    # cannot establish a shared clock epoch; retain receipt time and observation
    # without inventing a historical sample age. Active intervals never resume
    # across backend startup, so their current-epoch freshness remains meaningful.
    return {'freshness': freshness, 'age_ns': age if active and age >= 0 else None, 'received_at': row[4],
            'kernel': kernel_state, 'dispatcher': dispatcher_state,
            'observation': observation, 'summary': public_summary}


def validate_status(value):
    if value is None:
        return
    exact(value, 'freshness age_ns received_at kernel dispatcher observation summary')
    if value['freshness'] not in ('fresh', 'stale', 'historical', 'unavailable'):
        raise ProgressError('invalid health freshness')
    if value['age_ns'] is not None:
        number(value['age_ns'])
    elif value['freshness'] == 'fresh':
        raise ProgressError('fresh sample requires comparable clock age')
    if type(value['received_at']) is not str or len(value['received_at']) > 40:
        raise ProgressError('invalid health receipt time')
    if value['kernel'] not in ('sampled', 'unknown') or value['dispatcher'] not in ('sampled', 'inactive', 'unknown'):
        raise ProgressError('invalid health availability')
    validate(value['observation'])
    if value['freshness'] != 'fresh' and (value['kernel'] != 'unknown' or value['dispatcher'] != 'unknown'):
        raise ProgressError('historical or unavailable counters cannot be current')
    if value['kernel'] == 'sampled' and value['observation']['kernel']['state'] != 'observed':
        raise ProgressError('kernel sample has no observation')
    if value['dispatcher'] in ('sampled', 'inactive'):
        dispatcher = value['observation']['dispatcher']
        if dispatcher['state'] != 'observed' or dispatcher['age_ns'] + value['age_ns'] > FRESH_NS or (
                (value['dispatcher'] == 'inactive') != (dispatcher['active_plugins'] == 0)):
            raise ProgressError('dispatcher availability has no fresh observation')
    summary = value['summary']
    exact(summary, 'baseline preexisting_kernel_loss unavailable_seen incidents')
    exact(summary['incidents'], ' '.join(INCIDENTS))
    exact(summary['unavailable_seen'], 'kernel dispatcher')
    if type(summary['preexisting_kernel_loss']) is not bool or any(type(flag) is not bool for flag in
            (*summary['incidents'].values(), *summary['unavailable_seen'].values())):
        raise ProgressError('invalid health history flag')
    if summary['baseline'] is not None:
        baseline = summary['baseline']
        exact(baseline, 'boot_id auditd_pid lost')
        if not uuid_valid(baseline['boot_id']):
            raise ProgressError('invalid health baseline boot')
        number(baseline['auditd_pid'], 2**32-1)
        number(baseline['lost'], 2**32-1)
