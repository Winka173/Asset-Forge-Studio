"""Import existing concept once. No network calls and no fabricated golden/candidate."""
import shutil
import uuid
from apps.api import store
from apps.api.inspection import inspect_image


def bootstrap():
    with store.connect() as db:
        if db.execute("SELECT 1 FROM artifacts WHERE role='concept'").fetchone():
            return
    source = store.ROOT / "doc/852446485_1648007553499526_667194451249758572_n.png"
    folder = store.DATA / "projects/runavelle/assets/ARCHER_TOWER_T3/versions" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    target = folder / "concept.png"
    shutil.copyfile(source, target)
    record = store.add_artifact(target, "concept", "Archer Tower concept", inspect_image(target) | {
        "origin": "provided_in_doc", "license": "NEEDS_REVIEW", "approval": "NEEDS_REVIEW"})
    print(record["id"], record["sha256"])


if __name__ == "__main__":
    bootstrap()
