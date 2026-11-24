"""P0-01: export explicit contracts from sealed historical evidence, never infer missing masks."""
import argparse
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from app.offloading.agents49.input_contract import (
    InputSpec, InputContractError, file_sha256, write_model_contract, write_contract_index,
)
from app.offloading.agents49.normalizer import FEATURE_NAMES, SCALES, BINARY_INDICES, CONTRACT_VERSION


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def checked(path, expected):
    if file_sha256(path) != expected:
        raise InputContractError('Historical provenance mismatch: '+str(path))
    return Path(path)


def export(repo, baseline, out):
    repo,baseline,out=map(lambda p:Path(p).resolve(),(repo,baseline,out))
    if out.exists():raise InputContractError('Choose a new contract output directory')
    planned=[]
    long=repo/'profiles/rl-long-horizon-v1';design=read(long/'design.json')
    source_before=baseline/'source-before'
    sources=[]
    for historical,expected in design['source_sha256'].items():
        relative=historical.removeprefix('/app/')
        if relative.startswith('app/'):relative='backend/'+relative
        sources.append(checked(source_before/relative,expected))
    for metadata in sorted((long/'runs').glob('*/checkpoint.json')):
        doc=read(metadata);checkpoint=checked(metadata.with_suffix('.npz'),doc['sha256'])
        if 'feature_mask' not in doc:raise InputContractError('Missing original feature_mask')
        spec=InputSpec('pruned' if doc['feature_mask'] else 'full',tuple(doc['feature_mask']))
        planned.append(dict(name=metadata.parent.name,suite='long-horizon',algorithm=doc['algorithm'],
                            checkpoint=checkpoint,spec=spec,sources=[metadata,long/'design.json',*sources],
                            mask_evidence=dict(path=metadata.relative_to(repo).as_posix(),field='feature_mask'),
                            checkpoint_evidence=dict(path=metadata.relative_to(repo).as_posix(),field_path=['sha256'])))
    if len(planned)!=48 or sum(p['spec'].feature_mode=='pruned' for p in planned)!=24:
        raise InputContractError('Expected 24 Full and 24 Pruned historical checkpoints')

    # Full49 is established by sealed training sources, not by absence of a mask or 49D shape.
    old=repo/'profiles/agents49';study=read(old/'study.json')
    runner=checked(old/'evidence/agents49_experiment_as_executed.py',study['implementation_sha256']['scripts/agents49_experiment.py'])
    trainer=checked(source_before/'backend/app/offloading/agents49/training.py',study['implementation_sha256']['app/offloading/agents49/training.py'])
    member=repo/'work/agents49/incoming/SimPy49_DQN_DDQN_New'
    audit=read(old/'prototype-audit.json')
    for name,expected in audit['member_checksums'].items():checked(member/name,expected)
    checked(member/'app/offloading/rl/dqn.py',study['implementation_sha256']['app/offloading/agents49/dqn.py'])
    checked(member/'app/offloading/rl/normalizer.py',study['implementation_sha256']['app/offloading/agents49/normalizer.py'])
    if tuple(study['feature_names'])!=FEATURE_NAMES or study['normalizer']!=CONTRACT_VERSION or study['action_map']!=['local','edge','cloud']:
        raise InputContractError('Historical Full49 study contract differs')
    for algorithm in ('dqn','ddqn'):
        for seed in (42,43,44):
            metadata=old/'training'/algorithm/str(seed)/'checkpoint.json';doc=read(metadata)
            checkpoint=checked(old/doc['path'],doc['sha256'])
            planned.append(dict(name=f'legacy-{algorithm}-s{seed}',suite='legacy-full',algorithm=algorithm,
                                checkpoint=checkpoint,spec=InputSpec(),
                                sources=[metadata,old/'study.json',runner,trainer,member/'app/offloading/rl/dqn.py',member/'app/offloading/rl/normalizer.py'],
                                mask_evidence=dict(path=runner.relative_to(repo).as_posix(),review='verified-full49-training-source'),
                                checkpoint_evidence=dict(path=metadata.relative_to(repo).as_posix(),field_path=['sha256'])))
        metadata=member/'logs'/f'{algorithm}_metadata.json';doc=read(metadata)
        feature_doc=read(member/'examples/feature_names.json')
        if doc['algorithm']!=algorithm or tuple(doc['feature_names'])!=FEATURE_NAMES or doc['contract']!=CONTRACT_VERSION:
            raise InputContractError('Member Full49 contract differs')
        if ([f['name'] for f in feature_doc['features']]!=list(FEATURE_NAMES)
            or [f['scale'] for f in feature_doc['features']]!=SCALES.tolist()
            or tuple(i for i,f in enumerate(feature_doc['features']) if f['binary'])!=BINARY_INDICES
            or feature_doc['action_map']!={str(i):n for i,n in enumerate(('local','edge','cloud'))}):
            raise InputContractError('Member feature manifest differs')
        checkpoint=checked(member/'models'/f'{algorithm}_49d.npz',audit['member_checksums'][f'models/{algorithm}_49d.npz'])
        planned.append(dict(name=f'member-{algorithm}',suite='member-prototype',algorithm=algorithm,checkpoint=checkpoint,spec=InputSpec(),
                            sources=[metadata,old/'prototype-audit.json',member/'SHA256_MANIFEST.txt',member/'train.py',
                                     member/'app/offloading/rl/dqn.py',member/'app/offloading/rl/ddqn.py',
                                     member/'app/offloading/rl/normalizer.py',member/'app/offloading/rl/bridge.py',
                                     member/'examples/feature_names.json'],
                            mask_evidence=dict(path=(member/'train.py').relative_to(repo).as_posix(),review='verified-full49-training-source'),
                            checkpoint_evidence=dict(path=(old/'prototype-audit.json').relative_to(repo).as_posix(),
                                                     field_path=['member_checksums',f'models/{algorithm}_49d.npz'])))
    # Validate all provenance before exporting anything. No uncertain model gets a guessed contract.
    out.mkdir(parents=True)
    refs=[];inventory=[]
    for p in planned:
        ref=write_model_contract(p['checkpoint'],p['algorithm'],p['spec'],out/'contracts',repo,p['sources'],p['mask_evidence'],p['checkpoint_evidence'])
        refs.append(ref)
        inventory.append(dict(name=p['name'],suite=p['suite'],algorithm=p['algorithm'],feature_mode=p['spec'].feature_mode,
                              mask=list(p['spec'].zeroed_feature_indices),checkpoint=p['checkpoint'].relative_to(repo).as_posix(),
                              checkpoint_sha256=file_sha256(p['checkpoint']),contract_path=ref.path.relative_to(out).as_posix(),
                              contract_sha256=ref.sha256))
    write_contract_index(out/'index.json',refs)
    (out/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='PASS',models=len(inventory),long_horizon=48,legacy_full=6,member_full=2,
                          index_sha256=file_sha256(out/'index.json'))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('repo','baseline','out'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();export(a.repo,a.baseline,a.out)
