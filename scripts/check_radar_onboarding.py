"""Exercise the installed beta entry points and the exact shipped guided example."""
from __future__ import annotations

import argparse
import json
import platform
import shlex
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path


class Example(HTMLParser):
    selected = False
    text = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'pre' and dict(attrs).get('id') == 'guided':
            self.selected = True

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.selected = False

    def handle_data(self, data):
        if self.selected:
            self.text += data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guide', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix='forkit-beta-check-') as temporary:
        root = Path(temporary).resolve()
        store = root / 'private'
        projects = [root / 'real-project', root / 'separate-project']
        for p in projects:
            p.mkdir()
            subprocess.run(['/usr/bin/git', 'init', '-q', str(p)], check=True)
            (p / 'app.py').write_text('value = 1\n')
        def cli(*argv, cwd=projects[0], code=0):
            completed = subprocess.run([sys.executable, '-I', '-m', 'forkit_radar.cli', *map(str, argv)], cwd=cwd, capture_output=True, text=True)
            assert completed.returncode == code, (argv[0], completed.returncode, completed.stderr)
            return completed.stdout
        for _ in range(2):
            doctor = json.loads(cli('doctor', '--store', store, '--json'))
            assert doctor['ready'] and not store.exists()
            assert str(root) not in json.dumps(doctor)
        checks.append('installed_doctor_no_store_source_scan_or_private_paths')
        for p in projects:
            cli('start', '--tool', 'other', '--store', store, cwd=p)
        (projects[0] / 'app.py').write_text('value = 2\n')
        first = json.loads(cli('stop', '--store', store, '--json'))
        assert len(first['file_changes']) == 1
        assert len(json.loads(cli('session', 'active', '--store', store, '--json'))) == 1
        cli('stop', '--store', store, code=2)
        checks.append('project_stop_preserves_other_active_session_and_rejects_repeated_stop')
        cli('start', '--tool', 'other', '--store', store)
        (projects[0] / 'app.py').write_text('value = 3\n')
        second = json.loads(cli('stop', '--store', store, '--json'))
        assert second['previous_session_id'] == first['session_id']
        assert len(second['file_changes']) == 1
        checks.append('second_real_git_capture_reuses_existing_history_and_comparison')
        cli('stop', '--store', store, cwd=projects[1])
        view = root / 'private-view.html'
        card = root / 'card.html'
        cli('view', '--store', store, '--output', view)
        cli('card', second['session_id'], '--store', store, '--output', card)
        assert view.stat().st_mode & 0o777 == 0o600 and card.stat().st_mode & 0o777 == 0o600
        assert str(root) not in card.read_text()
        assert len(json.loads(cli('history', '--store', store, '--json'))) == 3
        checks.append('local_private_view_and_aggregate_card_without_account')
        assert json.loads(cli('metrics', 'status', '--store', store).split('\nLocal features')[0])['state'] == 'disabled'
        assert not (store / 'reporting.sqlite3').exists()
        checks.append('reporting_stays_disabled_without_profile_or_upload')
        reader = Example()
        reader.feed(args.guide.read_text())
        assert reader.text.startswith('(\nset -eu')
        command = shlex.quote(sys.executable) + ' -I -m forkit_radar.cli'
        example = reader.text.replace('~/.local/bin/forkit-radar', command)
        result = subprocess.run(['/bin/sh', '-c', example], cwd=root, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        sample = root / 'forkit-guided-history'
        receipt = json.loads(cli('receipt', '--store', sample, '--json'))
        assert len(receipt['file_changes']) == 1 and receipt['tool'] == 'other'
        assert len(json.loads(cli('history', '--store', store, '--json'))) == 3
        again = subprocess.run(['/bin/sh', '-c', example], cwd=root, capture_output=True, text=True)
        assert again.returncode != 0
        assert len(json.loads(cli('history', '--store', sample, '--json'))) == 1
        checks.append('exact_guide_example_is_isolated_and_refuses_existing_project')
    report = {'status': 'passed', 'platform': platform.platform(), 'python': platform.python_version(), 'checks': checks,
              'scope': 'Controlled local validation; no real tester, inference, signup or traction claim'}
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'checks': len(checks)}))


if __name__ == '__main__':
    main()
