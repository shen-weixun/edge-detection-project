"""Observe unchanged production function return frames. Never redraw RNG/update weights."""
import inspect,sys
import numpy as np
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN

def observed_call(fn,code,*args):
    if sys.getprofile() is not None:raise RuntimeError('Diagnostic observer requires an otherwise unprofiled thread')
    captured={}
    def observe(frame,event,arg):
        if frame.f_code is code and event=='return':
            captured.update(frame.f_locals)
            captured['_return_line']=frame.f_lineno
    sys.setprofile(observe)
    try:result=fn(*args)
    finally:sys.setprofile(None)
    return result,captured

source,start=inspect.getsourcelines(DQN.act)
random_lines=[start+i for i,line in enumerate(source) if 'return int(self.rng.choice(choices))' in line]
assert len(random_lines)==1,'Production source changed: review observer before running'
RANDOM_RETURN=random_lines[0]

class DiagnosticMixin:
    diagnostics_enabled=True
    last_action_diagnostics=None
    last_update_diagnostics=None

    def act(self,raw_state,epsilon=0):
        if not self.diagnostics_enabled:return super().act(raw_state,epsilon)
        result,frame=observed_call(super().act,DQN.act.__code__,raw_state,epsilon)
        # Additional pure forward is logging-only, outside deployed Adapter timing.
        _,q,greedy=self.predict_greedy(raw_state)
        self.last_action_diagnostics=dict(epsilon=float(epsilon),random_branch=frame['_return_line']==RANDOM_RETURN,
            action=int(result),greedy_action=int(greedy),q_values=q.tolist(),q_min=float(q.min()),q_max=float(q.max()),q_mean=float(q.mean()))
        return result

    def train_step(self):
        if not self.diagnostics_enabled:return super().train_step()
        result,f=observed_call(super().train_step,DQN.train_step.__code__)
        if result is None:
            self.last_update_diagnostics=None
            return result
        # q, target and grads are the ORIGINAL pre-update intermediate arrays.
        # Original clipping rebinds `grad`; it does not alter entries in `grads`.
        raw=f['q'][np.arange(len(f['a'])),f['a']]-f['target']
        norms=np.array([np.linalg.norm(g) for g in f['grads']])
        synced=self.updates%self.target_interval==0
        if synced:assert all(np.array_equal(a,b) for a,b in zip(self.online,self.target))
        values=np.r_[raw,norms,f['q'].ravel(),f['target'],result]
        assert np.isfinite(values).all(),'Non-finite numeric training diagnostic'
        self.last_update_diagnostics=dict(raw_td_error=raw.tolist(),td_clip_count=int((np.abs(raw)>100).sum()),
            td_clip_ratio=float((np.abs(raw)>100).mean()),td_abs_max=float(np.abs(raw).max()),
            q_min=float(f['q'].min()),q_max=float(f['q'].max()),q_mean=float(f['q'].mean()),
            gradient_norms=norms.tolist(),gradient_clip_count=int((norms>5).sum()),
            replay_size=len(self.memory),gradient_update_count=self.updates,
            target_update_count=self.updates//self.target_interval,target_synchronized=synced,
            loss=float(result),replay_indices=f['indexes'].tolist(),bellman_targets=f['target'].tolist())
        return result

class DiagnosticDQN(DiagnosticMixin,DQN):pass
class DiagnosticDDQN(DiagnosticMixin,DDQN):pass
AGENTS={'dqn':DiagnosticDQN,'ddqn':DiagnosticDDQN}
