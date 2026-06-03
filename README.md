# 🌬️ Smart Classroom Air Quality Monitoring System
**Edge-level Fault-Tolerant IoT System (MVP)**

## 📺 Demonstration Video
> **[Watch the Live Demo Here](YOUR_YOUTUBE_LINK_HERE)**
LINK LINK LINK

## 💡 System Overview
본 프로젝트는 스마트 강의실 및 스마트홈 환경을 위한 **결함 감내(Fault-Tolerant) 공기질 모니터링 시스템**입니다. 
무선 IoT 환경(Wi-Fi, Zigbee 등)에서 필연적으로 발생하는 **네트워크 패킷 유실(Packet Loss)**과 물리적 **센서 노이즈(Spike)**를 Edge Server(Raspberry Pi 5) 단에서 실시간으로 자가 복구합니다. 이를 통해 네트워크가 불안정한 상황에서도 단 1초의 중단 없이 일관된 환경 의사결정(예: 환기 필요 알림)을 내릴 수 있는 견고한 데이터 파이프라인을 구축했습니다.

## 🏗️ Architecture & Tech Stack
* **Virtual Sensor (Client):** Python (`paho-mqtt`, `requests`) - 원본(HTTP)과 오염된 데이터(MQTTS)를 동시 전송 및 장애(Drop/Spike) 시뮬레이션
* **Edge Infrastructure (RPi5):** Docker, Nginx (Reverse Proxy & TCP Stream), Eclipse Mosquitto
* **Backend (Data Pipeline):** Python FastAPI, SQLite - 3단계 Imputation 로직 처리 및 비동기 통신
* **Frontend (Dashboard):** Svelte, Vite, Tailwind CSS, Chart.js - 실시간 Polling 및 다중 데이터 시각화

## ⚙️ Core Logic: 3-Stage Imputation Pipeline
시스템은 수신된 불완전한 데이터를 다음 3단계 파이프라인을 거쳐 완벽하게 복구합니다.

1.  **Threshold Filtering (노이즈 컷오프):** 센서 오작동이나 물리적 간섭(예: 센서에 입김을 부는 행위)으로 인해 1틱(3초) 내에 임계치(CO2 기준 100ppm)를 초과하는 비정상적인 폭증이 발생하면, 이를 노이즈로 간주하고 즉시 Drop 합니다.
2.  **LOCF (Last Observation Carried Forward):** 네트워크 장애로 데이터가 유실되거나 1단계에서 노이즈가 Drop 된 경우, 가장 최근에 수신된 안전한 검증 데이터(Raw Baseline)를 끌어와 빈 구간을 평행하게 방어합니다.
3.  **Moving Average (스무딩):** 통신이 복구되어 새로운 데이터가 유입될 때 발생할 수 있는 차트의 직각 꺾임 현상을 방지하기 위해, Window Size=3의 이동 평균을 적용하여 시각적 연속성(Smoothing)을 보장합니다.

## 📁 Repository Structure
```text
.
├── /src                    # Backend API, Virtual Sensor, Infrastructure Config
│   ├── main.py             # FastAPI Server & Imputation Logic
│   ├── sensor_sim.py       # Virtual Sensor & Fault Injector
│   ├── nginx.conf          # Nginx Reverse/Stream Proxy Configuration (Masked)
│   └── requirements.txt    # Python Dependencies
├── /dashboard              # Frontend Web GUI (Svelte Dashboard)
│   ├── src/                # Svelte Components and Assets
│   ├── package.json        # Node Modules
│   └── tailwind.config.js  # Styling Configurations
├── /data                   # Sample SQLite Data Extraction
│   └── sample_data.csv     # 200 rows of synthetic air quality metrics
├── README.md               # System overview and logic
└── TROUBLESHOOTING.md      # Engineering log & major bug fixes


---

### 📄 2. `TROUBLESHOOTING.md`

```markdown
# 🛠️ Troubleshooting & Engineering Log

본 문서는 시스템을 구축하며 마주친 핵심적인 아키텍처 결함과, 이를 극복하기 위해 적용한 엔지니어링 문제 해결(Troubleshooting) 과정을 기록합니다.

## Issue 1. Docker Network Bypass (iptables 격리 실패)
* **Problem:** 네트워크 장애(Packet Loss 40%) 시뮬레이션을 위해 라즈베리파이 호스트에서 `tc netem` 및 `iptables -A INPUT` 명령어를 사용하여 MQTTS(8883 포트) 트래픽을 강제 Drop 하려 했습니다. 그러나 대시보드와 SQLite DB에는 아무런 유실 없이 데이터가 100% 적재되는 현상이 발생했습니다.
* **Root Cause Analysis:** 수신 브로커(Mosquitto)와 리버스 프록시(Nginx)를 **Docker 컨테이너**로 띄운 것이 원인이었습니다. Docker는 자체적인 NAT 라우팅 규칙을 생성하여 들어오는 트래픽을 호스트의 `INPUT` 체인에 닿기 전에 `PREROUTING` 단계에서 가로채어 `FORWARD` 체인으로 직행시킵니다.
* **Solution:** 호스트 방화벽 대신 Docker 네트워크 스택이 평가하는 공식 체인인 `DOCKER-USER`를 공략했습니다. 
    `sudo iptables -I DOCKER-USER 1 -p tcp --dport 8883 -m statistic --mode random --probability 0.4 -j DROP` 명령어를 통해 타 서비스에 영향을 주지 않고 MQTT 트래픽만 완벽하게 고립시켜 장애를 주입하는 데 성공했습니다. (이후 시연 편의성과 TCP 재전송(Retransmission) 변수를 완전히 통제하기 위해 가상 센서 애플리케이션 레벨의 장애 주입으로 최종 선회함)

## Issue 2. The "Threshold Trapping" Anomaly (임계치 함정)
* **Problem:** CO2 농도가 급격히 상승하는 구간에서, 가상 센서에 노이즈(입김 스파이크)를 주입하자 Recovered 선이 기준선(Ground Truth)으로 복귀하지 못하고 영원히 아래에 깔려버리는 '괴리 현상'이 발생했습니다.
* **Root Cause Analysis:** Moving Average(이동 평균)의 고질적인 **후행성(Lagging)**이 원인이었습니다. 논리 검사용 임계치(Threshold)의 기준이 되는 `last_known` 값을 시각화 처리가 끝난 'MA 값'으로 덮어씌웠기 때문입니다. MA는 실제 값보다 항상 과거에 머물러 있으므로, 정상적인 상승 데이터가 들어와도 MA 기준점과의 격차가 커져 이를 '노이즈'로 오판하고 Drop 해버리는 악순환에 빠진 것입니다.
* **Solution: Decoupling (계층 분리).** 백엔드 로직에서 임계치를 검사하는 **논리 판단 계층(Raw Baseline)**과 대시보드에 그리기 위한 **시각화 계층(MA Buffer)**을 완벽히 분리했습니다. 정상 데이터로 판별될 때만 Raw 기준점을 갱신하게 하여 오판을 원천 차단했습니다.

## Issue 3. Cold Start Spike 방어 (초기화 이상치)
* **Problem:** 시스템을 재시작했을 때 간헐적으로 Recovered 선이 4000ppm이라는 비정상적인 위치에서 평행선을 그리는 치명적인 버그가 발견되었습니다.
* **Root Cause Analysis:** 프론트엔드가 Polling을 통해 최근 30개의 데이터를 가져갈 때, 하필 그 30개 중 '첫 번째' 데이터가 과거에 발생했던 거대한 스파이크(이상치) 값이었던 상황입니다. 시스템은 무조건 첫 번째 값을 기준점으로 삼도록 하드코딩되어 있었기 때문에, 4000이라는 스파이크를 정상 궤도로 맹신하고 이후에 들어오는 600대의 정상 수치들을 모조리 노이즈로 판별해 잘라냈습니다.
* **Solution: Stable Baseline 궤도 탐색.** 초기 기준점을 잡을 때 단순히 첫 번째 데이터를 맹신하지 않도록 로직을 수정했습니다. 30개의 윈도우 내에서 `abs(val[i] - val[i+1]) <= threshold` 공식을 통해 **'연속된 두 값의 편차가 임계치 이내인 안정적인 궤도'**를 먼저 탐색한 뒤, 이를 진정한 기준점으로 삼는 Cold Start 방어 로직을 추가하여 무결성을 확보했습니다.
