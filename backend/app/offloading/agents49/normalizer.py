"""SimPy 49 維觀測正規化。固定轉換，訓練與推論務必共用。"""
import numpy as np

# Task 7 + (Local/Edge/Cloud 各14)；順序與 integration_contract.FEATURE_NAMES 一致。
FEATURE_NAMES = (
    'image_size_mb','width','height','arrival_ms','deadline_ms',
    'estimated_workload_ms','result_size_kb',
) + tuple(
    f'{node}.{field}' for node in ('local','edge','cloud') for field in (
        'compute_speed','queue_length','queue_work_ms','rtt_ms',
        'bandwidth_mbps','upload_backlog_ms','download_backlog_ms',
        'available','cpu_running','committed_count','transmitting_count',
        'returning_count','committed_work_ms','observed_at_ms'
    )
)
# 經驗尺度只是數值穩定化的起始設定；不依賴未來資料進行擬合。
SCALES = np.array([
    5,1920,1080,60000,1000,1000,16,
] + [
    4,20,5000,500,100,5000,5000,1,8,20,20,20,5000,60000
] * 3, dtype=np.float64)
BINARY_INDICES = (14,28,42)  # 0-based：三個 available 欄位
CONTRACT_VERSION = 'simpy49-log1p-v1'


def normalize(state):
    """將長度49的原始觀測轉為模型輸入；非負欄位使用 log1p 穩定尺度。"""
    x = np.asarray(state, dtype=np.float64)
    if x.shape != (49,):
        raise ValueError(f'需要49維 state，實際為 {x.shape}')
    if not np.all(np.isfinite(x)) or np.any(x < 0):
        raise ValueError('State 必須為有限且非負數值')
    for idx in BINARY_INDICES:
        if x[idx] not in (0.0, 1.0):
            raise ValueError(f'{FEATURE_NAMES[idx]} 必須為0或1')
    y = np.log1p(x / SCALES)
    y[list(BINARY_INDICES)] = x[list(BINARY_INDICES)]
    return y.astype(np.float64)


def available_actions(raw_state):
    """只允許 SimPy 宣告 available=1 的節點被選擇。"""
    x = np.asarray(raw_state)
    if x.shape != (49,):
        raise ValueError('需要49維 state')
    actions = [i for i, idx in enumerate(BINARY_INDICES) if x[idx] == 1]
    if not actions:
        raise ValueError('沒有任何 available=1 的節點；需由模擬器處理無可用節點情況')
    return actions
