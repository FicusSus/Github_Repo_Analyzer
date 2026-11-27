import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'

// Register only what the dashboard uses so unused Chart.js code is tree-shaken away.
Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
)

Chart.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
Chart.defaults.font.size = 12
