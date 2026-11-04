import requests,json
nodes=[]
for n,s,r,b in [('local',1,0,1000),('edge',3,20,120),('cloud',8,100,55)]:
 nodes.append(dict(name=n,compute_speed=s,queue_length=0,queue_work_ms=0,rtt_ms=r,bandwidth_mbps=b,upload_backlog_ms=0,download_backlog_ms=0,available=True))
task=dict(image_size_mb=.01,face_count=1,workload_ms=500,deadline_ms=1000,result_size_kb=16)
results=[]
for preferred in ['local','edge','cloud']:
 for reverse in [False,True]:
  scenario=json.loads(json.dumps(nodes))
  for n in scenario:
   if n['name']==preferred:
    n.update(queue_length=0,queue_work_ms=0,compute_speed=1 if preferred=='local' else 10,rtt_ms=0 if preferred=='local' else 1,bandwidth_mbps=1000)
   else:
    n.update(queue_length=100,queue_work_ms=100000,compute_speed=1 if n['name']=='local' else .1,rtt_ms=0 if n['name']=='local' else 5000,bandwidth_mbps=1)
  if reverse:scenario.reverse()
  response=requests.post('http://laya:8001/decide',json=dict(task=task,nodes=scenario,context=dict(kind='synthetic_diagnostic_not_measured',expected_fastest=preferred,reversed_node_order=reverse)),timeout=180);response.raise_for_status()
  result=dict(expected_fastest=preferred,reversed_order=reverse,response=response.json());results.append(result)
print(json.dumps(results,ensure_ascii=False))
