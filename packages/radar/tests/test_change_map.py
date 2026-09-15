from forkit_radar.sessions.change_map import render


def record(events, *, consistent=True):
    return {"changes": events, "between_changes": [{"category": "files", "label": "outside.py"}],
            "evolution": {"status": "consistent" if consistent else "unavailable"}, "partial": False}


def test_map_keeps_private_labels_as_text_and_excludes_unattributed_gap():
    html = render(record([{"category": "files", "label": '<img onerror="bad">/file.py'},
                          {"category": "dependencies", "label": "playwright"}]))
    assert '<img onerror=' not in html
    assert '&lt;img onerror=' in html
    assert "outside.py" not in html
    assert "not a live route" in html
    assert "authorship weren’t captured" in html


def test_map_does_not_invent_activity_when_evidence_is_unavailable_or_empty():
    events = [{"category": "files", "label": "changed.py"}]
    assert 'map-zone' not in render(record(events, consistent=False))
    assert render(record([])) == ""


def test_many_changed_areas_are_bounded_without_losing_the_remainder_count():
    events = [{"category": "files", "label": f"folder-{index}/file.py"} for index in range(20)]
    html = render(record(events))
    assert html.count('data-map-zone=') == 6
    assert '<strong>15</strong>' in html
    assert '9 more in receipt Details' in html
