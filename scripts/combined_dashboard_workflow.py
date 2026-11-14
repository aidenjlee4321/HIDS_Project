#!/usr/bin/env python3
"""Named verified synthetic dashboard scope. No root, stores, sources or install."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import dev
import m3_workflow as w


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-manifest',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--node',type=Path,required=True);p.add_argument('--modules',type=Path,required=True);a=p.parse_args()
    if sys.platform!='linux' or os.getuid()==0:raise RuntimeError('ordinary_linux_user_required')
    root=Path(__file__).resolve().parents[1];dev.verify(root,a.expected_manifest);w.ROOT=root
    run=w.Run(a.output,'combined_dashboard_synthetic',a.expected_manifest);error=None
    try:
        for name,pattern in [('process_view','test_process_view.py'),('combined_http','test_combined_dashboard_http.py'),('history_regression','test_history*.py'),('sessions_regression','test_dashboard*.py'),('setup_regression','test_setup*.py'),('installer_regression','test_development_install.py')]:
            run.phase(name,[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p',pattern])
        run.phase('source_control_regression',[sys.executable,'-B','-m','unittest','discover','-s','tests/unit','-p','test_process_setup.py'])
        run.phase('session_https',[sys.executable,'-B',str(root/'tests/integration/dashboard_session_https.py'),'--expected-manifest',a.expected_manifest,'--output',str(run.path/'session-transport')])
        front=run.path/'frontend-build';shutil.copytree(root/'frontend',front);(front/'node_modules').symlink_to(a.modules,target_is_directory=True)
        env={'PATH':str(a.node.parent)+':'+os.environ['PATH']}
        run.phase('client',[str(a.node),'--test',str(root/'tests/frontend/test_session_client.ts')],env=env)
        run.phase('types',[str(a.node),str(a.modules/'typescript/bin/tsc'),'--noEmit','--project',str(front/'tsconfig.json')],env=env)
        for name in ('dashboard','history','setup'):
            run.phase('build_'+name,[str(a.node),str(a.modules/'vite/bin/vite.js'),'build',str(front),'--config',str(front/('vite.'+name+'.config.ts'))],env=env)
        dev.verify(root,a.expected_manifest)
    except Exception as e:error=str(e)
    run.finish(error);print('RESULT_DIRECTORY',run.path);return 1 if error else 0
if __name__=='__main__':raise SystemExit(main())
