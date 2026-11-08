"""Independent closed M2 contract. No OS collection or M1 schema changes."""
import json
import re
from engine.ingestion.m1_contract import Invalid, integer, keys, timestamp, uuid_valid

CONTRACT = 'm2.journal-ssh/0.1.0'
EVENT_LIMIT, RESPONSE_LIMIT = 65536, 2048
MAX_REVISION = 2**63-1
REASONS = frozenset('missing_required malformed_field duplicate_field binary_field field_too_large too_many_fields event_too_large'.split())
REJECTS = frozenset('invalid_json invalid_event unsupported_version frame_too_large id_conflict stale_revision inactive_source reader_busy'.split())
LIMITS = {'_COMM':64, '_EXE':1024, 'MESSAGE':4096, '_PID':10, '_UID':10,
          '_GID':10, '_SYSTEMD_UNIT':256, 'PRIORITY':1, '_TRANSPORT':32, 'MESSAGE_ID':32}
PAIRS = {('sshd-session','/usr/lib/openssh/sshd-session'), ('sshd','/usr/sbin/sshd')}
BASE = 'protocol_version message_type contract_version source_id activation_id event_id cursor expected_revision observation'


def text(s, maximum, minimum=0, ascii_only=False):
    if type(s) is not str or '\0' in s:
        raise Invalid()
    try:
        size = len(s.encode('utf-8', errors='strict'))
    except UnicodeError as exc:
        raise Invalid('invalid_json') from exc
    if not minimum <= size <= maximum or (ascii_only and not s.isascii()):
        raise Invalid()


def decimal(s, maximum, minimum=0):
    if type(s) is not str or not re.fullmatch(r'0|[1-9][0-9]{0,19}', s) or not minimum <= int(s) <= maximum:
        raise Invalid()


def event_id(source, cursor):
    if not uuid_valid(source):
        raise Invalid()
    text(cursor,512,1,True)
    if any(not 32 <= ord(c) <= 126 for c in cursor):
        raise Invalid()
    return 'j1.'+source+'.'+cursor.encode('ascii').hex()


def matches(fields):
    return (fields.get('_COMM'),fields.get('_EXE')) in PAIRS


def validate_event(obj):
    if type(obj) is not dict:
        raise Invalid()
    if type(obj.get('protocol_version')) is not int or type(obj.get('contract_version')) is not str:
        raise Invalid()
    if obj['protocol_version'] != 2 or obj['contract_version'] != CONTRACT:
        raise Invalid('unsupported_version')
    kind=obj.get('message_type')
    if kind not in ('journal_event','journal_rejection'):
        raise Invalid()
    keys(obj, BASE+(' journal fields activity_wall_time activity_wall_time_reason' if kind=='journal_event' else ' reason'))
    if not uuid_valid(obj['activation_id']) or obj['event_id'] != event_id(obj['source_id'],obj['cursor']):
        raise Invalid()
    integer(obj['expected_revision'],0,MAX_REVISION)
    obs=obj['observation'];keys(obs,'producer_instance_id observed_at')
    if not uuid_valid(obs['producer_instance_id']):
        raise Invalid()
    timestamp(obs['observed_at'])
    if kind=='journal_rejection':
        if type(obj['reason']) is not str or obj['reason'] not in REASONS:
            raise Invalid()
        return obj
    clocks=obj['journal'];keys(clocks,'boot_id realtime_us monotonic_us')
    if type(clocks['boot_id']) is not str or not re.fullmatch('[0-9a-f]{32}',clocks['boot_id']):
        raise Invalid()
    for k in ('realtime_us','monotonic_us'):
        decimal(clocks[k],2**64-1)
    if obj['activity_wall_time'] is not None or obj['activity_wall_time_reason']!='not_established':
        raise Invalid()
    fields=obj['fields'];keys(fields,' '.join(LIMITS))
    for k,limit in LIMITS.items():
        v=fields[k]
        if v is None:
            if k in ('_COMM','_EXE','MESSAGE'):
                raise Invalid()
            continue
        text(v,limit,1 if k in ('_COMM','_EXE','_TRANSPORT') else 0, k in ('_TRANSPORT','PRIORITY','MESSAGE_ID','_PID','_UID','_GID'))
        if k in ('_PID','_UID','_GID'):
            decimal(v,2147483647 if k=='_PID' else 4294967295,1 if k=='_PID' else 0)
        if k=='PRIORITY' and v not in tuple('01234567'):
            raise Invalid()
        if k=='MESSAGE_ID' and not re.fullmatch('[0-9a-f]{32}',v):
            raise Invalid()
    if not matches(fields):
        raise Invalid()
    return obj


def _pairs(items):
    obj={}
    for k,v in items:
        if k in obj:
            raise Invalid('invalid_json')
        obj[k]=v
    return obj


def _no_float(_):
    raise Invalid('invalid_json')


def decode(raw, limit=EVENT_LIMIT):
    if len(raw)>limit:
        raise Invalid('frame_too_large')
    if not raw or b'\r' in raw or b'\n' in raw or raw.startswith(b'\xef\xbb\xbf'):
        raise Invalid('invalid_json')
    depth=0;quoted=escaped=False
    for b in raw:
        if quoted:
            if escaped: escaped=False
            elif b==92: escaped=True
            elif b==34: quoted=False
        elif b==34: quoted=True
        elif b in (123,91):
            depth+=1
            if depth>8: raise Invalid('invalid_json')
        elif b in (125,93): depth-=1
    try:
        obj=json.loads(raw.decode('utf-8',errors='strict'),object_pairs_hook=_pairs,parse_float=_no_float,parse_constant=_no_float)
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise Invalid('invalid_json') from exc
    if type(obj) is not dict: raise Invalid()
    return obj


def frame(obj, limit=EVENT_LIMIT):
    raw=json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    if len(raw)>limit: raise Invalid('frame_too_large')
    return raw+b'\n'


def canonical(obj):
    validate_event(obj)
    stable={k:v for k,v in obj.items() if k not in ('activation_id','expected_revision','observation')}
    return frame(stable).decode('ascii')[:-1]


def validate_response(obj, pending):
    if type(obj) is not dict or type(obj.get('protocol_version')) is not int or obj['protocol_version']!=2:
        raise Invalid()
    kind=obj.get('message_type')
    if kind=='ack':
        keys(obj,'protocol_version message_type event_id result checkpoint_revision code')
        integer(obj['checkpoint_revision'],1,MAX_REVISION)
        if obj['event_id']!=pending or type(obj['result']) is not str or obj['result'] not in ('stored','duplicate','rejected_record'):
            raise Invalid()
        if (obj['result']=='rejected_record' and (type(obj['code']) is not str or obj['code'] not in REASONS)) or (obj['result']!='rejected_record' and obj['code'] is not None):
            raise Invalid()
    elif kind in ('reject','error'):
        keys(obj,'protocol_version message_type event_id code')
        if type(obj['code']) is not str: raise Invalid()
        if kind=='reject':
            if obj['event_id'] not in (None,pending) or obj['code'] not in REJECTS: raise Invalid()
        elif obj['event_id']!=pending or obj['code']!='storage_error': raise Invalid()
    else: raise Invalid()
    return obj
