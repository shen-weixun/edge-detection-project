"""Frozen, stratified train/validation/test evaluation on two measured Profiles.
Selection uses validation MAE only; test outcomes are never selection inputs.
"""
import argparse,sys,os,csv,json,hashlib,random,math
from dataclasses import replace
from pathlib import Path
from statistics import mean
from datetime import datetime,timezone
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.offloading.estimators import WorkloadEstimator,assert_disjoint,register,identities
from app.offloading import profiles


def evaluate(model,rows):
    p=np.asarray([model.predict(r) for r in rows]);y=np.asarray([r['workload_ms'] for r in rows]);e=p-y
    return dict(n=len(y),mae_ms=float(np.abs(e).mean()),rmse_ms=float(np.sqrt((e*e).mean())),bias_ms=float(e.mean()),
                signed_error_p05_ms=float(np.quantile(e,.05)),signed_error_p50_ms=float(np.quantile(e,.5)),signed_error_p95_ms=float(np.quantile(e,.95)),abs_error_p95_ms=float(np.quantile(abs(e),.95)))

def run(lfw,wider,out):
    out.mkdir(parents=True,exist_ok=True);data={};meta={};manifest=[];duplicates=[];seen={}
    for label,identifier in [('lfw',lfw),('wider',wider)]:
        m,rows=profiles.load(identifier);meta[label]=m
        unique=[]
        for row in rows:
            digest=hashlib.sha256((Path(os.getenv('DATASET_ROOT','/datasets'))/row['source_path']).read_bytes()).hexdigest()
            if digest in seen:duplicates.append(dict(source_path=row['source_path'],same_as=seen[digest]));continue
            seen[digest]=row['source_path'];unique.append(dict(row,image_sha256=digest))
        random.Random(314159).shuffle(unique)
        n=len(unique);a=int(.6*n);b=int(.8*n)
        data[label]=dict(training=unique[:a],validation=unique[a:b],testing=unique[b:])
        for role,rs in data[label].items():
            manifest += [dict(dataset=label,role=role,source_path=r['source_path'],image_sha256=r['image_sha256']) for r in rs]
    train=sum((d['training'] for d in data.values()),[]);val=sum((d['validation'] for d in data.values()),[]);test=sum((d['testing'] for d in data.values()),[])
    assert_disjoint(train,val,test)
    hashes=[{r['image_sha256'] for r in part} for part in (train,val,test)]
    assert not(hashes[0]&hashes[1] or hashes[0]&hashes[2] or hashes[1]&hashes[2])
    (out/'split-manifest.json').write_text(json.dumps(dict(seed=314159,measurement_seed=271828,partitions=manifest,duplicates_excluded=duplicates,profiles={k:v['id'] for k,v in meta.items()}),ensure_ascii=False,indent=2),encoding='utf-8')
    candidates={}
    for kind,alphas in [('median',[1.]),('ridge_raw',[.1,1.,10.]),('ridge_log',[.1,1.,10.])]:
        for alpha in alphas:
            key=kind if kind=='median' else kind+'-'+str(alpha)
            model=WorkloadEstimator.fit(train,kind,alpha)
            model=replace(model,validation_identities=tuple(identities(val)))
            model.validate_test(test);candidates[key]=model
    validation={k:evaluate(m,val) for k,m in candidates.items()}
    best_feature=min((k for k in candidates if k!='median'),key=lambda k:(validation[k]['mae_ms'],k))
    selected=min(candidates,key=lambda k:(validation[k]['mae_ms'],k))
    # Persist selection before computing any final test metrics.
    (out/'validation-selection.json').write_text(json.dumps(dict(objective='validation_MAE_ms',candidates=validation,selected=selected,best_feature=best_feature,test_used_for_selection=False),indent=2),encoding='utf-8')
    model_ids={k:register(candidates[k]) for k in {'median',best_feature,selected}}
    for k,m in candidates.items():m.save(out/'models'/(k+'.json'))
    results=[];predictions=[]
    for label,part in data.items():
        testing=part['testing']
        for key,model in candidates.items():
            results.append(dict(dataset=label,method=key,**evaluate(model,testing)))
            for row in testing:predictions.append(dict(dataset=label,method=key,source_path=row['source_path'],actual_ms=row['workload_ms'],predicted_ms=model.predict(row),error_ms=model.predict(row)-row['workload_ms']))
    intervals=[];rng=np.random.default_rng(424242)
    for label,part in data.items():
        ts=part['testing'];difference=np.asarray([abs(candidates[best_feature].predict(r)-r['workload_ms'])-abs(candidates['median'].predict(r)-r['workload_ms']) for r in ts])
        boot=np.asarray([difference[rng.integers(0,len(ts),len(ts))].mean() for _ in range(2000)])
        intervals.append(dict(dataset=label,quantity='feature_MAE_minus_median_MAE_ms',mean_difference_ms=float(difference.mean()),ci95_low_ms=float(np.quantile(boot,.025)),ci95_high_ms=float(np.quantile(boot,.975)),n=len(ts),bootstrap_seed=424242))
    cross=[]
    for source,target in [('lfw','wider'),('wider','lfw')]:
        alternatives={}
        for kind,alphas in [('median',[1.]),('ridge_raw',[.1,1.,10.]),('ridge_log',[.1,1.,10.])]:
            for alpha in alphas:
                k=kind+'-'+str(alpha);alternatives[k]=WorkloadEstimator.fit(data[source]['training'],kind,alpha)
        k=min(alternatives,key=lambda x:(evaluate(alternatives[x],data[source]['validation'])['mae_ms'],x))
        cross.append(dict(train_dataset=source,test_dataset=target,selected_using_source_validation=k,**evaluate(alternatives[k],data[target]['testing'])))
    # Derived test-only Profiles make saved-model API experiments safe by construction.
    test_ids={}
    for label,part in data.items():
        parent=meta[label];paths={r['source_path'] for r in part['testing']}
        ident=hashlib.sha256((parent['id']+'paper-test-v1'+'|'.join(sorted(paths))).encode()).hexdigest()[:32]
        raw=list(csv.DictReader(profiles.path_for(parent['id'],'.csv').open(encoding='utf-8-sig')))
        selected_rows=[r for r in raw if r['source_path'] in paths]
        with profiles.path_for(ident,'.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=profiles.FIELDS);writer.writeheader();writer.writerows(selected_rows)
        n=len(selected_rows);child=dict(parent,id=ident,count=n,completed=n,succeeded=n,failed=0,status='completed',derived_from=parent['id'],split_role='held_out_test',created_at=datetime.now(timezone.utc).isoformat(),selected_samples=[dict(sample_id=r['sample_id'],source_path=r['source_path']) for r in selected_rows],csv_sha256=hashlib.sha256(profiles.path_for(ident,'.csv').read_bytes()).hexdigest())
        profiles.save(child);test_ids[label]=ident
    for name,rows in [('estimator-test-metrics',results),('estimator-predictions',predictions),('estimator-confidence',intervals),('estimator-cross-domain',cross)]:
        with (out/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    output=dict(selected=selected,best_feature=best_feature,model_ids=model_ids,test_profile_ids=test_ids,
                validation=validation,split_counts={k:{r:len(v) for r,v in p.items()} for k,p in data.items()},test_metrics=results,confidence=intervals,cross_domain=cross)
    (out/'estimator-evaluation.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(selected=selected,best_feature=best_feature,model_ids=model_ids,test_profiles=test_ids,counts=output['split_counts'],confidence=intervals)),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--lfw',required=True);a.add_argument('--wider',required=True);a.add_argument('--output',type=Path,default=Path('/tmp/paper-improvements'));args=a.parse_args();run(args.lfw,args.wider,args.output)
