"""Optional CLI uses the same phase-separated measurement as the web profiler."""
import argparse
import csv
import random
from pathlib import Path
from .profiles import FIELDS, measure_row
from .. import inference

def build_profile(images, output, max_images=30, repeats=3, seed=42):
    if repeats < 3 or max_images < 1:
        raise ValueError("repeats >= 3 and max_images >= 1 required")
    import os
    root=Path(os.getenv("DATASET_ROOT", "/datasets")).resolve()
    directory=Path(images).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("Images must be inside DATASET_ROOT")
    paths=sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if len(paths)<max_images:
        raise ValueError("Insufficient images")
    inference.initialize_model()
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS);writer.writeheader()
        for path in random.Random(seed).sample(paths,max_images):
            writer.writerow(measure_row("",path.relative_to(root).as_posix(),directory.name,repeats))
    return max_images

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--images",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--max-images",type=int,default=30)
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--seed",type=int,default=42)
    args=parser.parse_args()
    print("Measured",build_profile(args.images,args.output,args.max_images,args.repeats,args.seed),"images; web profiles should be created through /api/offloading/profiles")

if __name__ == "__main__": main()
