import time
import random
import json
import requests
import paho.mqtt.client as mqtt
from datetime import datetime

import ssl
import random
import time
import threading

# ==========================================
# ⚙️ 설정 (Configuration)
# ==========================================
MQTT_HOST = "uniP-ICT.h2omol.com" 
MQTT_PORT = 8883
MQTT_TOPIC = "campus/room_101/sensors/air"
HTTP_ENDPOINT = f"https://h2omol.com/api/uniP/internal/ground_truth" #검증용 ground truth.

# 전송 주기 (초)
INTERVAL = 3

# ==========================================
# 📊 가상 센서 상태 (초기값)
# ==========================================
state = {
    "co2": 450.0,
    "temp": 22.0,
    "hum": 40.0,
    "pm25": 10.0
}

manual_spike = False # 입김 이벤트 플래그

def wait_for_enter():
    """백그라운드에서 엔터 키 입력을 대기하는 함수"""
    global manual_spike
    while True:
        input() # 엔터 키 대기 (출력 없이 조용히 대기)
        manual_spike = True
        print("\n💨 [이벤트 발생] 누군가 센서에 입김을 불었습니다! (CO2 폭증)")

def generate_realistic_data():
    """이전 값을 기반으로 서서히 변하는 현실적인 데이터를 생성합니다."""
    global state, manual_spike
    
    # CO2: 사람이 있으면 오르고, 가끔 크게 튐 (400 ~ 2000 범위)
    state["co2"] += random.uniform(-10, 25)
    state["co2"] = max(400, min(state["co2"], 2000))
    
    # 온도: 매우 서서히 변함 (18 ~ 30 범위)
    state["temp"] += random.uniform(-0.1, 0.15)
    state["temp"] = max(18, min(state["temp"], 30))
    
    # 습도: 서서히 변함 (30 ~ 70 범위)
    state["hum"] += random.uniform(-0.5, 0.5)
    state["hum"] = max(30, min(state["hum"], 70))
    
    # PM2.5: 기본적으로 낮지만, 가끔 먼지가 발생해 튐
    if random.random() < 0.1: # 10% 확률로 미세먼지 스파이크
        state["pm25"] += random.uniform(10, 30)
    else:
        state["pm25"] += random.uniform(-2, 1)
    state["pm25"] = max(5, min(state["pm25"], 150))
    
    # 🚨 입김 스파이크 이벤트 적용
    current_co2 = state["co2"]
    if manual_spike:
        current_co2 += random.uniform(2000, 4000) # 순간적으로 600~900 튀어오름
        manual_spike = False # 플래그 초기화
    

    return {
        "timestamp": int(time.time()),
        "sensor_id": "v_sensor_01",
        "data": {
            "co2": round(current_co2, 1),
            "temp": round(state["temp"], 2),
            "hum": round(state["hum"], 1),
            "pm25": round(state["pm25"], 1)
        }
    }

def main():
    print(f"🚀 가상 센서 가동 시작... (Target IP: {MQTT_HOST})")
    print("💡 [안내] 실행 중 언제라도 '엔터 키'를 누르면 CO2 폭증 이벤트가 발생합니다.\n")

    # 키보드 입력 감지 스레드 백그라운드 실행
    threading.Thread(target=wait_for_enter, daemon=True).start()

    # MQTT 클라이언트 설정
    # mqtt_client = mqtt.Client()
    # mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    
    # MQTT 클라이언트설정 v2
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    
    # 2. SSL 인증서 호스트명 검증 무시 (인증서 불일치 에러 해결)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    mqtt_client.tls_set_context(ssl_context)

    try:
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
        mqtt_client.loop_start()
        mqtt_connected = True
        print("✅ MQTT Broker 연결 성공")
    except Exception as e:
        mqtt_connected = False
        print(f"⚠️ MQTT 연결 실패 (서버가 아직 없으므로 정상입니다). 에러: {e}")

    try:
        while True:
            # 1. 데이터 생성
            payload = generate_realistic_data()
            json_payload = json.dumps(payload)
            
            now_str = datetime.now().strftime('%H:%M:%S')
            print(f"\n[{now_str}] 📡 생성된 데이터: {json_payload}")

            # 2. HTTP 전송 (Ground Truth - 원본 데이터)
            try:
                res = requests.post(HTTP_ENDPOINT, json=payload, timeout=2)
                print(f"  👉 [HTTP] Ground Truth 전송 완료 (Status: {res.status_code})")
            except requests.exceptions.RequestException:
                print("  👉 [HTTP] 서버 응답 없음 (API 서버 대기중...)")

            # 3. MQTT 전송 (네트워크 오염 시뮬레이션용 데이터)
            if mqtt_connected:
                # 40% 확률로 패킷 로스(Loss) 시뮬레이션
                if random.random() < 0.4:
                    print("  💥 [장애 시뮬레이션] Packet Loss 발생! MQTT 전송을 고의로 누락합니다.")
                else:
                    # 네트워크 지연(Delay) 시뮬레이션: 0.1초 ~ 0.8초 사이의 랜덤 지연
                    time.sleep(random.uniform(0.1, 0.8))
                    mqtt_client.publish(MQTT_TOPIC, json_payload, qos=0) # Imputation로직을 보이기 위해 QoS level = 0
                    print("  👉 [MQTT] 메시지 Publish 완료")           
            
            # 4. 대기
            time.sleep(INTERVAL)
            
    except KeyboardInterrupt:
        print("\n🛑 가상 센서 작동을 중지합니다.")
        if mqtt_connected:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()

if __name__ == "__main__":
    main()
