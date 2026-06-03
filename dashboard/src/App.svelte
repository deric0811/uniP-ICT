<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Line } from 'svelte-chartjs';
  import {
    Chart as ChartJS,
    Title,
    Tooltip,
    Legend,
    LineElement,
    LinearScale,
    PointElement,
    CategoryScale,
  } from 'chart.js';

  // Chart.js 모듈 등록
  ChartJS.register(Title, Tooltip, Legend, LineElement, LinearScale, PointElement, CategoryScale);

  const API_URL = 'https://h2omol.com/api/uniP/data/latest?limit=30';
  const POLLING_INTERVAL = 3000; // 3초 폴링 (서버 복구 딜레이 완벽 대응)

  let intervalId: number;
  
  // 최신 상태 저장용 변수
  let currentStatus = "Loading...";
  let currentMetrics = { temp: 0, hum: 0, pm25: 0 };
  let lastUpdate = "";

  // 차트 데이터 반응형 객체
  let chartData = {
    labels: [] as string[],
    datasets: [] as any[]
  };

  // API 폴링 및 데이터 정제 함수
  async function fetchData() {
    try {
      const response = await fetch(API_URL);
      if (!response.ok) throw new Error('API fetch failed');
      const data = await response.json(); // Array of 30 items (시간 오름차순)

      if (data.length === 0) return;

      // 1. 라벨(시간) 추출 (Python timestamp가 초 단위인지 밀리초 단위인지 대응)
      const labels = data.map((d: any) => {
        const date = new Date(d.timestamp > 1e11 ? d.timestamp : d.timestamp * 1000);
        return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`;
      });

      // 2. CO2 데이터 시리즈 3종 추출
      const gtData = data.map((d: any) => d.ground_truth.co2);
      const rxData = data.map((d: any) => d.received.co2); // 결측치는 null
      const recData = data.map((d: any) => d.recovered.co2);

      // 3. 최신 상태 업데이트 (화면 상단 UI용)
      const latest = data[data.length - 1];
      currentStatus = latest.decision || "Unknown";
      currentMetrics = {
        temp: latest.recovered.temp,
        hum: latest.recovered.hum,
        pm25: latest.recovered.pm25
      };
      lastUpdate = labels[labels.length - 1];

      // 4. 차트 데이터 덮어쓰기 (Svelte 반응성 트리거)
      chartData = {
        labels,
        datasets: [
          {
            label: 'Ground-Truth (원본)',
            data: gtData,
            borderColor: 'rgba(156, 163, 175, 0.4)', // 옅은 회색
            borderDash: [5, 5],
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.1
          },
          {
            label: 'Received (수신됨)',
            data: rxData,
            borderColor: 'rgba(239, 68, 68, 1)', // 빨간색
            backgroundColor: 'rgba(239, 68, 68, 0.8)',
            borderWidth: 0, // 선은 없애고 점만 찍어서 유실을 극적으로 표현
            pointRadius: 5,
            spanGaps: false // 핵심: 데이터가 없으면 선이 끊어짐
          },
          {
            label: 'Recovered (LOCF 복구)',
            data: recData,
            borderColor: 'rgba(16, 185, 129, 0.8)', // 에메랄드 (Tailwind green-500)
            borderWidth: 3,
            pointRadius: 0,
            tension: 0.3 // 부드러운 곡선
          }
        ]
      };
    } catch (error) {
      console.error("데이터 로드 실패:", error);
    }
  }

  onMount(() => {
    fetchData(); // 마운트 즉시 1회 호출
    intervalId = window.setInterval(fetchData, POLLING_INTERVAL);
  });

  onDestroy(() => {
    if (intervalId) clearInterval(intervalId);
  });

  // 차트 옵션
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 0 }, // 폴링마다 차트가 번쩍이는 현상 방지
    scales: {
      y: {
        grid: { color: 'rgba(255, 255, 255, 0.05)' },
        ticks: { color: '#9CA3AF' },
        suggestedMin: 350,
        suggestedMax: 1200
      },
      x: {
        grid: { display: false },
        ticks: { color: '#6B7280', maxTicksLimit: 10 }
      }
    },
    plugins: {
      legend: { labels: { color: '#D1D5DB', usePointStyle: true, boxWidth: 8 } }
    }
  };
</script>

<main class="min-h-screen bg-[#0a0a0a] text-neutral-200 p-8 font-sans">
  <div class="max-w-6xl mx-auto space-y-6">
    
    <header class="flex justify-between items-end border-b border-neutral-800 pb-4">
      <div>
        <h1 class="text-3xl font-bold tracking-tight text-white">Air Quality Monitoring</h1>
        <p class="text-neutral-500 mt-1">Fault-Tolerant System Dashboard (LOCF Imputation)</p>
      </div>
      <div class="text-right">
        <p class="text-xs text-neutral-500 uppercase tracking-widest mb-1">System Status</p>
        <div class="flex items-center gap-3">
          <span class="relative flex h-3 w-3">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
          </span>
          <span class="text-2xl font-bold {currentStatus === 'Good' ? 'text-green-500' : currentStatus === 'Moderate' ? 'text-yellow-500' : 'text-red-500'}">
            {currentStatus}
          </span>
        </div>
        <p class="text-xs text-neutral-600 mt-1">Last Sync: {lastUpdate}</p>
      </div>
    </header>

    <div class="grid grid-cols-3 gap-4">
      <div class="bg-neutral-900 border border-neutral-800 p-4 rounded-xl">
        <p class="text-neutral-500 text-sm">Temperature</p>
        <p class="text-2xl font-semibold mt-1">{currentMetrics.temp.toFixed(1)} <span class="text-sm text-neutral-600">°C</span></p>
      </div>
      <div class="bg-neutral-900 border border-neutral-800 p-4 rounded-xl">
        <p class="text-neutral-500 text-sm">Humidity</p>
        <p class="text-2xl font-semibold mt-1">{currentMetrics.hum.toFixed(1)} <span class="text-sm text-neutral-600">%</span></p>
      </div>
      <div class="bg-neutral-900 border border-neutral-800 p-4 rounded-xl">
        <p class="text-neutral-500 text-sm">PM 2.5</p>
        <p class="text-2xl font-semibold mt-1">{currentMetrics.pm25.toFixed(1)} <span class="text-sm text-neutral-600">µg/m³</span></p>
      </div>
    </div>

    <div class="bg-neutral-900 border border-neutral-800 p-6 rounded-xl shadow-2xl">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-semibold text-neutral-300">CO2 Concentration & Imputation (Real-time)</h2>
        <div class="flex gap-4 text-xs">
          <span class="flex items-center gap-2"><div class="w-3 h-[2px] bg-neutral-400 border-dashed border-b-2"></div> Ground Truth</span>
          <span class="flex items-center gap-2"><div class="w-2 h-2 rounded-full bg-red-500"></div> Received (Lossy)</span>
          <span class="flex items-center gap-2"><div class="w-3 h-[3px] bg-green-500"></div> Recovered</span>
        </div>
      </div>
      <div class="h-[450px] w-full">
        {#if chartData.labels.length > 0}
          <Line data={chartData} options={chartOptions} />
        {:else}
          <div class="h-full w-full flex items-center justify-center text-neutral-600">
            Waiting for data stream...
          </div>
        {/if}
      </div>
    </div>

  </div>
</main>
