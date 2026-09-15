"""Generate the clearly labeled illustrative product-page card from its strict schema."""

import argparse
from pathlib import Path

from forkit_radar.sessions.cards import Counts, Prior, SessionCard, html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    card = SessionCard(
        tool="claude-code", elapsed_minutes=42, outcome="manual_stop",
        file_state="complete", file_changes=27, possible_renames=0,
        dependencies=Counts(state="complete", added=2, removed=0, changed=0),
        tools=Counts(state="complete", added=1, removed=0, changed=0),
        models=Counts(state="complete", added=0, removed=0, changed=1),
        configuration=Counts(state="complete", added=0, removed=0, changed=0),
        passport="not_selected", passport_change="not_selected",
        since_previous=Prior(state="complete", files=31, metadata_entries=4),
        between_sessions=Prior(state="complete", files=4, metadata_entries=0),
    )
    content = html(card).replace("<h1>Your local share card</h1>",
        "<h1>Example share card · illustrative data</h1><p>This example is not an actual coding session. Generate your own with <code>forkit-radar card --output receipt.html</code>.</p>")
    path = Path(__file__).resolve().parents[1] / "packages/radar/site/example-card.html"
    if args.check:
        if path.read_text() != content:
            raise SystemExit("Example card drift; run scripts/generate_radar_card_example.py")
        print("Product-page example matches the card renderer.")
    else:
        path.write_text(content)


if __name__ == "__main__":
    main()
