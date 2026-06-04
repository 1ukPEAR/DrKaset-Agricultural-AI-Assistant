import { useEffect, useMemo, useState } from 'react'
import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudRain,
  CloudSun,
  Droplets,
  Moon,
  RefreshCw,
  Sun,
  Wind,
} from 'lucide-react'
import { weatherAPI } from '../../api'
import styles from './WeatherWidget.module.css'

const iconMap = {
  cloud: CloudSun,
  drizzle: CloudDrizzle,
  fog: CloudFog,
  moon: Moon,
  rain: CloudRain,
  sun: Sun,
}

const LOCATION_CACHE_KEY = 'drkaset_weather_location'
const LOCATION_CACHE_TTL = 30 * 60 * 1000

function getCachedLocation() {
  try {
    const cached = JSON.parse(sessionStorage.getItem(LOCATION_CACHE_KEY) || 'null')
    if (!cached || Date.now() - cached.timestamp > LOCATION_CACHE_TTL) return null
    return cached.coords
  } catch {
    return null
  }
}

function setCachedLocation(coords) {
  sessionStorage.setItem(
    LOCATION_CACHE_KEY,
    JSON.stringify({ coords, timestamp: Date.now() })
  )
}

function getCurrentPosition() {
  if (!navigator.geolocation) return Promise.resolve(null)

  const cached = getCachedLocation()
  if (cached) return Promise.resolve(cached)

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const location = {
          lat: Number(coords.latitude.toFixed(4)),
          lon: Number(coords.longitude.toFixed(4)),
        }
        setCachedLocation(location)
        resolve(location)
      },
      () => resolve(null),
      {
        enableHighAccuracy: false,
        maximumAge: LOCATION_CACHE_TTL,
        timeout: 8000,
      }
    )
  })
}

function WeatherIcon({ name, size = 36 }) {
  const Icon = iconMap[name] || Cloud
  return <Icon size={size} strokeWidth={1.8} />
}

function HourlyChart({ hourly = [] }) {
  const points = useMemo(() => {
    if (!hourly.length) return ''
    const temps = hourly.map((item) => item.temperature)
    const min = Math.min(...temps)
    const max = Math.max(...temps)
    const spread = Math.max(max - min, 1)
    return hourly
      .map((item, index) => {
        const x = hourly.length === 1 ? 0 : (index / (hourly.length - 1)) * 100
        const y = 80 - ((item.temperature - min) / spread) * 52
        return `${x},${y}`
      })
      .join(' ')
  }, [hourly])

  if (!hourly.length) return null

  return (
    <div className={styles.chart}>
      <svg className={styles.chartSvg} viewBox="0 0 100 88" preserveAspectRatio="none">
        <polyline className={styles.chartLine} points={points} />
      </svg>
      <div className={styles.hourLabels}>
        {hourly.map((item) => (
          <span key={item.time}>
            <strong>{item.temperature}°</strong>
            {item.hour}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function WeatherWidget() {
  const [weather, setWeather] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadWeather = async () => {
    setLoading(true)
    setError('')
    try {
      const coords = await getCurrentPosition()
      const res = await weatherAPI.current(coords || undefined)
      setWeather(res.data)
    } catch (err) {
      setError('ไม่สามารถโหลดสภาพอากาศได้')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadWeather()
  }, [])

  if (loading && !weather) {
    return <section className={`${styles.widget} ${styles.loading}`}>กำลังโหลดสภาพอากาศ...</section>
  }

  if (error && !weather) {
    return (
      <section className={styles.widget}>
        <div className={styles.errorRow}>
          <span>{error}</span>
          <button type="button" onClick={loadWeather} aria-label="โหลดข้อมูลอากาศอีกครั้ง">
            <RefreshCw size={16} />
          </button>
        </div>
      </section>
    )
  }

  const current = weather.current

  return (
    <section className={styles.widget}>
      <div className={styles.topRow}>
        <div className={styles.place}>
          <span>สภาพอากาศ</span>
          <strong>{weather.location.name}</strong>
        </div>
        <button
          className={styles.refreshButton}
          type="button"
          onClick={loadWeather}
          disabled={loading}
          aria-label="โหลดข้อมูลอากาศใหม่"
          title="โหลดข้อมูลอากาศใหม่"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      <div className={styles.currentGrid}>
        <div className={styles.currentMain}>
          <WeatherIcon name={current.icon} size={54} />
          <div>
            <div className={styles.temp}>{current.temperature}°C</div>
            <div className={styles.condition}>{current.condition}</div>
          </div>
        </div>
        <div className={styles.metrics}>
          <span><Droplets size={14} /> ความชื้น {current.humidity}%</span>
          <span><CloudRain size={14} /> ฝน {current.precipitation} มม.</span>
          <span><Wind size={14} /> ลม {current.wind_speed} กม./ชม.</span>
        </div>
      </div>

      <HourlyChart hourly={weather.hourly} />

      <div className={styles.daily}>
        {weather.daily.slice(0, 6).map((day) => (
          <div className={styles.day} key={day.date}>
            <span>{day.weekday}</span>
            <WeatherIcon name={day.icon} size={24} />
            <strong>{day.temp_max}°</strong>
            <em>{day.temp_min}°</em>
          </div>
        ))}
      </div>
    </section>
  )
}
