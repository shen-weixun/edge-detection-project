import csv,hashlib,json
from pathlib import Path
from dataclasses import asdict
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def file_sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise FileExistsError(p)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def table(p,rows):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def rng_state(a):return canonical(a.rng.bit_generator.state).decode()
def weight_sha(a):return hashlib.sha256(b''.join(w.tobytes() for w in a.online)).hexdigest()
def arrays_equal(a,b):return all(np.array_equal(x,y) for x,y in zip(a,b))
def task_rows(tasks):return [asdict(t) for t in tasks]
