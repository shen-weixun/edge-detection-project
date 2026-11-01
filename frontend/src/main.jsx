import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ScanFace, LayoutDashboard, Database, History, ArrowUpRight, Upload, Scan, Check, LoaderCircle, GitCompareArrows } from 'lucide-react';
import './style.css';

async function api(path, options) {
  const response = await fetch('/api' + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `請求失敗 (${response.status})`);
  }
  return response.json();
}
const strategies = [['fixed', '固定式／門檻策略'], ['latency_aware', 'Latency-aware'], ['dqn_ddqn', 'DQN／DDQN'], ['decision_model', '決策模型（進階）']];
function TimingResult({ result }) {
  if (!result.timings_ms) return null;
  return <section className="timing-result" aria-label="執行耗時"><h3>執行耗時</h3><p>策略：{strategies.find(([key]) => key === result.strategy)?.[1] ?? result.strategy} · 本地執行</p><div className="timing-grid">{['device', 'edge', 'cloud'].map(target => <div key={target}><span>{target}</span><strong>{result.timings_ms[target] == null ? '未執行' : `${result.timings_ms[target].toFixed(2)} ms`}</strong></div>)}</div><p>目前四種策略皆使用本地後端（device），尚未啟用策略決策或 edge／cloud 卸載。耗時包含圖片解碼、推論與等待；首次執行也包含模型載入，不含上傳網路及資料庫寫入。</p></section>;
}
function App() {
  const [tab, setTab] = useState('detect'), [health, setHealth] = useState(null), [datasets, setDatasets] = useState([]);
  const [file, setFile] = useState(null), [second, setSecond] = useState(null), [preview, setPreview] = useState('');
  const [secondPreview, setSecondPreview] = useState('');
  const [result, setResult] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [dataset, setDataset] = useState('lfw'), [samples, setSamples] = useState([]), [offset, setOffset] = useState(0), [history, setHistory] = useState([]);
  const [threshold, setThreshold] = useState(0.4), [selected, setSelected] = useState(null);
  const [strategy, setStrategy] = useState('fixed');
  const input = useRef();
  async function refresh() { try { const [h, d] = await Promise.all([api('/health'), api('/datasets')]); setHealth(h); setDatasets(d); } catch { setHealth(null); } }
  useEffect(() => { refresh(); }, []);
  useEffect(() => {
    let active = true;
    if (tab === 'datasets') api(`/samples?dataset=${dataset}&offset=${offset}`).then(r => active && setSamples(r)).catch(e => active && setError(e.message));
    if (tab === 'history') api('/history').then(r => active && setHistory(r)).catch(e => active && setError(e.message));
    return () => { active = false; };
  }, [tab, dataset, offset]);
  useEffect(() => { if (!file) return; const url = URL.createObjectURL(file); setPreview(url); return () => URL.revokeObjectURL(url); }, [file]);
  useEffect(() => {
    if (!second) { setSecondPreview(''); return; }
    const url = URL.createObjectURL(second);
    setSecondPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [second]);
  function choose(f) { if (!f) return; if (f.size > 10 * 1024 * 1024) { setError('單張圖片上限為 10 MB'); return; } setFile(f); setSelected(null); setResult(null); setError(''); }
  async function execute() {
    setBusy(true); setError(''); setResult(null);
    try {
      const body = new FormData();
      body.append('strategy', strategy);
      let path;
      if (tab === 'verify') { body.append('first', file); body.append('second', second); body.append('threshold', threshold); path = '/verify'; }
      else if (selected) path = `/samples/${selected}/detect`;
      else { body.append('file', file); path = '/detect'; }
      setResult(await api(path, { method: 'POST', body }));
      refresh();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  function navigate(key) { setTab(key); setError(''); setResult(null); }
  const total = datasets.reduce((n, d) => n + d.count, 0);
  const nav = [['detect', ScanFace, '偵測工作台'], ['verify', GitCompareArrows, '人臉驗證'], ['datasets', Database, '資料集管理'], ['history', History, '實驗紀錄']];
  return <div className="app"><aside><a className="brand" href="#" onClick={() => navigate('detect')}><span><ScanFace size={27}/></span>FaceLab<span className="brand-dot">.</span></a><div className="workspace">WORKSPACE <span>01</span></div><nav>{nav.map(([key, Icon, label]) => <button disabled={busy} key={key} className={tab === key ? 'active' : ''} onClick={() => navigate(key)}><Icon size={19}/>{label}{tab === key && <i/>}</button>)}</nav><div className="side-note"><div className="tiny">POWERED BY</div><strong>InsightFace</strong><p>看見細節，探索人臉視覺。</p><span className="model-tag">buffalo_l · CPU</span></div><div className="side-bottom"><span className="avatar">FL</span><div>研究工作空間<small>LOCAL ENVIRONMENT</small></div></div></aside>
  <main><header><span>工作空間 <span className="slash">/</span> {nav.find(n => n[0] === tab)[2]}</span><button className="status" onClick={refresh}><i className={health ? 'online' : ''}/>{health ? 'API 已連線' : 'API 未連線'}<span>↻</span></button></header><div className="content"><div className="heading"><div><div className="eyebrow">COMPUTER VISION / FACE ANALYSIS</div><h1>{tab === 'detect' ? '讓每一張臉，清晰可見。' : nav.find(n => n[0] === tab)[2]}</h1><p>{tab === 'detect' ? '上傳影像，透過 InsightFace 探索人臉位置與關鍵特徵。' : '從資料到結果，建立可追溯的人臉視覺實驗。'}</p></div><span className="research">研究模式 <ArrowUpRight size={15}/></span></div>
  <div className="stats"><Stat icon={<ScanFace/>} label="推論模型" value="InsightFace" detail="buffalo_l / SCRFD + ArcFace"/><Stat icon={<Database/>} label="已匯入圖片" value={total.toLocaleString()} detail={`${datasets.length} 個資料集分割 · PostgreSQL`}/><Stat icon={<LayoutDashboard/>} label="模型狀態" value={health?.model === 'ready' ? '已就緒' : '等待載入'} detail="首次推論將下載並載入模型"/></div>
  {error && <div className="error" role="alert">{error}</div>}
  {(tab === 'detect' || tab === 'verify') && <div className="studio"><section className="panel"><div className="panel-head"><h2>{tab === 'verify' ? '01 / 比對影像' : '01 / 影像輸入'}</h2><span>JPEG · PNG</span></div><div className="panel-body"><input ref={input} hidden type="file" accept="image/jpeg,image/png" onChange={e => choose(e.target.files[0])}/>
  {!preview ? <button className="dropzone" onClick={() => input.current.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); choose(e.dataTransfer.files[0]); }}><span className="upload-icon"><Upload size={27}/></span><strong>將圖片拖曳至此處</strong><span>或點擊瀏覽本機檔案</span><small>單張上限 10 MB / 2,000 萬像素</small></button> : <><div className="image-stage"><img src={preview} alt="待分析影像"/>{result?.faces && <svg viewBox={`0 0 ${result.width} ${result.height}`} aria-label="人臉偵測框">{result.faces.map((f,i) => <g key={i}><rect x={f.bbox[0]} y={f.bbox[1]} width={f.bbox[2]-f.bbox[0]} height={f.bbox[3]-f.bbox[1]} fill="none" stroke="#66ffd5" strokeWidth={Math.max(2,result.width/300)}/>{f.landmarks.map(([x,y],k) => <circle key={k} cx={x} cy={y} r={result.width/200} fill="#ffe18a"/>)}</g>)}</svg>}</div><button className="text-button" onClick={() => input.current.click()}>重新選擇圖片</button></>}
  {tab === 'verify' && <div className="verify-fields"><label>第二張人臉照片<input type="file" accept="image/jpeg,image/png" onChange={e => { setSecond(e.target.files[0]); setResult(null); }}/></label>{secondPreview && <div className="image-stage"><img src={secondPreview} alt="第二張人臉照片預覽"/></div>}<label>餘弦相似度門檻：{threshold}<input type="range" min="-1" max="1" step="0.01" value={threshold} onChange={e => { setThreshold(Number(e.target.value)); setResult(null); }}/></label><small>每張影像需恰好一張人臉；預設門檻尚未校準。</small></div>}
  <div className="input-footer"><span><Check size={15}/> 上傳影像不保存至磁碟</span><div className="execution-controls"><select aria-label="執行策略" value={strategy} disabled={busy} onChange={e => { setStrategy(e.target.value); setResult(null); }}>{strategies.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><button className="primary" disabled={busy || (!file && !selected) || (tab === 'verify' && (!file || !second))} onClick={execute}>{busy ? <LoaderCircle className="spin" size={17}/> : <Scan size={17}/>} {busy ? '分析中…' : tab === 'verify' ? '開始驗證' : '開始偵測'}</button></div></div></div></section>
  <section className="panel results"><div className="panel-head"><h2>02 / 分析結果</h2><span className="pill">{result ? '完成' : '待執行'}</span></div>{!result ? <div className="empty"><div className="scan-illustration"><ScanFace size={66} strokeWidth={1}/></div><h3>{busy ? '正在分析影像' : '等待你的第一張影像'}</h3><p>{busy ? '首次載入可能需要數分鐘，請稍候。' : '執行分析後，在這裡檢視結果。'}</p><div className="legend"><i/> 人臉框 <i/> 五點特徵</div></div> : <div className="result-body"><TimingResult result={result}/>{result.faces ? <><div className="result-count">{result.faces.length}<span>張人臉</span></div><p>座標以校正方向後的原始影像為基準。</p>{result.faces.map((f,i) => <div className="face-row" key={i}><span>人臉 {String(i+1).padStart(2,'0')}<small>{f.bbox.map(v => Math.round(v)).join(' / ')}</small></span><strong>{(f.score*100).toFixed(1)}%<small>偵測信心分數</small></strong></div>)}</> : <><div className="result-count">{result.similarity.toFixed(3)}</div><h3>{result.match ? '達到比對門檻' : '未達比對門檻'}</h3><p>門檻 {result.threshold} · {result.note}</p></>}<button className="text-button" onClick={() => { const u = URL.createObjectURL(new Blob([JSON.stringify(result,null,2)], {type:'application/json'})); const a = document.createElement('a'); a.href=u; a.download='facelab-result.json'; a.click(); setTimeout(() => URL.revokeObjectURL(u),1000); }}>匯出 JSON ↗</button></div>}</section></div>}
  {tab === 'datasets' && <section className="panel dataset-panel"><div className="panel-head"><h2>資料集瀏覽</h2><select aria-label="選擇資料集" value={dataset} onChange={e => { setDataset(e.target.value); setOffset(0); setSamples([]); }}><option value="lfw">LFW</option><option value="wider_train">WIDER FACE / train</option><option value="wider_val">WIDER FACE / val</option></select></div>{samples.length ? <div className="sample-grid">{samples.map(s => <button key={s.id} onClick={() => { setFile(null); setSelected(s.id); setPreview(s.url); setTab('detect'); setResult(null); }}><img src={s.url} alt={s.label} loading="lazy"/><strong>{s.label.replaceAll('_',' ')}</strong><small>{dataset === 'lfw' ? 'LFW 身分標籤' : `${s.boxes.length} 個有效標註框`} · 點擊偵測</small></button>)}</div> : <div className="empty"><Database size={40}/><h3>尚無圖片</h3><p>請依 README 將資料集放入 data/ 並執行匯入指令。</p></div>}<div className="pagination"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0,offset-24))}>上一頁</button><span>第 {offset/24+1} 頁</span><button disabled={samples.length < 24} onClick={() => setOffset(offset+24)}>下一頁</button></div></section>}
  {tab === 'history' && <section className="panel"><div className="panel-head"><h2>最近 30 次實驗</h2><span>PostgreSQL</span></div>{history.length ? history.map(r => <div className="history-row" key={r.id}><span>#{r.id} · {r.kind === 'verify' ? '人臉驗證' : '人臉偵測'}</span><strong>{r.result.faces ? `${r.result.faces.length} 張人臉` : `相似度 ${r.result.similarity.toFixed(3)}`}</strong><time>{new Date(r.created_at).toLocaleString('zh-TW')}</time></div>) : <div className="empty"><History size={40}/><h3>還沒有實驗紀錄</h3><p>完成偵測或驗證後，結果會自動儲存。</p></div>}</section>}
  <div className="dataset-notes"><div><span className="tiny">DATASET / 01</span><h3>LFW <span>身分驗證</span></h3><p>以人物身分標籤整理影像，支援人臉辨識研究。</p></div><div><span className="tiny">DATASET / 02</span><h3>WIDER FACE <span>人臉偵測</span></h3><p>多尺度、遮擋與複雜場景，提供人臉位置標註。</p></div><a href="https://github.com/deepinsight/insightface" target="_blank" rel="noreferrer">探索 InsightFace<ArrowUpRight size={18}/></a></div><footer>FaceLab / 視覺研究工作台<span>React + Python + PostgreSQL</span></footer></div></main></div>;
}
function Stat({icon,label,value,detail}) { return <div className="stat"><div className="stat-top">{label}{icon}</div><strong>{value}</strong><small>{detail}</small></div>; }
createRoot(document.getElementById('root')).render(<App/>);
