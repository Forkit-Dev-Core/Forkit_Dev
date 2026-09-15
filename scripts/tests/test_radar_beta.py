"""Questionnaire denominator, duplicate and privacy checks using independent cases."""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'summarize_radar_beta.py'
spec = importlib.util.spec_from_file_location('radar_beta', SCRIPT)
beta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(beta)
AS_OF = date(2026, 9, 22)


def record(**updates):
    return dict(schema_version='1.0', kind='forkit_beta_feedback', version=beta.VERSION,
                participant_id=str(uuid4()), report_id=str(uuid4()), recorded_on='2026-09-14', consent=True,
                stage='first_use', participant_type='external', platform='macos_arm64', tool='codex',
                workflow='cli', install='succeeded', exercise='real_project', receipt='created',
                time_to_result='under_5_minutes', usefulness='useful', incorrect_change='no',
                keep_installed='yes', repeat_use='not_yet', share_card='created', friction=['none']) | updates


def put(root, name, value):
    p = root / name
    p.write_text(json.dumps(value))
    return p


def test_empty_cohort_has_no_install_or_retention_claim(tmp_path):
    result = beta.summarize(tmp_path, as_of=AS_OF)
    assert result['external_first_use_respondents'] == 0
    assert result['total_installs'] is None
    assert result['repeat_use_lower_bound']['basis_points'] is None
    assert not result['pilot_targets']['reported_targets_reached']
    assert result['release_decision'] == 'manual_review_required'


def test_actual_denominators_exclusions_and_nonresponses(tmp_path):
    first = [record() for _ in range(8)]
    # One failure remains in the install denominator; one example is not activation.
    first[0].update(install='blocked', receipt='failed', exercise='not_attempted', usefulness='not_reviewed', incorrect_change='not_reviewed', share_card='not_attempted', friction=['prerequisites'])
    first[1]['exercise'] = 'guided_example'
    for i, v in enumerate(first):
        put(tmp_path, f'first-{i}.json', v)
    for i, v in enumerate(first[2:5]):
        put(tmp_path, f'follow-{i}.json', v | dict(report_id=str(uuid4()), stage='follow_up', recorded_on='2026-09-21', repeat_use='another_day'))
    put(tmp_path, 'team.json', record(participant_type='team'))
    put(tmp_path, 'fixture.json', record(participant_type='synthetic'))
    put(tmp_path, 'unmatched.json', record(stage='follow_up'))
    put(tmp_path, 'copied.json', first[0])
    r = beta.summarize(tmp_path, as_of=AS_OF)
    assert r['reported_install_success'] == beta.ratio(7, 8)
    assert r['real_project_receipts'] == 6
    assert r['reported_useful_real_receipts'] == beta.ratio(6, 6)
    assert r['repeat_use_lower_bound'] == beta.ratio(3, 8)
    assert r['repeat_use_among_follow_up_respondents'] == beta.ratio(3, 3)
    assert r['follow_up_nonresponses'] == 5
    assert r['duplicate_files_ignored'] == 1 and r['unmatched_follow_up_reports'] == 1
    assert r['excluded_team_or_synthetic_reports'] == 2
    assert r['pilot_targets']['reported_targets_reached']
    assert r['release_decision'] == 'manual_review_required'
    for v in first:
        assert v['participant_id'] not in json.dumps(r) and v['report_id'] not in json.dumps(r)


def test_immature_and_early_follow_up_do_not_inflate_retention(tmp_path):
    a, b = record(recorded_on='2026-09-21'), record()
    for i, v in enumerate((a, b)):
        put(tmp_path, f'{i}.json', v)
        put(tmp_path, f'f{i}.json', v | dict(report_id=str(uuid4()), stage='follow_up', recorded_on='2026-09-21' if i == 0 else '2026-09-15', repeat_use='another_day'))
    r = beta.summarize(tmp_path, as_of=AS_OF)
    assert r['follow_up_eligible_after_7_days'] == 1
    assert r['eligible_follow_up_responses'] == 0
    assert r['repeat_use_lower_bound'] == beta.ratio(0, 1)


@pytest.mark.parametrize('field,value', [
    ('source_code', 'PRIVATE'), ('consent', False), ('participant_id', 'user@example.org'),
    ('recorded_on', '2026-02-30'), ('recorded_on', '2026-09-23'), ('recorded_on', '2026-9-2'),
    ('usefulness', '<script>PRIVATE</script>'), ('usefulness', []), ('stage', 'unknown'),
    ('friction', ['none', 'privacy']), ('friction', ['privacy', 'privacy']), ('friction', []),
    ('friction', ['private path']), ('receipt', 'failed'), ('install', 'blocked'),
    ('exercise', 'not_attempted'), ('version', 'unknown'),
])
def test_invalid_private_or_contradictory_feedback_rejected(field, value):
    with pytest.raises(ValueError):
        beta.validate(record(**{field: value}), as_of=AS_OF)


@pytest.mark.parametrize('kind', ['duplicate_key', 'symlink', 'fifo', 'oversize', 'hardlink'])
def test_unsafe_input_files_are_refused(tmp_path, kind):
    p = tmp_path / 'input.json'
    if kind == 'duplicate_key':
        p.write_text('{"consent":true,"consent":false}')
    elif kind == 'symlink':
        p.symlink_to(put(tmp_path, 'outside.data', record()))
    elif kind == 'fifo':
        import os
        os.mkfifo(p)
    elif kind == 'hardlink':
        import os
        os.link(put(tmp_path, 'outside.data', record()), p)
    else:
        p.write_bytes(b'x' * 16385)
    with pytest.raises((OSError, ValueError)):
        beta.read_report(p, AS_OF)


def test_conflicting_stages_and_report_ids_require_review(tmp_path):
    v = record()
    put(tmp_path, 'first.json', v)
    p = put(tmp_path, 'duplicate.json', v | dict(report_id=str(uuid4()), usefulness='not_useful'))
    with pytest.raises(ValueError, match='multiple_reports'):
        beta.summarize(tmp_path, as_of=AS_OF)
    p.write_text(json.dumps(v | dict(participant_id=str(uuid4()))))
    with pytest.raises(ValueError, match='conflicting_report_id'):
        beta.summarize(tmp_path, as_of=AS_OF)


def test_withdrawal_recomputes_remaining_cohort(tmp_path):
    a = put(tmp_path, 'a.json', record())
    put(tmp_path, 'b.json', record())
    assert beta.summarize(tmp_path, as_of=AS_OF)['external_first_use_respondents'] == 2
    a.unlink()
    assert beta.summarize(tmp_path, as_of=AS_OF)['external_first_use_respondents'] == 1
