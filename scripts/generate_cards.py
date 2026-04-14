#!/usr/bin/env python3
"""
Generate intelligence cards from normalized data.
Cards are the final output format for analysis.
"""

import json
from datetime import date
from pathlib import Path


def main():
    today = date.today().isoformat()
    normalized_dir = Path(__file__).parent.parent / "data" / "normalized"
    cards_dir = Path(__file__).parent.parent / "data" / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    # Load events
    events_path = normalized_dir / "events.json"
    if not events_path.exists():
        print("No events.json found")
        return

    with open(events_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    # Filter today's events
    today_events = [e for e in events if e.get("date", "")[:10] == today]

    # Generate cards for today
    cards = []
    for event in today_events:
        card = {
            "id": event.get("id"),
            "date": event.get("date"),
            "type": "intel_card",
            "companies": event.get("companies", []),
            "topics": event.get("topics", []),
            "impact": event.get("impact", "neutral"),
            "title": event.get("title", ""),
            "summary": event.get("summary", ""),
            "source_count": len(event.get("sources", [])),
            "sources": event.get("sources", [])
        }
        cards.append(card)

    # Save as JSONL
    card_file = cards_dir / f"{today}.jsonl"
    with open(card_file, "w", encoding="utf-8") as f:
        for card in cards:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")

    print(f"Generated {len(cards)} cards for {today}")

    # Also create summary report
    reports_dir = Path(__file__).parent.parent / "reports" / "daily"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_content = f"""# Daily Intelligence Report - {today}

## Summary
- Total Events: {len(today_events)}
- Companies Mentioned: {len(set(c for e in today_events for c in e.get('companies', [])))}

## Events by Impact

### Positive
"""
    for e in [e for e in today_events if e.get("impact") == "positive"]:
        report_content += f"- **{e.get('title')}**\n  {e.get('summary', '')[:100]}...\n\n"

    report_content += "\n### Negative\n"
    for e in [e for e in today_events if e.get("impact") == "negative"]:
        report_content += f"- **{e.get('title')}**\n  {e.get('summary', '')[:100]}...\n\n"

    report_content += "\n### Neutral\n"
    for e in [e for e in today_events if e.get("impact") == "neutral"][:10]:
        report_content += f"- {e.get('title')}\n"

    with open(reports_dir / f"{today}.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"Generated report at {reports_dir / f'{today}.md'}")


if __name__ == "__main__":
    main()
