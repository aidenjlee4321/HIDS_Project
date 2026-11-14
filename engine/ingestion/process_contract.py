"""Approved process.lifecycle/0.1.0, independent Python receipt validation."""
import json
import re
import uuid
from engine.ingestion.m1_contract import Invalid, integer, keys, timestamp, uuid_valid, utc_now
from engine.ingestion.m1_contract import decode as bounded_decode, Framer

CONTRACT='process.lifecycle/0.1.0'
PROFILE='linux.cn_proc.lifecycle/1'
EVENT_LIMIT=16384
RESPONSE_LIMIT=1024
KINDS={'PROC_EVENT_FORK':(1,'fork','creation'),'PROC_EVENT_EXEC':(2,'exec','start'),'PROC_EVENT_EXIT':(2147483648,'exit','end')}

def require(value,code='invalid_event'):
    if not value:raise Invalid(code)

def canonical_uuid(value):
    try:require(type(value) is str and str(uuid.UUID(value))==value)
    except (ValueError,AttributeError):raise Invalid() from None

def scope(value,mode):
    keys(value,'adapter mode source_id activation_id boot_id profile')
    require(mode in ('live','synthetic') and value['mode']==mode)
    require(value['adapter']=='linux.cn_proc' and value['profile']==PROFILE)
    require(uuid_valid(value['source_id']) and uuid_valid(value['activation_id']))
    canonical_uuid(value['boot_id'])
    return value

def native(value):
    keys(value,'what what_code tid tgid parent cpu connector_sequence timestamp_ns native_exit_status native_exit_signal')
    require(type(value['what']) is str and value['what'] in KINDS)
    code,action,kind=KINDS[value['what']]
    integer(value['what_code'],code,code)
    for name in ('tid','tgid'):integer(value[name],1,2147483647)
    for name in ('cpu','connector_sequence'):integer(value[name],0,4294967295)
    raw=value['timestamp_ns']
    require(type(raw) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}',raw) is not None and int(raw)<=2**64-1)
    if action=='exec':require(value['parent'] is None)
    else:
        keys(value['parent'],'tid tgid')
        for name in ('tid','tgid'):integer(value['parent'][name],0,2147483647)
    for name in ('native_exit_status','native_exit_signal'):
        if action=='exit':integer(value[name],0,4294967295)
        else:require(value[name] is None)
    return action,kind

def validate(value,expected_source,mode='live',producer=None):
    keys(value,'protocol_version message_type contract_version ecs_reference_version event_id producer_instance_id source native timestamps normalized')
    require(type(value['protocol_version']) is int and value['protocol_version']==1,'unsupported_version')
    require(value['contract_version']==CONTRACT and value['ecs_reference_version']=='9.5.0','unsupported_version')
    require(value['message_type']=='event' and uuid_valid(value['event_id']) and uuid_valid(value['producer_instance_id']))
    scope(expected_source,mode);scope(value['source'],mode)
    require(value['source']==expected_source)
    if producer is not None:require(value['producer_instance_id']==producer)
    action,kind=native(value['native']);n=value['native']
    t=value['timestamps'];keys(t,'activity_wall_time activity_wall_time_reason observed_at observation')
    require(t['activity_wall_time'] is None and t['activity_wall_time_reason']=='not_emitted_by_source' and t['observation']=='native_decode')
    timestamp(t['observed_at'])
    process={'pid':n['tgid'],'thread':{'id':n['tid']}}
    if n['parent'] is not None and n['parent']['tgid']>0:process['parent']={'pid':n['parent']['tgid']}
    expected={'event':{'id':value['event_id'],'kind':'event','category':['process'],'type':[kind],'action':action,'provider':'linux.cn_proc','created':t['observed_at']},'process':process}
    # JSON text equality also distinguishes Boolean true from numeric 1.
    require(dump(value['normalized'])==dump(expected))
    require(len(dump(value).encode('ascii'))<=EVENT_LIMIT,'frame_too_large')
    return value

def dump(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
def decode(raw):return bounded_decode(raw,EVENT_LIMIT)
def frame(value):
    raw=dump(value).encode('ascii');require(len(raw)<=RESPONSE_LIMIT,'frame_too_large');return raw+b'\n'

REASONS=frozenset(('none','native_gap','queue_full','clock_failed','transport_failed','storage_failed','capacity','cancelled','source_failed','stopped'))
def status(value,expected_source,producer,mode='live'):
    keys(value,'protocol_version message_type contract_version source producer_instance_id acknowledged delivery incomplete stopped reason diagnostic_counts')
    require(type(value['protocol_version']) is int and value['protocol_version']==1)
    require(value['message_type']=='status' and value['contract_version']==CONTRACT)
    scope(value['source'],mode);require(value['source']==expected_source)
    require(uuid_valid(value['producer_instance_id']) and value['producer_instance_id']==producer)
    for k in ('acknowledged','delivery','incomplete','stopped'):require(type(value[k]) is bool)
    require(type(value['reason']) is str and value['reason'] in REASONS)
    require(type(value['diagnostic_counts']) is list and len(value['diagnostic_counts'])==20)
    for count in value['diagnostic_counts']:integer(count,0,4294967295)
    return value
