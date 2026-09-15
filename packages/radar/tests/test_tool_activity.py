"""Real Git/SQLite tests for opt-in activity, privacy, scope and retained history."""
import json
import subprocess
from pathlib import Path

import pytest

from forkit_radar.capture import automatic as auto
from forkit_radar.capture.activity import hostname, observation
from forkit_radar.sessions.cards import project as card
from forkit_radar.sessions.private_view import render
from forkit_radar.sessions.storage import SessionStore
from forkit_radar.sessions.summary import build
from forkit_radar.sessions.summary_cards import project as summary_card


@pytest.fixture
def local(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir(mode=0o700)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setenv('CODEX_HOME', str(home / '.codex'))
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(home / '.claude'))
    monkeypatch.setattr(auto, 'detected', lambda _: {'codex'})
    project = home / 'project'
    project.mkdir()
    subprocess.run(['git', 'init', '-q', project], check=True)
    (project / 'main.py').write_text('x = 1\n')
    return home, home / '.forkit-radar', project


def send(local, event, *, agent='codex', session='session-1', call='tool-1', tool='mcp__browser__browser_navigate', **extra):
    home, root, project = local
    data = {'hook_event_name': event, 'session_id': session, 'cwd': str(project), 'source': 'startup',
            'tool_name': tool, 'tool_use_id': call,
            'tool_input': {'url': 'https://user:NEVER_PASSWORD@docs.example.com/private/NEVER_PATH?token=NEVER_QUERY#NEVER_FRAGMENT',
                           'prompt': 'NEVER_PROMPT'},
            'tool_response': {'body': 'NEVER_RESULT'}, 'transcript_path': '/NEVER_TRANSCRIPT',
            **extra}
    if agent == 'cursor':
        data.update(workspace_roots=[str(project)], is_background_agent=False)
    return auto.automatic_receive(agent, root, auto.encode(data))


@pytest.mark.parametrize('agent,start,post,end', [('codex','SessionStart','PostToolUse','SessionEnd'),
    ('claude-code','SessionStart','PostToolUse','SessionEnd'),('cursor','sessionStart','postToolUse','sessionEnd')])
def test_repeated_sessions_privacy_and_public_exclusion(local, agent, start, post, end):
    _, root, project = local
    auto.setup(root, agents=[agent], activity=True)
    for n in (1,2):
        session = 'session-' + str(n)
        send(local, start, agent=agent, session=session)
        send(local, post, agent=agent, session=session)
        send(local, post, agent=agent, session=session)  # duplicate
        (project / 'main.py').write_text(f'x = {n+1}\n')
        send(local, end, agent=agent, session=session)
    store = SessionStore(root)
    report = build(store)
    assert report['total_receipts'] == 2
    for record in report['records']:
        assert record['activity']['state'] == 'partial'
        assert len(record['activity']['events']) == 1
        assert record['activity']['events'][0]['destination'] == 'docs.example.com'
        assert 'token' not in record['activity']['events'][0]
    raw = (root / 'sessions.sqlite3').read_bytes()
    assert b'NEVER_' not in raw and b'tool-1' not in raw
    html = render(report)
    assert b'Tools &amp; destinations' in html and b'docs.example.com' in html
    assert b'new receipts require reopening' in html
    assert 'docs.example.com' not in card(store.receipt()).model_dump_json()
    assert 'docs.example.com' not in summary_card(report, 'today').model_dump_json()
    assert not (root / 'usage').exists()
    assert json.loads((root / ('capture-status-' + agent + '.json')).read_text())['result'] == 'receipt_saved'


def test_opt_in_is_not_retroactive_and_disable_preserves_history(local):
    _, root, _ = local
    auto.setup(root)
    assert 'PostToolUse' not in auto.state(root)['agents']['codex']['groups']
    send(local, 'SessionStart')
    auto.setup(root, activity=True)
    send(local, 'PostToolUse')
    send(local, 'SessionEnd')
    assert build(SessionStore(root))['records'][0]['activity']['state'] == 'not_enabled'
    auto.setup(root)  # normal setup preserves explicit activity preference
    assert auto.setup(root, inspect=True)['agents'][0]['local_activity']
    send(local, 'SessionStart', session='session-2')
    send(local, 'PostToolUse', session='session-2')
    send(local, 'SessionEnd', session='session-2')
    auto.setup(root, activity=False)
    assert 'PostToolUse' not in auto.state(root)['agents']['codex']['groups']
    send(local, 'SessionStart', session='session-3')
    send(local, 'PostToolUse', session='session-3')
    send(local, 'SessionEnd', session='session-3')
    rows = build(SessionStore(root))['records']
    assert [r['activity']['state'] for r in rows] == ['not_enabled','partial','not_enabled']
    auto.setup(root, disable=True)
    assert len(SessionStore(root).history()) == 3


def test_foreign_late_and_unsupported_events_cannot_attach(local):
    _, root, _ = local
    auto.setup(root, activity=True)
    send(local, 'PostToolUse')  # no baseline
    assert not (root / 'sessions.sqlite3').exists()
    send(local, 'SessionStart')
    send(local, 'PostToolUse', session='foreign')
    send(local, 'PostToolUse', tool='Bash')
    send(local, 'PostToolUse', tool='WebSearch')  # Codex hosted search not observed
    send(local, 'PostToolUse', tool_use_id='invalid call id')
    send(local, 'SessionEnd')
    send(local, 'PostToolUse')  # late
    assert build(SessionStore(root))['records'][0]['activity']['events'] == []


def test_event_limit_does_not_break_session_finish(local):
    _, root, _ = local
    auto.setup(root, activity=True)
    send(local, 'SessionStart')
    for i in range(132):
        send(local, 'PostToolUse', call='call-' + str(i))
    send(local, 'SessionEnd')
    record = build(SessionStore(root))['records'][0]
    assert record['activity']['truncated'] and len(record['activity']['events']) == 128
    assert record['receipt']['status'] == 'completed'


def test_unknown_mcp_and_search_do_not_invent_destinations():
    base = {'tool_name':'mcp__private_server__custom_query','tool_use_id':'call-1','hook_event_name':'PostToolUse',
            'tool_input':{'url':'https://example.com/private'}}
    _, item = observation(base, 'codex')
    assert item == {'kind':'mcp_tool','destination':None,'outcome':'tool_returned'}
    base['tool_name']='WebSearch'
    _, item = observation(base, 'claude-code')
    assert item['kind']=='web_search' and item['destination'] is None
    base.update(tool_name='WebFetch',hook_event_name='PostToolUseFailure')
    _, item=observation(base,'claude-code')
    assert item['destination']=='example.com' and item['outcome']=='tool_reported_failure'
    base.update(tool_name='MCP:browser_navigate',hook_event_name='postToolUse')
    _, item=observation(base,'cursor')
    assert item['kind']=='browser_navigation' and item['destination']=='example.com'


def test_scope_status_distinguishes_parent_from_repository(local):
    home, _, project=local
    assert auto.workspace_state(project)=='eligible_git_project'
    assert auto.workspace_state(home)=='outside_local_git_project'


def test_cursor_post_event_can_omit_background_flag_only_with_matching_baseline(local):
    _,root,_=local
    auto.setup(root,agents=['cursor'],activity=True)
    send(local,'sessionStart',agent='cursor')
    data={'conversation_id':'session-1','workspace_roots':[str(local[2])],
          'hook_event_name':'postToolUse','tool_name':'MCP:browser_navigate',
          'tool_use_id':'cursor-call','tool_input':{'url':'http://localhost:1234/secret'}}
    auto.automatic_receive('cursor',root,auto.encode(data))
    send(local,'sessionEnd',agent='cursor')
    assert build(SessionStore(root))['records'][0]['activity']['events'][0]['destination']=='localhost'


@pytest.mark.parametrize('url,expected', [
    ('https://user:password@EXAMPLE.com:443/path?token=secret#private','example.com'),
    ('http://localhost:5186/secret','localhost'),('http://192.168.1.9/secret','local-network'),
    ('http://private.internal/secret','local-network'),('http://[::1]/secret','local-network'),
    ('https://docs.example.com','docs.example.com'),('https://my-domain.example.com','my-domain.example.com'),
    ('file:///private/secret',None),('javascript:alert(1)',None),('https://bad\nhost.example',None),
    ('https://[broken',None),('https://host/ ' ,None),(None,None)])
def test_destination_allowlist(url, expected):
    assert hostname(url) == expected


def test_corrupt_annotation_does_not_hide_receipt(local):
    _, root, _ = local
    auto.setup(root, activity=True)
    send(local,'SessionStart'); send(local,'SessionEnd')
    store=SessionStore(root)
    with store._connect(write=True) as db:
        db.execute('UPDATE settings SET value=? WHERE name=?',(b'{"private":"bad"}','activity:'+store.history()[0].session_id))
    report=build(store)
    assert report['records'][0]['activity']['state']=='unavailable'
    assert b'Activity evidence unavailable' in render(report)
