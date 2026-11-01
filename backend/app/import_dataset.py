import argparse
import os
from pathlib import Path
from sqlalchemy.dialects.postgresql import insert
from .db import Base, engine, Session, Sample
from .datasets import lfw_samples, wider_samples

def main():
    parser = argparse.ArgumentParser(description="匯入已解壓的 LFW / WIDER FACE；重跑會更新而不重複")
    parser.add_argument("dataset", choices=["lfw", "wider"])
    parser.add_argument("--images", required=True, help="相對 DATASET_ROOT 的圖片目錄")
    parser.add_argument("--annotations")
    parser.add_argument("--split", choices=["train", "val"], default="val")
    args = parser.parse_args()
    if args.dataset == "wider" and not args.annotations:
        parser.error("WIDER FACE 需要 --annotations")
    root = Path(os.getenv("DATASET_ROOT", "/datasets")).resolve()
    rows = lfw_samples(root, args.images) if args.dataset == "lfw" else wider_samples(root, args.images, args.annotations, args.split)
    Base.metadata.create_all(engine)
    count = 0
    with Session.begin() as session:
        for row in rows:
            stmt = insert(Sample).values(**row)
            session.execute(stmt.on_conflict_do_update(index_elements=["dataset", "path"], set_={"label": stmt.excluded.label, "boxes": stmt.excluded.boxes}))
            count += 1
        if count == 0:
            raise ValueError("沒有找到任何圖片，未匯入資料")
    print(f"已匯入 {count} 張圖片")

if __name__ == "__main__":
    main()
