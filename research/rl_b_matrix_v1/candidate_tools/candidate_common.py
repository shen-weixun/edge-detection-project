import gzip,hashlib,json,os,struct,time
from pathlib import Path
import numpy as np
from common import ROOT,canonical,digest,file_sha,write,rng_state
OUT=ROOT/'candidate-results'
CHECKPOINTS=(0,2400,4800,7200,9600)
LIMIT=57600
def gzwrite(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(gzip.compress(canonical(x),compresslevel=3,mtime=0))
def readgz(p):return json.loads(gzip.decompress(Path(p).read_bytes()))
def weights_sha(weights):return hashlib.sha256(b''.join(w.tobytes() for w in weights)).hexdigest()
def fingerprint(agent):
    h=hashlib.sha256()
    for s,a,r,ns,d,m in agent.memory:
        h.update(s.tobytes());h.update(ns.tobytes());h.update(m.tobytes());h.update(struct.pack('<id?',a,r,d))
    return dict(online=weights_sha(agent.online),target=weights_sha(agent.target),rng=rng_state(agent),
                updates=agent.updates,replay_length=len(agent.memory),replay_sha256=h.hexdigest())
def resources():
    stat=os.statvfs(ROOT);memory={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith(('MemAvailable:','MemTotal:')):
            key,value=line.split(':',1);memory[key]=int(value.split()[0])*1024
    return dict(tmp_free_bytes=stat.f_bavail*stat.f_frsize,**memory)
def resource_guard():
    value=resources()
    if value['tmp_free_bytes']<256*1024**2 or value['MemAvailable']<384*1024**2:
        raise RuntimeError('Resource guard: remaining disk/memory below declared floor')
    return value
def all_finite(*arrays):
    assert all(np.isfinite(np.asarray(a,dtype=float)).all() for a in arrays),'NaN/Inf detected'
def forward(x,w):
    w1,b1,w2,b2,w3,b3=w
    return np.maximum(np.maximum(x@w1+b1,0)@w2+b2,0)@w3+b3
def audit_bootstrap(agent,diag,old_online,old_target):
    rows=[agent.memory[int(i)] for i in diag['replay_indices']]
    ns=np.stack([r[3] for r in rows]);masks=np.stack([r[5] for r in rows])
    online=forward(ns,old_online);target=forward(ns,old_target)
    dqn=np.max(np.where(masks>0,target,-1e30),axis=1)
    choices=np.argmax(np.where(masks>0,online,-1e30),axis=1)
    ddqn=target[np.arange(len(choices)),choices]
    reward=np.array([r[2] for r in rows]);done=np.array([r[4] for r in rows],dtype=float)
    expected=reward+(1-done)*(dqn if agent.algorithm=='dqn' else ddqn)
    observed=np.array(diag['bellman_targets'])
    assert agent.gamma==1 and np.allclose(expected,observed,rtol=1e-12,atol=1e-12),'Bootstrap formula mismatch'
    current=forward(np.stack([r[0] for r in rows]),old_online)
    raw=current[np.arange(len(rows)),[r[1] for r in rows]]-expected
    assert np.allclose(raw,diag['raw_td_error'],rtol=1e-12,atol=1e-12)
    all_finite(online,target,expected,raw)
    return dict(bootstrap_disagreement_count=int((np.abs(dqn-ddqn)>1e-12).sum()),
                bootstrap_difference_max=float(np.abs(dqn-ddqn).max()),
                independent_target_error=float(np.abs(expected-observed).max()))
