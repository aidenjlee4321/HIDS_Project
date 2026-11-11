"""Closed sanitized resource-incident evidence; never retains native payloads."""
import json

from engine.ingestion.m3_progress import ProgressError

NUMBERS = {'event_bytes_before', 'event_records_before', 'trigger_begin', 'trigger_end',
           'group_limit', 'group_record_limit', 'aggregate_limit', 'retained_accounted_bytes',
           'retained_records', 'retained_record_limit', 'requested_accounted_bytes',
           'observed_active_ms', 'observed_monotonic_ms', 'paused_ms'}


def validate(value):
    if type(value) is not dict or value.keys() != NUMBERS | {'policy', 'reason', 'incoming_for_event'}:
        raise ProgressError('invalid resource evidence')
    if type(value['policy']) is not int or value['policy'] != 1 or value['reason'] not in (
            'event_bytes', 'event_records', 'aggregate_bytes', 'aggregate_records'):
        raise ProgressError('invalid resource policy')
    if type(value['incoming_for_event']) is not bool or any(
            type(value[key]) is not int or not 0 <= value[key] < 2**63 for key in NUMBERS):
        raise ProgressError('invalid resource number')
    v = value
    if not (v['trigger_begin'] < v['trigger_end'] and 0 < v['group_limit'] <= 16*1024*1024 and
            v['group_limit'] <= v['aggregate_limit'] <= 32*1024*1024 and
            0 < v['group_record_limit'] <= 65536 and 0 < v['retained_record_limit'] <= 65536 and
            v['retained_records'] <= v['retained_record_limit'] and
            v['retained_accounted_bytes'] <= v['aggregate_limit'] and
            v['event_bytes_before'] <= v['group_limit'] and v['event_records_before'] <= v['group_record_limit'] and
            v['event_bytes_before']+1024*v['event_records_before'] <= v['retained_accounted_bytes'] and
            v['observed_active_ms'] <= v['observed_monotonic_ms'] and
            v['paused_ms'] == v['observed_monotonic_ms']-v['observed_active_ms']):
        raise ProgressError('inconsistent resource accounting')
    length = v['trigger_end']-v['trigger_begin']
    if v['requested_accounted_bytes'] != length+1024:
        raise ProgressError('resource charge mismatch')
    reason = v['reason']
    if reason == 'event_bytes' and not (v['incoming_for_event'] and v['event_bytes_before']+length > v['group_limit']):
        raise ProgressError('event byte limit not exceeded')
    if reason == 'event_records' and not (v['incoming_for_event'] and v['event_records_before']+1 > v['group_record_limit']):
        raise ProgressError('event record limit not exceeded')
    if reason == 'aggregate_bytes' and v['retained_accounted_bytes']+v['requested_accounted_bytes'] <= v['aggregate_limit']:
        raise ProgressError('aggregate byte limit not exceeded')
    if reason == 'aggregate_records' and v['retained_records'] < v['retained_record_limit']:
        raise ProgressError('retained record limit not exceeded')
    return json.dumps(v, sort_keys=True, separators=(',', ':'))
