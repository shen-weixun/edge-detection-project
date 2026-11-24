"""Traditional Chinese review from completed evidence, with no model execution."""
from collections import defaultdict,deque,Counter
from pathlib import Path
import csv,json
BASE=Path(__file__).resolve().parent;R=BASE/'reports/analysis'
def csvrows(name):return list(csv.DictReader((R/name).open(encoding='utf-8-sig')))
diag=json.loads((R/'diagnostic-summary.json').read_text())['models']
full=csvrows('full-validation.csv');checkpoints=csvrows('checkpoint-sha256.csv')
control=json.loads((BASE/'control-validation/summary.json').read_text())
assert control['gradient_updates']==0
keys=[m['policy_key'] for m in diag]
groups=defaultdict(lambda:dict(first=[],last=deque(maxlen=200)))
for row in csv.DictReader((R/'update-diagnostics.csv').open(encoding='utf-8-sig')):
    g=groups[row['policy_key']]
    if len(g['first'])<200:g['first'].append(row)
    g['last'].append(row)
def avg(rows,key):return sum(float(x[key]) for x in rows)/len(rows)
lines=['# B矩陣正式候選：研究驗收審查','',
 '日期：2026-11-24（Asia/Taipei）。工程驗證通過；六模型完成固定訓練及完整Validation，但佇列自適應與泛化尚未通過研究效果驗收。','',
 '沒有正式Test、A矩陣訓練、14400次延長、Ridge、API/前端整合或改寫歷史成果。以下結果沒有用於中途調參或挑選Seed。','',
 '## A．六模型、更新及SHA','',
 '每模型9600派送、9537次gradient update、47次定期Target同步；合計57600派送、57222次update、282次同步。初始化拷貝與Validation載入不算定期Target更新。','',
 '| 模型 | 最終9600 policy.npz SHA-256 |','|---|---|']
for key in keys:
    alg,seed=key.split('-s');row=next(r for r in checkpoints if r['algorithm']==alg and r['seed']==seed and r['step']=='9600')
    lines.append(f'| {key} | `{row["sha256"]}` |')
lines+=['','30個Checkpoint完整清單：candidate-results/reports/checkpoint-sha256.csv。每個均有來源契約、Online/Target、Replay、RNG及更新計數。未選擇中途最佳Checkpoint，完整Validation一律使用9600。','',
 '## B、C．每Seed學習曲線與五個Greedy檢查點','',
 '固定24-case監測子集；EPS=0、不計決策成本。下列macro Reward只是時間趨勢診斷，不是跨情境策略排名。','',
 '| 模型 | 0 | 2400 | 4800 | 7200 | 9600 |','|---|---:|---:|---:|---:|---:|']
for m in diag:lines.append('| '+m['policy_key']+' | '+' | '.join(f'{v:.4f}' for v in m['monitor_rewards'])+' |')
lines+=['','所有Seed最終監測Reward高於初始，但Seed44初始已接近Cloud-only，最終改善很小。DQN42從7200到9600略退步；Seed43兩演算法在7200/9600的平台伴隨固定Cloud，不能據此宣稱收斂到良好自適應策略。',
 'Training Reward另受epsilon=.8→.1影響，須與固定Greedy監測分開解讀。完整逐Episode及逐update曲線保留。','',
 '## D、E、F．完整共同Validation與公平比較','',
 '- 120 cells × Validation seed701/709 =240 cases。每case100任務；六候選及六Baseline，分含/不含成本，共576000評估派送。',
 '- 中途監測額外72000派送；48-cell事件預檢4800派送、零梯度。後續控制驗證252個合成任務、零梯度。',
 '- 只有Training/Validation CSV進入實驗；80張Training與40張Validation獨立影像，重複派送/多Seed不是更多獨立樣本。',
 '- 同Seed DQN/DDQN外生manifest與RNG/圖片抽樣固定；容許策略造成內部佇列差異。未修改Baseline及Latency-aware。',
 '- 原始Mean、P95、Deadline、Completion、Reward、Action Ratio、決策/決策排隊/網路/CPU排隊/Compute逐case存於full-validation.csv。',
 '- 每候選對六Baseline的逐case差距存於baseline-differences.csv；不產生單一總排名。','',
 '### 可核查的分層例子（均Validation seed701、不計決策成本）','',
 '| 資料／情境 | 模型 | Mean ms | P95 ms | Deadline |','|---|---|---:|---:|---:|']
examples=[('lfw','Low','local_advantage','steady'),('wider_train','High','network_4','burst'),('lfw','High','local_entry','burst')]
for ds,load,network,pattern in examples:
    for key in keys+['local_only','cloud_only','latency_aware_v2']:
        x=next(r for r in full if r['policy_key']==key and (r['dataset'],r['load'],r['network'],r['pattern'],r['validation_seed'],r['overhead'])==(ds,load,network,pattern,'701','False'))
        lines.append(f'| {ds}/{load}/{network}/{pattern} | {key} | {float(x["mean_ms"]):.3f} | {float(x["p95_ms"]):.3f} | {100*float(x["deadline_rate"]):.1f}% |')
lines+=['','WIDER部分中低負載情境優於V2，但常伴隨固定Cloud；這可解釋為學到資料集服務成本偏好，尚不能證明學會動態佇列最佳化。高負載Burst及極端Local優勢則保留明顯失敗。','',
 'Mean改善不保證P95改善。例：WIDER/Medium/network_4/steady、seed701，DDQN42 Mean503.963 vs V2 653.066 ms，但P95 730.417 vs604.296 ms。',
 '原嚴格正差CSV含一筆約7e-12 ms的P95浮點差；以原事件容差1e-6 ms排除純數值差後，對V2/不計成本共有24筆model×case的實質Mean/P95取捨。原CSV未改寫。','',
 '## G．控制與自然流的佇列適應證據','',
 '自然流每Episode及每個greedy Validation decision均保存估計成本差距、CPU/link成本分項反轉、Action及Q。反轉是可觀測成本分項診斷，可重疊；不是真實最優或因果標籤。',
 'DDQN42在CPU空閒選Edge、壅塞後轉Cloud，顯示局部CPU反應；其他五模型在該空閒例也選Cloud。六模型在link_busy及remote_busy皆仍選Cloud。這些輸入來自原生SimPy背景事件，不是手填未來工作量。新控制驗證實際執行模型probe，並用三種probe派送的完成結果事後核算整個Episode成本：','',
 '| 控制案例 | 模型probe位置 | probe延遲ms | 事後較低成本probe | 整個Episode成本差 |','|---|---|---:|---|---:|']
for name in ['cpu_idle','cpu_busy','link_idle','link_busy','remote_idle','remote_busy']:
    xs=[r for r in control['control_rows'] if r['case']==name]
    assert len(xs)==6
    grouped=Counter((x['selected_node'],x['probe_latency_ms'],x['best_probe_action_hindsight'],x['episode_cost_regret']) for x in xs)
    for (node,latency,best,regret),count in grouped.items():
        lines.append(f'| {name}（{count}/6模型） | {node} | {latency:.3f} | {best} | {regret:.6f} |')
lines+=['','成本單位為秒延遲加一次性miss懲罰。link_busy的2.882差距包含約1.882秒延遲與一次miss；remote_busy多0.216811。這證明該已完成控制流存在可避免成本，不只是模型與V2意見不同。',
 '控制限制：link_busy背景圖1MB超過本批Training典型大小；控制Episode為1/2/4/19任務且probe為最後工作，與100-task Training的horizon不同。Full49沒有剩餘Episode長度，因此不能只憑控制反例認定Bellman公式錯誤或要求所有狀態都選即時最短節點。',
 '在自然100-task、Training分布內的WIDER/High/network_4/burst亦有明顯落後V2的結果，故局限並非只有控制案例外推。','',
 '## H．實際決策成本','',
 '六候選全Validation的平均決策wall time約0.228～0.232 ms（含原Adapter特徵、Normalizer、forward與Median預測），平均決策排隊皆0。逐case原值及成本差距完整保存。',
 '含成本為閉環實驗：額外延遲會改變後續可觀測狀態及Action，總延遲差不一定只等於直接決策時間。',
 '已追查最明顯反向例：DQN42、WIDER/Medium/local_advantage/burst、seed709，含成本Mean23738.235 vs不含24236.609 ms，下降498.375 ms。直接決策時間仍為正0.2085 ms；Task67首次改選，edge.cpu_running由0變1、returning_count由1變0，後續九個Action不同。這是事件時序/派送回饋，沒有負的決策成本或修改統計。','',
 '## I、J．失敗Seed、數值與Bootstrap','',
 '| 模型 | ≥99%單節點cases/240 | Local-entry全Cloud/24 | TD裁切 | 梯度張量裁切 | DQN/DDQN Bootstrap值不同 |','|---|---:|---:|---:|---:|---:|']
for m in diag:
    lines.append(f'| {m["policy_key"]} | {m["near_fixed_cases"]} | {m["local_entry_all_cloud"]} | {100*m["td_clip_ratio"]:.4f}% | {100*m["gradient_clip_ratio"]:.2f}% | {100*m["bootstrap_disagreement_ratio"]:.2f}% |')
lines+=['','所有獨立Bootstrap target最大誤差0；DQN/DDQN確實有非零Bootstrap差異。沒有NaN/Inf、非法Action、守恆錯誤或RNG污染。',
 'Seed43接近固定Cloud平台；DDQN42較多混合Action，但在若干case仍有較差成本，不能把較多節點切換等同較好。',
 'TD裁切很少；梯度裁切約22～31%不罕見。多個模型的後段Loss/梯度裁切升高，不能宣稱穩定收斂；也不能僅據此判定數值發散。','',
 '| 模型 | 前200updates平均Loss | 最後200平均Loss | 最後200梯度裁切比例 |','|---|---:|---:|---:|']
for key in keys:
    g=groups[key];lines.append(f'| {key} | {avg(g["first"],"loss"):.4f} | {avg(g["last"],"loss"):.4f} | {100*avg(g["last"],"grad_clip_ratio"):.2f}% |')
lines+=['','## K．版本與重現','',
 '完整來源、profile SHA、30個模型契約及Checkpoint、逐步Replay/TD/梯度、候選輸入封存與實際命令均保存。所有原檔核對結果見FINAL_VERIFICATION.json、original-protection.json；完整重現入口及單次預算保護見REPRODUCE.md。',
 '工程門檻：56份歷史契約＋336拒絕案例、130回歸、48-cell無梯度事件預檢、五個Checkpoint的Validation fingerprint及所有新模型SHA核對。',
 '時間：候選訓練＋中途Validation約250.49秒，完整Validation約283.24秒；整個隔離流程含預檢、分析及輸出約603.49秒。分析process峰值RSS約229MiB，並非已量到訓練process的峰值。資源門檻檢查均未觸發。','',
 '## L．研究判斷','',
 '已證實：可重現訓練、正確Bootstrap與Reward/時間定義、學到偏向Cloud的低成本策略、部分Validation改善，以及固定選點和部分泛化失敗。',
 '未證實：收斂、跨Seed一致的自適應最優、普遍優於Latency-aware、Mean與尾延遲同步改善、真實部署效能或任何正式Test泛化。',
 '仍為假說：Median對WIDER低估、單一Cloud在多數場景已很強、全域Reward的高變異/延遲傳播、有限horizon的狀態混疊、訓練分布與極端Validation差距，各自對固定Cloud的因果貢獻。不能以本輪資料指定唯一根因。','',
 '## M．下一輪建議（本輪沒有執行）','',
 '1. 優先做相同9600預算的A矩陣對照，檢查保留極端覆蓋能否改善Local Sanity，以及是否犧牲B邊界表現；共用本輪固定Validation，不更改Baseline。',
 '2. 估計器實驗值得安排：Median在WIDER偏差已知，RL部分勝出可能反映隱式工作量學習。Ridge須另訓六模型、全策略用同一估計器、相同真實工作量與arrival，不能重用現有權重冒稱驗收。',
 '3. 不優先盲目延長14400。監測有平台/退步、後段Loss及梯度裁切升高，增加4800次並不保證打破固定Cloud。若另獲授權延長，保持9600前綴及第三輪epsilon=.1，另報固定策略/長尾與所有Seed。',
 '4. 現在不建議把這批候選宣稱已通過自適應研究驗收或直接進入正式Test。先審查上述受控對照，方法凍結後再建立新的正式測試程序。','',
 '工作已停止；沒有刪除失敗Seed、覆寫歷史成果、部署模型或自動延伸實驗。','']
with (BASE/'B_CANDIDATE_REVIEW_ZH_TW.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines))
print('Traditional Chinese A-M review written from completed evidence; no training/model changes.')
