const baseUrlEl = document.getElementById("baseUrl");
const patientIdEl = document.getElementById("patientId");
const fetchBtn = document.getElementById("fetchBtn");
const errorEl = document.getElementById("error");
const canvas = document.getElementById("chart");

let chart = null;

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.style.display = "block";
}

function hideError() {
  errorEl.style.display = "none";
}

fetchBtn.addEventListener("click", async () => {
  const baseUrl = baseUrlEl.value.trim();
  const patientId = patientIdEl.value.trim();
  if (!baseUrl || !patientId) {
    showError("Enter API base URL and Patient ID.");
    return;
  }
  hideError();
  const url = `${baseUrl.replace(/\/$/, "")}/api/history/${encodeURIComponent(patientId)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    if (!Array.isArray(data) || data.length === 0) {
      showError("No history for this patient.");
      renderChart([]);
      return;
    }
    renderChart(data);
  } catch (e) {
    showError("Failed to load history: " + e.message);
    renderChart([]);
  }
});

function renderChart(history) {
  const labels = history.map((_, i) => `Session ${i + 1}`);
  const scores = history.map((d) => d.anomaly_score);

  if (chart) chart.destroy();
  chart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Anomaly score",
          data: scores,
          borderColor: "rgb(75, 192, 192)",
          tension: 0.1,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "MSE" } },
      },
    },
  });
}
