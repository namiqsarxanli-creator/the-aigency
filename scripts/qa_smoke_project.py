"""Create one realistic local QA project and run the production state machine end-to-end."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agency import TERMINAL_STATUSES, advance_project, create_project
from app.database import SessionLocal
from app.db_models import Workspace

BRIEF = (
    "Bakıda yeni açılan premium artisan qəhvə məkanı 'Səma Coffee' üçün Instagram postu hazırla. "
    "Məqsəd açılış həftəsində 20-35 yaşlı şəhər auditoriyasını məkana gətirməkdir. "
    "Ton isti, zövqlü və insani olsun; 20% açılış təklifini vurğula. Vizualda real barista, "
    "təbii səhər işığı və estetik qəhvə dükanı interyeri istifadə et. AI görünüşlü şəkil olmasın."
)

def main():
    db = SessionLocal()
    try:
        workspace = db.query(Workspace).order_by(Workspace.id).first()
        project = create_project(db, BRIEF, workspace_id=workspace.id if workspace else None)
        for step in range(80):
            advance_project(db, project)
            db.refresh(project)
            print(f"step={step + 1} status={project.status}", flush=True)
            if project.status in TERMINAL_STATUSES:
                break
        print(f"PROJECT_ID={project.id}")
        print(f"SHARE_TOKEN={project.share_token}")
        print(f"STATUS={project.status}")
        print(f"OUTPUT_TYPE={project.output_type}")
        print(f"IMAGE_URL={project.deliverable_image_url or ''}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
