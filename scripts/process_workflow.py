#!/usr/bin/env python3
"""Verified Linux process-pipeline offline scope. Never subscribes or installs."""
import argparse
import os
from pathlib import Path
import sys
import dev
import m3_workflow as workflow

def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    if sys.platform!='linux' or os.getuid()==0:raise RuntimeError('ordinary_linux_user_required')
    root=Path(__file__).resolve().parents[1];dev.verify(root,args.expected_manifest);workflow.ROOT=root
    run=workflow.Run(Path(args.output),'process_pipeline_offline',args.expected_manifest);error=None
    try:
        common=['c++','-std=c++20','-Wall','-Wextra','-Wpedantic','-Werror','-Icollector/include','-Icollector/third_party']
        sources=['collector/src/pilot/contract.cpp','collector/src/process/pipeline.cpp','collector/src/process/stream.cpp','collector/src/process/runtime.cpp','collector/src/process_collector.cpp','collector/src/process_connector_protocol.cpp','collector/src/linux_process_connector.cpp']
        objects=[]
        for n,source in enumerate(sources):
            obj=run.path/(str(n)+'.o');run.phase('compile_'+str(n),common+['-c',source,'-o',str(obj)]);objects.append(str(obj))
        run.phase('native_link',common+['tests/unit/process_pipeline_test.cpp',*objects,'-o',str(run.path/'process-test')])
        run.phase('native_test',[str(run.path/'process-test')])
        for name,flags in [('process-collector',[]),('process-owned-trial',['-DHIDS_PROCESS_ACCEPTANCE'])]:
            run.phase(name,common+flags+['collector/src/process/main.cpp',*objects,'-o',str(run.path/name)])
        run.phase('sender_link',common+['tests/integration/process_pipeline_sender.cpp',*objects,'-o',str(run.path/'process-sender')])
        run.phase('receiver',[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test_process_receiver.py'],env={'HIDS_PROCESS_SENDER':str(run.path/'process-sender')})
        run.phase('python',[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test_process_pipeline.py'])
        run.phase('process_setup',[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test_process_setup.py'])
        run.phase('setup_regression',[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test_setup*.py'])
        run.phase('cross_language',[sys.executable,'-B','tests/integration/process_cross_language.py',str(run.path/'process-test')])
        dev.verify(root,args.expected_manifest)
    except Exception as exc:error=str(exc)
    run.finish(error);print('RESULT_DIRECTORY',run.path)
    return 1 if error else 0
if __name__=='__main__':raise SystemExit(main())
