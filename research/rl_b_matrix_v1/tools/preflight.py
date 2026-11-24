"""Run original regression suite and new gates; any failure blocks Smoke."""
import json,unittest
from pathlib import Path
from common import ROOT,write
from design import build

class Recorder(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.records=[]
    def addSuccess(self,t):super().addSuccess(t);self.records.append(dict(test=t.id(),verdict='PASS'))
    def addFailure(self,t,e):super().addFailure(t,e);self.records.append(dict(test=t.id(),verdict='FAIL',detail=self._exc_info_to_string(e,t)))
    def addError(self,t,e):super().addError(t,e);self.records.append(dict(test=t.id(),verdict='ERROR',detail=self._exc_info_to_string(e,t)))
    def addSkip(self,t,reason):super().addSkip(t,reason);self.records.append(dict(test=t.id(),verdict='SKIP',detail=reason))

if __name__=='__main__':
    build(ROOT/'results/design')
    loader=unittest.TestLoader()
    suite=loader.discover(str(ROOT/'runtime/backend/tests'))
    from tests_preflight import Preflight
    suite.addTests(loader.loadTestsFromTestCase(Preflight))
    with (ROOT/'results/preflight.log').open('x',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Recorder).run(suite)
    write(ROOT/'results/preflight-tests.json',dict(passed=result.wasSuccessful(),tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),tests=result.records))
    print(dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors)),flush=True)
    if not result.wasSuccessful():raise SystemExit(2)
    write(ROOT/'results/PREFLIGHT_PASS.json',dict(passed=True,tests_run=result.testsRun))
