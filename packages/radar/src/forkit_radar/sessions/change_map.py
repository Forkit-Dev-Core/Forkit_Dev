"""A bounded view of recorded changes, never a fabricated agent trajectory."""

from html import escape

LABELS = {"dependencies": "Dependencies", "tools": "MCP / tools", "models": "Models",
          "configuration": "Settings", "passport": "Passport"}


def render(record):
    if record["evolution"]["status"] != "consistent":
        return '<p class="quiet">Change map unavailable: history evidence needs attention.</p>'
    groups = {}
    for event in record["changes"]:
        category = event["category"]
        path = event["label"]
        label = (path.split("/", 1)[0] + "/" if "/" in path else "Project root") if category == "files" else LABELS[category]
        groups.setdefault((category, label), []).append(event)
    if not groups:
        return ""
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    zones = [(label, events) for (_category, label), events in ordered[:5]]
    if len(ordered) > 5:
        zones.append(("Other changed areas", [event for _, events in ordered[5:] for event in events]))
    buttons, descriptions = [], []
    for index, (label, events) in enumerate(zones):
        safe = escape(label, quote=True)
        count = len(events)
        buttons.append(f'<button type="button" class="map-zone map-zone-{index}" data-map-zone="{index}" aria-pressed="false" title="{safe}"><span class="zone-dot" aria-hidden="true"></span><span class="zone-name">{safe}</span><strong>{count}</strong><span class="zone-unit">recorded change{"s" if count != 1 else ""}</span></button>')
        items = "".join('<li>' + escape(event["label"]) + '</li>' for event in events[:6])
        more = f'<li>{count - 6} more in receipt Details</li>' if count > 6 else ''
        descriptions.append(f'<div data-map-detail="{index}" hidden><strong>{safe}</strong><ul>{items}{more}</ul></div>')
    partial = " · partial coverage" if record["partial"] else ""
    return ('<section class="change-map" aria-label="Map of recorded changes">'
            '<div class="map-heading"><div><h3>Where things changed</h3>'
            f'<p class="quiet">This session{partial}</p></div>'
            '<button class="secondary map-replay" type="button">Replay highlights</button></div>'
            '<div class="map-rooms">' + ''.join(buttons) + '</div>'
            '<p class="map-caption">Recorded changes, not a live route. Order and authorship weren’t captured.</p>'
            '<div class="map-details" aria-live="polite">' + ''.join(descriptions) + '</div></section>')
