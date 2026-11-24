"""Publish only scenario-local summaries/charts, preserving frozen result bytes."""
from pathlib import Path
import json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'profiles/ai-comparison';OUT=ROOT/'frontend/public/ai-comparison';OUT.mkdir(parents=True,exist_ok=True)
assert (DATA/'validation-summary.json').exists()
def copy(source,target):
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists() and target.suffix!='.md':assert source.read_bytes()==target.read_bytes(),'Frozen published data changed: '+str(target)
 shutil.copy2(source,target)
for root,prefix in [(DATA/'web',Path('.')),(DATA/'charts',Path('charts'))]:
 for p in root.rglob('*'):
  if p.is_file():copy(p,OUT/prefix/p.relative_to(root))
for name in ('AI_COMPARISON_REPORT.md','TEAM_BLOCKERS.md','model_validation.md'):copy(DATA/name,OUT/name)
manifest=dict(source_run_config_sha256=hashlib.sha256((DATA/'run-config.json').read_bytes()).hexdigest(),scenario_count=24,common_subset_size=10,replay=False,blocked=['dqn','ddqn'],files={str(p.relative_to(OUT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='publication.json'})
(OUT/'publication.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print('PUBLISHED',len(manifest['files']),'scenario-local files')
