import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity, Database, Cpu, Layers,
  CheckCircle, XCircle, RefreshCw, ArrowLeft
} from 'lucide-react'
import { healthAPI } from '../api'
import Sidebar from '../components/layout/Sidebar'
import { useChat } from '../hooks/useChat'
import styles from './HealthPage.module.css'

function StatusCard({ icon: Icon, title, status, detail }) {
  const ok = status === 'ok' || status === 'loaded'
  return (
    <div className={`${styles.statusCard} ${ok ? styles.ok : styles.error}`}>
      <div className={styles.statusTop}>
        <div className={styles.statusIcon}><Icon size={20} /></div>
        <div className={styles.statusInfo}>
          <h3>{title}</h3>
          <p>{detail || status}</p>
        </div>
        <div className={styles.statusBadge}>
          {ok
            ? <><CheckCircle size={16} /> ปกติ</>
            : <><XCircle size={16} /> ผิดพลาด</>}
        </div>
      </div>
    </div>
  )
}

export default function HealthPage() {
  const navigate = useNavigate()
  const { sessions, fetchSessions, loadingSessions, loadSession, activeSession, newSession } = useChat()
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastChecked, setLastChecked] = useState(null)

  const check = async () => {
    setLoading(true)
    try {
      const r = await healthAPI.check()
      setHealth(r.data)
      setLastChecked(new Date())
    } catch {
      setHealth({ db: 'error: ไม่สามารถเชื่อมต่อได้', ollama: 'error', faiss: 'not loaded' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchSessions(); check() }, [])

  const allOk = health && Object.values(health).every(v => v === 'ok' || v === 'loaded')

  return (
    <div className="app-layout">
      <Sidebar
        sessions={sessions}
        activeSession={activeSession}
        onSelectSession={(s) => { loadSession(s); navigate('/chat') }}
        onNewChat={() => { newSession(); navigate('/chat') }}
        loadingSessions={loadingSessions}
      />

      <main className={styles.main}>
        <header className={styles.header}>
          <button className="btn btn-ghost" style={{ gap: 6, padding: '8px 14px' }} onClick={() => navigate('/chat')}>
            <ArrowLeft size={16} /> กลับ
          </button>
          <h2 className={styles.title}>สถานะระบบ</h2>
          <button className="btn btn-ghost" style={{ gap: 6, padding: '8px 14px', marginLeft: 'auto' }} onClick={check} disabled={loading}>
            <RefreshCw size={15} className={loading ? styles.spin : ''} />
            รีเฟรช
          </button>
        </header>

        <div className={styles.content}>
          {/* Overall status banner */}
          <div className={`${styles.banner} ${allOk ? styles.bannerOk : styles.bannerError}`}>
            <Activity size={22} />
            <div>
              <h3>{loading ? 'กำลังตรวจสอบ...' : allOk ? 'ระบบทำงานปกติทุกส่วน' : 'พบปัญหาบางส่วน'}</h3>
              {lastChecked && (
                <p>ตรวจสอบล่าสุด: {lastChecked.toLocaleTimeString('th-TH')}</p>
              )}
            </div>
          </div>

          {/* Status cards */}
          <div className={styles.cards}>
            {loading ? (
              [...Array(3)].map((_, i) => <div key={i} className={styles.skeleton} />)
            ) : health ? (
              <>
                <StatusCard
                  icon={Database}
                  title="ฐานข้อมูล MySQL"
                  status={health.db}
                  detail={health.db === 'ok' ? 'เชื่อมต่อสำเร็จ' : health.db}
                />
                <StatusCard
                  icon={Cpu}
                  title="Ollama LLM"
                  status={health.ollama}
                  detail={health.ollama === 'ok' ? 'โมเดลพร้อมใช้งาน' : health.ollama}
                />
                <StatusCard
                  icon={Layers}
                  title="FAISS Vector Store"
                  status={health.faiss}
                  detail={health.faiss === 'loaded' ? 'โหลด Index สำเร็จ' : 'ยังไม่ได้โหลด'}
                />
              </>
            ) : null}
          </div>

          {/* Info box */}
          <div className={styles.infoBox}>
            <h4>เกี่ยวกับระบบ DrKaset</h4>
            <div className={styles.infoGrid}>
              <div className={styles.infoItem}><span>Backend</span><strong>FastAPI + SQLAlchemy</strong></div>
              <div className={styles.infoItem}><span>LLM</span><strong>Ollama (qwen2.5:7b)</strong></div>
              <div className={styles.infoItem}><span>Vector DB</span><strong>FAISS + BGE Embeddings</strong></div>
              <div className={styles.infoItem}><span>Database</span><strong>MySQL</strong></div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
