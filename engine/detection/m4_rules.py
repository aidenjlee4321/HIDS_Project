"""One explicitly approved non-demo rule. No discovery or automatic enablement."""
import json
from pathlib import Path
import stat
from engine.detection.m4_pilot import Invalid,canonical,digest,load_json
from engine.ingestion.m3_progress import _canonical_execution
from engine.ingestion.m3_event import PROFILE

RULE_ID='linux.audit.configured-root-shell'
RULE_REVISION='1'
RULE_HASH='597c033085d36600dafb65b3b972333443a540d0995c900529a9a181c53852e2'
RULE_PATH=Path(__file__).resolve().parents[2]/'rules/process/configured-root-shell.json'
REFERENCE=dict(id=RULE_ID,revision=RULE_REVISION,hash=RULE_HASH)


def validate_rule(value):
    # Exact content pin also distinguishes Boolean/float constants from uint32.
    if type(value) is not dict or digest('hids.m4.live.rule/1',value)!=RULE_HASH:
        raise Invalid('unapproved rule definition/revision')
    return json.loads(canonical(value))


def validate_references(values):
    if type(values) is not list or len(values)>1:
        raise Invalid('bounded approved rule selection required')
    if values and (type(values[0]) is not dict or canonical(values[0])!=canonical(REFERENCE)):
        raise Invalid('exact approved rule id/revision/hash required')
    return values


def load_rules(values):
    validate_references(values)
    if not values:return []
    if RULE_PATH.resolve()!=RULE_PATH:raise Invalid('canonical rule path required')
    info=RULE_PATH.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o644:
        raise Invalid('root-owned rule definition required')
    for parent in (RULE_PATH.parent,RULE_PATH.parent.parent,RULE_PATH.parent.parent.parent):
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise Invalid('untrusted rule directory')
    return [validate_rule(load_json(RULE_PATH))]


def evaluate(execution,profile,rule):
    _canonical_execution(execution);rule=validate_rule(rule)
    if profile!=PROFILE:return 'unable','source_profile_unavailable',{}
    if not all(execution[p['field']]==p['eq'] for p in rule['all_of']):return 'no_match','predicate_not_equal',{}
    return 'matched','all_predicates_equal',{p['field']:execution[p['field']] for p in rule['all_of']}
