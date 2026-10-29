import json
import sqlite3
import sys
from datetime import UTC, datetime

from app.config import Settings
from app.models import parse_project
from app.scoring import is_cross_category_match, score_project


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings()
    skill_ids = set(settings.skill_ids)
    conn = sqlite3.connect(settings.db_path)
    rows = conn.execute("SELECT raw, budget_uah, first_seen_at, reject_reason FROM projects ORDER BY id").fetchall()

    report = []
    for raw, budget_uah, first_seen_at, reason in rows:
        project = parse_project(json.loads(raw))
        cross = not project.skill_ids & skill_ids and is_cross_category_match(project)
        if reason not in (None, "skills") or (reason == "skills" and not cross):
            continue
        score = score_project(project, budget_uah, datetime.fromisoformat(first_seen_at), cross)
        report.append((score.value, project, score, cross))

    for value, project, score, cross in sorted(report, key=lambda r: r[0], reverse=True):
        tag = " [інша категорія]" if cross else ""
        print(f"{value:3d} | {project.id} | {project.name[:60]}{tag}")
        print(f"      + {', '.join(score.pros) or '-'}")
        print(f"      - {', '.join(score.cons) or '-'}")
    print(f"\nВсього: {len(report)}")


if __name__ == "__main__":
    main()
