import json
from common import ROOT
from smoke import run
if __name__=='__main__':
    gate=json.loads((ROOT/'results/PREFLIGHT_PASS.json').read_text())
    assert gate['passed']
    t=json.loads((ROOT/'results/design/training-manifest.json').read_text())
    v=json.loads((ROOT/'results/design/validation-manifest.json').read_text())
    run(dict(training=t['training'],validation=v['cases']),ROOT/'results/smoke')
