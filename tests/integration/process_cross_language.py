"""Synthetic C++ parser/normalizer and independent Python receipt agreement."""
import copy
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from engine.ingestion import process_contract as c

tool=sys.argv[1]
p=subprocess.run([tool,'--generate'],capture_output=True,check=True,timeout=10)
events=[json.loads(line) for line in p.stdout.splitlines()]
assert len(events)==3
for event in events:c.validate(event,event['source'],'synthetic')
cases=[]
for event in events:
    cases.append((c.dump(event),True))
    for key,value in [('tid',0),('tid',True),('tgid',2147483648),('cpu',-1),('timestamp_ns','18446744073709551616'),('timestamp_ns','01'),('what_code',False)]:
        bad=copy.deepcopy(event);bad['native'][key]=value;cases.append((c.dump(bad),False))
    for where,key,value in [('normalized','x',1),('source','mode','live'),('timestamps','activity_wall_time','2026-11-13T00:00:00.000000Z')]:
        bad=copy.deepcopy(event);bad[where][key]=value;cases.append((c.dump(bad),False))
    bad=copy.deepcopy(event);bad['normalized']['process']['pid']=float(event['native']['tgid']);cases.append((c.dump(bad),False))
    bad=copy.deepcopy(event);bad['normalized']['process']['thread']['id']=True;cases.append((c.dump(bad),False))
    raw=c.dump(event);cases.append((raw[:-1]+',"event_id":"duplicate"}',False))
source=events[0]['source']
for raw,expected in cases:
    try:c.validate(c.decode(raw.encode()),source,'synthetic');python=True
    except (c.Invalid,ValueError):python=False
    native=subprocess.run([tool,'--validate'],input=raw+'\n',text=True,capture_output=True,timeout=5).returncode==0
    assert python==native==expected,(python,native,expected)
print('Cross-language cases passed:',len(cases))
