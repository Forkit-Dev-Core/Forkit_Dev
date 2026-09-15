"""Real Git/SQLite lifecycle integration and adversarial callback/config boundaries."""
import argparse
import json
import subprocess
from pathlib import Path

import pytest
from forkit_radar.capture.cli import configuration, receive
from forkit_radar.jsonio import ContractError
from forkit_radar.sessions.storage import SessionStore
from forkit_radar.sessions.cards import project as card
from forkit_radar.sessions.summary import build


@pytest.fixture
def setup(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    subprocess.run(['git', 'init', '-q', str(project)], check=True)
    (project / 'main.py').write_text('x = 1\n')
    return argparse.Namespace(agent='codex', project=project, store=tmp_path/'store', agent_manifest=None, registry=None, passport_id=None)


def event(args, name, **extra):
    data = dict(session_id='external-123', cwd=str(args.project), hook_event_name=name, source='startup', transcript_path='/never/open/secret.jsonl', prompt='DO_NOT_PERSIST_123', **extra)
    if args.agent == 'cursor':
        data.update(workspace_roots=[str(args.project)], is_background_agent=False)
    return json.dumps(data).encode()


@pytest.mark.parametrize('agent,start,end', [('codex','SessionStart','SessionEnd'), ('claude-code','SessionStart','SessionEnd'), ('cursor','sessionStart','sessionEnd')])
def test_hooks_capture_once_without_private_payload(setup, agent, start, end):
    setup.agent=agent
    receive(setup, event(setup,start))
    receive(setup, event(setup,start))
    (setup.project/'main.py').write_text('x = 2\n')
    receive(setup, event(setup,end))
    receive(setup, event(setup,end))
    store=SessionStore(setup.store)
    assert len(store.history())==1 and not store.active()
    receipt=store.receipt()
    assert len(receipt.file_changes)==1 and receipt.tool_basis=='hook_reported'
    assert receipt.outcome=='hook_end' and receipt.elapsed_ms is not None
    assert receipt.comparison==('partial' if agent=='cursor' else 'complete')
    assert card(receipt).tool_basis=='hook_reported'
    assert build(store)['periods']['history']['receipts']==1
    raw=(setup.store/'sessions.sqlite3').read_bytes()
    assert b'DO_NOT_PERSIST_123' not in raw and b'/never/open/' not in raw and b'external-123' not in raw


def test_foreign_end_cannot_finish_manual_or_other_session(setup):
    store=SessionStore(setup.store)
    started,_=store.start(setup.project,tool='cursor')
    with pytest.raises(ContractError): receive(setup,event(setup,'SessionEnd'))
    assert store.active()[0].started.session_id==started.session_id
    store.finish(started.session_id)
    receive(setup,event(setup,'SessionStart'))
    raw=json.loads(event(setup,'SessionEnd')); raw['session_id']='foreign'
    with pytest.raises(ContractError): receive(setup,json.dumps(raw).encode())
    assert len(store.active())==1


def test_compaction_wrong_scope_and_missing_start(setup):
    receive(setup,event(setup,'SessionEnd'))
    assert not setup.store.exists()
    raw=json.loads(event(setup,'SessionStart')); raw['source']='compact'
    receive(setup,json.dumps(raw).encode())
    assert not setup.store.exists()
    raw['source']='startup'; raw['cwd']=str(setup.project.parent)
    with pytest.raises(ContractError): receive(setup,json.dumps(raw).encode())
    with pytest.raises(ContractError): receive(setup,b'x'*1048577)


def test_resume_preserves_prior_history_and_recovery(setup):
    receive(setup,event(setup,'SessionStart'))
    store=SessionStore(setup.store)
    store.finish(store.active()[0].started.session_id,outcome='recovered')
    receive(setup,event(setup,'SessionStart'))
    receive(setup,event(setup,'SessionEnd'))
    assert len(store.history())==2
    assert store.history()[1].comparison=='partial'


def test_configuration_uses_official_shapes_and_quotes_paths(setup):
    setup.store=setup.store.parent/"space ' and $(private)"
    for agent in ('codex','claude-code','cursor'):
        setup.agent=agent
        config=configuration(setup,setup.project)
        if agent=='cursor':
            assert config['version']==1 and set(config['hooks'])=={'sessionStart','sessionEnd'}
        else:
            assert set(config['hooks'])=={'SessionStart','SessionEnd'}
            assert config['hooks']['SessionEnd'][0]['hooks'][0]['timeout'] <= 10
        assert '--store' in json.dumps(config) and 'transcript' not in json.dumps(config)
