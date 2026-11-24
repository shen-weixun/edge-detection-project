"""Frozen metadata-only group split; reuse valid measurements, checkpoint missing work.
Run inside the existing backend container. Never edits old Profiles or algorithms.
"""
import sys,os,json,csv,hashlib,random,platform,time
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from PIL import Image
from sqlalchemy import select
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import Session,Sample
from app.offloading import profiles
from app import inference
OUT=profiles.root()/'formal-evaluation';OUT.mkdir(exist_ok=True)
SEED=20261104;COUNTS={'training':40,'validation':20,'testing':100}
def save(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dhash(path):
 with Image.open(path) as image:
  v=list(image.convert('L').resize((9,8)).getdata())
 return sum((v[y*9+x]>v[y*9+x+1])<<(y*8+x) for y in range(8) for x in range(8))
def cache():
 saved={};history=set()
 for meta in sorted(profiles.listing(),key=lambda m:(m['created_at'],m['id'])):
  if meta.get('derived_from') or meta.get('split_role') or meta['status']!='completed':continue
  path=profiles.path_for(meta['id'],'.csv')
  if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=meta.get('csv_sha256'):continue
  for row in csv.DictReader(path.open(encoding='utf-8-sig')):
   history.add(row['source_path'])
   if row['success']=='True' and row['model']=='buffalo_l' and int(row['repeats'])>=3 and len(json.loads(row['inference_samples_ms']))>=3:
    saved.setdefault(row['source_path'],dict(row=row,profile_id=meta['id'],profile_metadata=meta))
 return saved,history

def plan():
 if (OUT/'plan.json').exists():return read(OUT/'plan.json')
 saved,history=cache();selected=[];excluded=[];digests=set();perceptual=[];inventory={};rng=random.Random(SEED)
 with Session() as session:
  for dataset in ('lfw','wider_train'):
   candidates=[dict(sample_id=i,source_path=p,dataset=dataset,group=dataset+'/'+Path(p).parent.name) for i,p in session.execute(select(Sample.id,Sample.path).where(Sample.dataset==dataset).order_by(Sample.id))]
   groups=sorted({r['group'] for r in candidates});rng.shuffle(groups);n=len(groups);role_groups={'training':groups[:n//2],'validation':groups[n//2:3*n//4],'testing':groups[3*n//4:]}
   inventory[dataset]=dict(images=len(candidates),groups=n,partition_groups=role_groups)
   for role,count in COUNTS.items():
    pool=[r for r in candidates if r['group'] in role_groups[role] and (role!='testing' or r['source_path'] not in history)];rng.shuffle(pool)
    if role!='testing':pool.sort(key=lambda r:r['source_path'] not in saved)
    chosen=[];used_groups=set()
    for r in pool:
     if dataset=='lfw' and r['group'] in used_groups:continue
     path=Path(os.getenv('DATASET_ROOT','/datasets'))/r['source_path']
     try:sha=hashlib.sha256(path.read_bytes()).hexdigest();dh=dhash(path)
     except Exception as e:excluded.append(dict(**r,reason='metadata_decode:'+str(e)));continue
     if sha in digests or any((dh^old).bit_count()<=4 for old in perceptual):excluded.append(dict(**r,reason='exact_or_dhash_distance_le4'));continue
     digests.add(sha);perceptual.append(dh);used_groups.add(r['group']);chosen.append(dict(**r,role=role,image_sha256=sha,dhash=f'{dh:016x}',reuse_profile_id=saved[r['source_path']]['profile_id'] if r['source_path'] in saved else None))
     if len(chosen)==count:break
    if len(chosen)!=count:raise RuntimeError(('Insufficient unique images',dataset,role,len(chosen)))
    selected+=chosen
 x=dict(schema='formal-dataset-v1',seed=SEED,counts=COUNTS,created_at=datetime.now(timezone.utc).isoformat(),inventory=inventory,selected=selected,excluded=excluded,
        rules='Metadata-only split frozen before missing inference. LFW person and WIDER event-folder disjoint; one image per LFW identity. Exact SHA256 and 64-bit dHash distance<=4 excluded before freeze. Test never previously measured in registered Profiles. Train/val prefer earlier valid measurements, never chosen by duration.',
        estimated_new_images=sum(not r['reuse_profile_id'] for r in selected),estimated_new_model_calls=4*sum(not r['reuse_profile_id'] for r in selected),prior_profile_ids=sorted({r['reuse_profile_id'] for r in selected if r['reuse_profile_id']}))
 save('plan.json',x);print('PLAN',Counter((r['dataset'],r['role']) for r in selected),'new',x['estimated_new_images'],'calls',x['estimated_new_model_calls'],flush=True);return x

def run():
 x=plan();saved,_=cache();folder=OUT/'measurements';folder.mkdir(exist_ok=True);inference.initialize_model()
 import insightface,onnxruntime
 device=dict(host=platform.node(),platform=platform.platform(),machine=platform.machine(),provider='CPUExecutionProvider',insightface=insightface.__version__,onnxruntime=onnxruntime.__version__)
 for i,r in enumerate(x['selected']):
  target=folder/(r['image_sha256']+'.json')
  if target.exists():continue
  path=Path(os.getenv('DATASET_ROOT','/datasets'))/r['source_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==r['image_sha256']
  if r['reuse_profile_id']:
   original=saved[r['source_path']];assert original['profile_id']==r['reuse_profile_id'];row=original['row'];provenance=dict(kind='reused_real_profile',profile_id=original['profile_id'],device=original['profile_metadata']['device'],model=original['profile_metadata']['model'],versions=original['profile_metadata'].get('versions'))
  else:
   row=profiles.measure_row(r['sample_id'],r['source_path'],r['dataset'],3);provenance=dict(kind='new_real_measurement',device=device,model='InsightFace buffalo_l; detection + recognition; det_size=640x640; threshold=0.5')
  save('measurements/'+target.name,dict(selection=r,row=row,provenance=provenance,timestamp=datetime.now(timezone.utc).isoformat()));print('MEASURE',i+1,'/',len(x['selected']),r['dataset'],r['role'],row['success'],flush=True)
 export()

def export():
 x=plan();measured=[]
 for r in x['selected']:
  p=OUT/'measurements'/(r['image_sha256']+'.json')
  if p.exists():measured.append(read(p))
 summary=Counter((v['selection']['dataset'],v['selection']['role'],str(v['row']['success'])) for v in measured)
 save('measurement-progress.json',dict(completed=len(measured),planned=len(x['selected']),counts=[dict(dataset=k[0],role=k[1],success=k[2],count=v) for k,v in summary.items()]))
 if len(measured)!=len(x['selected']):return
 profile_ids={}
 for dataset in ('lfw','wider_train'):
  for role in COUNTS:
   part=[v for v in measured if v['selection']['dataset']==dataset and v['selection']['role']==role]
   ident=hashlib.sha256(('formal-v1'+dataset+role+hashlib.sha256((OUT/'plan.json').read_bytes()).hexdigest()).encode()).hexdigest()[:32]
   path=profiles.path_for(ident,'.csv')
   if not path.exists():
    with path.open('w',newline='',encoding='utf-8') as f:
     w=csv.DictWriter(f,fieldnames=profiles.FIELDS);w.writeheader();w.writerows(v['row'] for v in part)
    n=sum(str(v['row']['success'])=='True' for v in part)
    profiles.save(dict(id=ident,dataset=dataset,count=len(part),completed=len(part),succeeded=n,failed=len(part)-n,status='completed' if n else 'failed',repeats=3,seed=SEED,created_at=datetime.now(timezone.utc).isoformat(),split_role=role,model='buffalo_l detection + recognition; inherited measurement provenance per row',device={'scope':'per-image provenance, same CPUExecutionProvider and software versions'},csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),selected_samples=[dict(sample_id=v['row']['sample_id'],source_path=v['row']['source_path']) for v in part]))
   profile_ids[dataset+'/'+role]=ident
 save('profile-ids.json',profile_ids);save('measurement-complete.json',dict(total=len(measured),successful=sum(str(v['row']['success'])=='True' for v in measured),profiles=profile_ids));print('DATA COMPLETE',profile_ids,flush=True)
if __name__=='__main__':
 if '--plan' in sys.argv:plan()
 elif '--export' in sys.argv:export()
 else:run()
