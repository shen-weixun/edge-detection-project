"""Small persisted estimators using pre-inference image metadata only.

Training and model selection are offline. Test labels never enter predict().
Median remains the default in experiment.py for backwards compatibility.
"""
from dataclasses import dataclass,asdict,replace
from pathlib import Path
from statistics import median
from math import isfinite,log1p,log
import hashlib,json,re,os
import numpy as np
from .workload import source_identity

FEATURES=('image_size_mb','megapixels','log_aspect_ratio')

def features(row):
    def value(key):return row[key] if isinstance(row,dict) else getattr(row,key)
    size=float(value('image_size_mb'));width=float(value('width'));height=float(value('height'))
    if not all(isfinite(x) for x in (size,width,height)) or size<=0 or width<=0 or height<=0:
        raise ValueError('Estimator requires positive finite size, width and height')
    return [size,width*height/1_000_000,log(width/height)]

def identities(rows):return sorted({source_identity(r['source_path']) for r in rows})

def assert_disjoint(*partitions):
    seen=set()
    for rows in partitions:
        if not rows or any(not r.get('source_path') for r in rows):raise ValueError('Nonempty source identities required')
        ids=set(identities(rows))
        if seen & ids:raise ValueError('Estimator train/validation/test image overlap')
        seen |= ids

@dataclass(frozen=True)
class WorkloadEstimator:
    kind: str
    value_ms: float
    coefficients: tuple=()
    center: tuple=()
    scale: tuple=()
    training_identities: tuple=()
    validation_identities: tuple=()
    ridge_alpha: float=1.0
    schema: str='workload-estimator-v1'

    @classmethod
    def fit(cls,rows,kind='median',alpha=1.0):
        if not rows or kind not in ('median','ridge_raw','ridge_log') or not isfinite(alpha) or alpha<=0:
            raise ValueError('Invalid estimator configuration')
        y=np.asarray([r['workload_ms'] for r in rows],dtype=float)
        if not np.all(np.isfinite(y)) or np.any(y<=0):raise ValueError('Invalid training labels')
        ids=tuple(identities(rows))
        if any(not r.get('source_path') for r in rows):raise ValueError('Training source identities required')
        if kind=='median':return cls(kind,float(median(y)),training_identities=ids)
        x=np.asarray([features(r) for r in rows]);center=x.mean(0);scale=x.std(0);scale=np.where(scale>1e-12,scale,1.)
        z=np.column_stack([np.ones(len(x)),(x-center)/scale])
        target=np.log(y) if kind=='ridge_log' else y
        penalty=np.diag([0.,alpha,alpha,alpha])
        coeff=np.linalg.solve(z.T@z+penalty,z.T@target)
        return cls(kind,float(median(y)),tuple(coeff),tuple(center),tuple(scale),ids,ridge_alpha=alpha)

    def predict(self,row):
        if self.kind=='median':return self.value_ms
        x=np.asarray(features(row));z=(x-np.asarray(self.center))/np.asarray(self.scale)
        predicted=float(self.coefficients[0]+np.dot(self.coefficients[1:],z))
        # Positive, finite outputs; no test-label-dependent clipping range.
        if self.kind=='ridge_log':predicted=float(np.exp(np.clip(predicted,-13.8,20.7)))
        return max(1e-3,predicted)

    def validate_test(self,rows):
        used=set(self.training_identities)|set(self.validation_identities)
        if used.intersection(identities(rows)):raise ValueError('Estimator train/validation/test image overlap')

    def to_dict(self):return asdict(self)

    @classmethod
    def from_dict(cls,data):
        if data.get('schema')!='workload-estimator-v1' or data.get('kind') not in ('median','ridge_raw','ridge_log'):
            raise ValueError('Invalid estimator schema/kind')
        for key in ('coefficients','center','scale','training_identities','validation_identities'):
            data={**data,key:tuple(data.get(key,()))}
        obj=cls(**data)
        if not isfinite(obj.value_ms) or obj.value_ms<=0:raise ValueError('Invalid estimator prior')
        if obj.kind!='median':
            if len(obj.coefficients)!=4 or len(obj.center)!=3 or len(obj.scale)!=3:raise ValueError('Invalid estimator dimensions')
            if not all(isfinite(v) for v in obj.coefficients+obj.center+obj.scale) or any(v<=0 for v in obj.scale):raise ValueError('Invalid estimator numbers')
        return obj

    def save(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(self.to_dict(),sort_keys=True,allow_nan=False),encoding='utf-8')

    @classmethod
    def load(cls,path):return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))


def model_root():return Path(os.getenv('PROFILE_ROOT','/profiles'))/'estimators'

def register(model):
    payload=json.dumps(model.to_dict(),sort_keys=True,allow_nan=False).encode()
    ident=hashlib.sha256(payload).hexdigest()
    model.save(model_root()/(ident+'.json'))
    return ident

def load_registered(identifier):
    if not re.fullmatch('[0-9a-f]{64}',identifier):raise ValueError('Invalid estimator ID')
    path=model_root()/(identifier+'.json')
    data=json.loads(path.read_text(encoding='utf-8'))
    if hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False).encode()).hexdigest()!=identifier:raise ValueError('Estimator checksum mismatch')
    return WorkloadEstimator.from_dict(data)


class EstimatedPolicy:
    """Charge metadata prediction inside the existing policy wall-time boundary.

    Workload precomputation supplies the simulator's estimated commitment ledger;
    this call represents the actual device decision pipeline, never actual service.
    """
    def __init__(self,policy,model):
        self.policy,self.model=policy,model

    def select_node(self,task,state):
        observed=replace(task,estimated_workload_ms=self.model.predict(task))
        return self.policy.select_node(observed,state)

    def __getattr__(self,name):return getattr(self.policy,name)
