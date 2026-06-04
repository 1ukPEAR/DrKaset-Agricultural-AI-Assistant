import { useEffect, useState } from 'react'
import { ExternalLink, RefreshCw, TrendingUp } from 'lucide-react'
import { marketPriceAPI } from '../../api'
import styles from './MarketPriceWidget.module.css'

function formatPrice(value) {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('th-TH', {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export default function MarketPriceWidget() {
  const [prices, setPrices] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadPrices = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await marketPriceAPI.list()
      setPrices(res.data)
    } catch (err) {
      setError('โหลดราคาจาก OAE ไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPrices()
  }, [])

  return (
    <section className={styles.widget}>
      <div className={styles.header}>
        <div className={styles.title}>
          <TrendingUp size={16} />
          <span>ราคา OAE</span>
        </div>
        <button
          type="button"
          onClick={loadPrices}
          disabled={loading}
          aria-label="โหลดราคาจาก OAE ใหม่"
          title="โหลดราคาจาก OAE ใหม่"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      {loading && !prices ? (
        <div className={styles.state}>กำลังดึงราคาล่าสุด...</div>
      ) : error && !prices ? (
        <div className={styles.state}>{error}</div>
      ) : (
        <>
          <p className={styles.source}>
            {prices.updated_text || prices.title}
          </p>
          <div className={styles.list}>
            {prices.items.map((item) => (
              <a
                className={styles.item}
                href={item.url || prices.source_url}
                target="_blank"
                rel="noreferrer"
                key={item.name}
              >
                <span className={styles.name}>{item.name}</span>
                <strong>{formatPrice(item.price)}</strong>
                <small>{item.unit}</small>
                <ExternalLink size={13} />
              </a>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
