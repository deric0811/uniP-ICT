import sqlite3
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import paho.mqtt.client as mqtt

# ==========================================
# ⚙️ 설정값
# ==========================================
DB_FILE = "sensor.db"
MQTT_BROKER = "127.0.0.1" # docker 로컬 브로커
MQTT_TOPIC = "campus/room_101/sensors/air"

# ==========================================
# 🗄️  SQLite DB 초기화 (앱 실행 시 자동 생성)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metrics (
            timestamp INTEGER PRIMARY KEY,
            sensor_id TEXT,
            gt_co2 REAL, gt_temp REAL, gt_hum REAL, gt_pm25 REAL,
            rx_co2 REAL, rx_temp REAL, rx_hum REAL, rx_pm25 REAL
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ SQLite DB 준비 완료 (sensor.db)")

# ==========================================
# 📡 MQTT 콜백 (네트워크 오염 시뮬레이션용 데이터 수신)
# ==========================================
def on_connect(client, userdata, flags, rc):
    print(f"🔌 MQTT Broker 연결됨 (Result Code: {rc})")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    ts = payload["timestamp"]
    data = payload["data"]

    # MQTT로 들어온 데이터(rx)를 DB에 업데이트 (netem으로 지연/손실 가능성 있음)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 이미 Ground-Truth가 기록되어 있으면 UPDATE, 아니면 INSERT
    cursor.execute('''
        INSERT INTO metrics (timestamp, sensor_id, rx_co2, rx_temp, rx_hum, rx_pm25)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(timestamp) DO UPDATE SET
            rx_co2=excluded.rx_co2, rx_temp=excluded.rx_temp,
            rx_hum=excluded.rx_hum, rx_pm25=excluded.rx_pm25
    ''', (ts, payload["sensor_id"], data["co2"], data["temp"], data["hum"], data["pm25"]))
    conn.commit()
    conn.close()
    print(f"📥 [MQTT] 데이터 수신 및 DB 적재 (TS: {ts})")

# ==========================================
# 🚀 FastAPI LifeSpan (서버 시작/종료 시 이벤트)
# ==========================================
mqtt_client = mqtt.Client()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB 셋업
    init_db()
    # 2. MQTT 백그라운드 쓰레드 시작
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    try:
        mqtt_client.connect(MQTT_BROKER, 1883, 60)
        mqtt_client.loop_start() # 논블로킹으로 MQTT 수신 대기
    except Exception as e:
        print(f"⚠️ MQTT 브로커에 연결할 수 없습니다. (브로커 도커를 아직 안 띄웠다면 정상입니다): {e}")

    yield # --- 서버 가동 중 ---

    # 3. 서버 종료 시 정리
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    print("🛑 서버 종료됨")

# ==========================================
# 🌐 FastAPI 앱 및 라우터 설정
# ==========================================
app = FastAPI(lifespan=lifespan)

# Svelte(다른 포트)에서 API를 호출할 수 있도록 CORS 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Model
class SensorData(BaseModel):
    timestamp: int
    sensor_id: str
    data: dict

@app.post("/api/uniP/internal/ground_truth")
def receive_ground_truth(payload: SensorData):
    """(1) 랩탑 스크립트가 보내는 완벽한 원본 데이터를 DB에 Insert"""
    data = payload.data
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO metrics (timestamp, sensor_id, gt_co2, gt_temp, gt_hum, gt_pm25)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(timestamp) DO UPDATE SET
            gt_co2=excluded.gt_co2, gt_temp=excluded.gt_temp,
            gt_hum=excluded.gt_hum, gt_pm25=excluded.gt_pm25
    ''', (payload.timestamp, payload.sensor_id, data.get("co2"), data.get("temp"), data.get("hum"), data.get("pm25")))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": "Ground truth recorded"}

@app.get("/api/uniP/data/latest")
def get_latest_data(limit: int = 30):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM metrics ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    rows.reverse() # 시간 오름차순 정렬 (과거 -> 현재)

    # 🛠️ [핵심 아키텍쳐] 논리 판단용(RAW) 기준점 초기화
    last_valid_raw = {}
    for key in ["co2", "temp", "hum", "pm25"]:
        fallback = {"co2": 400.0, "temp": 22.0, "hum": 40.0, "pm25": 10.0}[key]
        
        # NULL이 아닌 수신된 데이터만 리스트로 추출
        valid_vals = [dict(r)[f"rx_{key}"] for r in rows if dict(r)[f"rx_{key}"] is not None]
        
        stable_val = fallback
        if len(valid_vals) > 0:
            stable_val = valid_vals[0] # 일단 첫 번째 값을 임시 할당
            # '연속으로 임계치 이내인 두 값'을 찾아 진짜 안정적인 기준점으로 굳힘
            for i in range(len(valid_vals) - 1):
                if abs(valid_vals[i] - valid_vals[i+1]) <= thresholds[key]:
                    stable_val = valid_vals[i]
                    break # 안정적인 기준점을 찾았으므로 즉시 탐색 종료
                    
        last_valid_raw[key] = stable_val

    ma_window = {"co2": [], "temp": [], "hum": [], "pm25": []}
    thresholds = {"co2": 100.0, "temp": 2.0, "hum": 5.0, "pm25": 15.0}

    result = []

    for row in rows:
        row_dict = dict(row)
        recovered = {}
        is_imputed = False

        for key in ["co2", "temp", "hum", "pm25"]:
            rx_val = row_dict[f"rx_{key}"]
            candidate_val = rx_val

            # [Step 1] 결측치 및 임계치 필터링 (반드시 순수 RAW 데이터인 last_valid_raw와 비교)
            if rx_val is None:
                is_imputed = True
                candidate_val = last_valid_raw[key] # 단순 유실: LOCF
            elif abs(rx_val - last_valid_raw[key]) > thresholds[key]:
                is_imputed = True
                candidate_val = last_valid_raw[key] # 비정상 폭증: 노이즈 필터링 후 LOCF 방어
            else:
                last_valid_raw[key] = rx_val # ✅ 정상 데이터일 때만 RAW 기준점 갱신

            # [Step 2] 스무딩을 위한 MA(이동 평균) 버퍼 계산
            ma_window[key].append(candidate_val)
            if len(ma_window[key]) > 3:
                ma_window[key].pop(0) # 윈도우 사이즈 3 유지

            final_val = sum(ma_window[key]) / len(ma_window[key])
            recovered[key] = round(final_val, 1)

        # 의사결정 상태 도출 (CO2 기준)
        status = "Good"
        if recovered["co2"] > 1000:
            status = "Ventilation Needed"
        elif recovered["co2"] > 800:
            status = "Moderate"

        result.append({
            "timestamp": row_dict["timestamp"],
            "ground_truth": {k: row_dict[f"gt_{k}"] for k in ["co2", "temp", "hum", "pm25"]},
            "received": {k: row_dict[f"rx_{k}"] for k in ["co2", "temp", "hum", "pm25"]},
            "recovered": recovered,
            "is_imputed": is_imputed,
            "decision": status
        })

    return result
