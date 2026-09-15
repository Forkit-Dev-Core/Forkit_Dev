"""Exercise a released offline bundle with real Git, SQLite, Passport and cards."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    checks=[]
    with tempfile.TemporaryDirectory(prefix='forkit-public-') as temp:
        root=Path(temp).resolve(); extracted=root/'extracted'; extracted.mkdir()
        with zipfile.ZipFile(args.bundle) as archive:
            if any(Path(n).is_absolute() or '..' in Path(n).parts for n in archive.namelist()): raise ValueError('unsafe archive')
            archive.extractall(extracted)
        app=root/'app'; bin_dir=root/'bin'; project=root/'project'; project.mkdir()
        env={k:v for k,v in os.environ.items() if not k.startswith(('FORKIT','PYTHON','PIP_'))}
        env.update(PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_CONFIG_FILE=os.devnull,HOME=str(root),FORKIT_USAGE_STORE=str(root/'usage'),PATH=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH',''))
        def run(argv,cwd=project):
            result=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,capture_output=True,text=True)
            if result.returncode: raise RuntimeError(result.stdout+'\n'+result.stderr)
            return result.stdout
        run(['sh','install.sh','--prefix',app,'--bin-dir',bin_dir],extracted/'forkit-session-receipt')
        command=bin_dir/'forkit-radar'; checks.append('offline_hashed_install')
        assert '0.1.0b3' in run([command,'--version'])
        run(['git','init','-q',project]); (project/'main.py').write_text('value = 1\n')
        run([command,'start','--tool','codex']); (project/'main.py').write_text('value = 2\n')
        receipt=json.loads(run([command,'stop','--json'])); assert len(receipt['file_changes'])==1
        run([command,'history','--json']); run([command,'view','--output',root/'history.html'])
        run([command,'card','--output',root/'card.html']); run([command,'summary','--period','today','--json'])
        checks.extend(['session_files_and_duration','history_json','private_view','local_share_card','daily_summary'])
        # Core metadata is deliberately an example. Creation stays local and does not need a login.
        model=root/'model-input.json'; model.write_text(json.dumps({'passport_type':'model','name':'Local bundle validation model','version':'1.0','creator':{'name':'Release validation'},'task_type':'code-generation','architecture':'other'}))
        run([command,'passport','create','--input',model,'--output',root/'model.json'])
        checks.append('local_core_passport')
        run([command,'hooks','setup','--agent','codex']); config=project/'.codex/hooks.json'
        hooks=json.loads(config.read_text())['hooks']; hook_receipts=[]
        for event in ('SessionStart','SessionEnd'):
            if event=='SessionEnd': (project/'main.py').write_text('value = 3\n')
            callback=hooks[event][0]['hooks'][0]['command']
            # The generated command has been reviewed above and comes from this installed bundle.
            data={'session_id':'bundle-lifecycle','cwd':str(project),'hook_event_name':event,'source':'startup','prompt':'NEVER_STORED_BUNDLE_MARKER'}
            subprocess.run(callback,shell=True,cwd=project,env=env,input=json.dumps(data),text=True,check=True,capture_output=True)
        hook=json.loads(run([command,'receipt','--json'])); assert hook['tool_basis']=='hook_reported' and len(hook['file_changes'])==1
        assert b'NEVER_STORED_BUNDLE_MARKER' not in (root/'.forkit-radar/sessions.sqlite3').read_bytes()
        checks.append('installed_hook_callbacks')
        assert not (root/'usage').exists()
        checks.append('reporting_off_no_signup')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'bundle':args.bundle.name,'sha256':hashlib.sha256(args.bundle.read_bytes()).hexdigest(),'platform':sys.platform,'machine':platform.machine(),'python':platform.python_version(),'checks':checks,'status':'passed'},indent=2)+'\n')
    print(args.output.read_text())

if __name__=='__main__': main()
