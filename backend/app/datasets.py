"""Streaming parsers; paths must remain inside the mounted dataset directory."""
from pathlib import Path

def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("資料路徑超出 datasets 目錄")
    return path

def lfw_samples(root: Path, folder: str):
    directory = safe_path(root, folder)
    if not directory.is_dir():
        raise ValueError(f"找不到 LFW 目錄：{folder}")
    for path in sorted(directory.glob("*/*.jpg")):
        safe_path(root, str(path.relative_to(root)))
        yield dict(dataset="lfw", path=path.relative_to(root).as_posix(), label=path.parent.name, boxes=[])

def wider_samples(root: Path, folder: str, annotation: str, split: str):
    directory = safe_path(root, folder)
    with safe_path(root, annotation).open(encoding="utf-8") as stream:
        while line := stream.readline():
            name = line.strip()
            if not name:
                continue
            count = int(stream.readline().strip())
            if count < 0:
                raise ValueError("負數標註數量")
            boxes = []
            # Official zero-face entries have one all-zero placeholder row.
            for _ in range(max(1, count)):
                fields = [int(x) for x in stream.readline().split()]
                if len(fields) < 10:
                    raise ValueError(f"標註格式錯誤：{name}")
                x, y, w, h = fields[:4]
                if count and fields[7] == 0 and w > 0 and h > 0:
                    boxes.append([x, y, x + w, y + h])
            path = safe_path(root, str(directory.relative_to(root) / name))
            if not path.is_file():
                raise ValueError(f"缺少圖片：{name}")
            yield dict(dataset=f"wider_{split}", path=path.relative_to(root).as_posix(), label=name.split('/')[0], boxes=boxes)
