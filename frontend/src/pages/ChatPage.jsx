import { useEffect, useRef } from 'react'
import { Bug, Calculator, CloudSun, Sprout, TrendingUp } from 'lucide-react'
import { useChat } from '../hooks/useChat'
import Sidebar from '../components/layout/Sidebar'
import ChatMessage from '../components/chat/ChatMessage'
import ChatInput from '../components/chat/ChatInput'
import WeatherWidget from '../components/weather/WeatherWidget'
import MarketPriceWidget from '../components/market/MarketPriceWidget'
import styles from './ChatPage.module.css'

const FEATURE_CARDS = [
  {
    icon: TrendingUp,
    title: 'เช็กราคาและแนวโน้ม',
    description: 'ถามราคาย้อนหลังหรือราคาอ้างอิงล่าสุดของพืชเศรษฐกิจ พร้อมดูแนวโน้มแบบใช้งานจริง',
    prompt: 'ขอราคาข้อมูลย้อนหลังของข้าวโพดหน่อย',
  },
  {
    icon: Calculator,
    title: 'คำนวณต้นทุนปลูก',
    description: 'ใช้คำถามแนวต้นทุนต่อไร่ รายได้ และกำไรคร่าว ๆ จากชุดข้อมูลที่มีในระบบ',
    prompt: 'ต้นทุนต่อไร่ของมังคุดประมาณเท่าไหร่',
  },
  {
    icon: Bug,
    title: 'โรคและอาการพืช',
    description: 'ลองถามจากอาการจริง เช่น ใบเหลือง ลูกร่วง หรือแมลงลง เพื่อดูว่าระบบวิเคราะห์ได้แค่ไหน',
    prompt: 'สวนมะพร้าวลูกร่วงก่อนแก่ เกิดจากขาดน้ำหรือแมลงลงครับ ขอวิธีบำรุงเบื้องต้นด้วย',
  },
  {
    icon: CloudSun,
    title: 'เทียบพืชตามสภาพแปลง',
    description: 'เหมาะกับคำถามแนวเปรียบเทียบพืชจากดิน ฝน และความเสี่ยง เพื่อใช้ตัดสินใจก่อนปลูก',
    prompt: 'ดินทรายฝนน้อย ระหว่างมันสำปะหลังกับข้าวโพดควรปลูกอะไร',
  },
]

function WelcomeScreen({ onPrompt }) {
  return (
    <div className={styles.welcome}>
      <div className={styles.welcomeIcon}>
        <Sprout size={44} />
      </div>
      <h1 className={styles.welcomeTitle}>สวัสดีครับ เกษตรกรคนเก่ง</h1>
      <p className={styles.welcomeSubtitle}>
        DrKaset ช่วยตอบคำถามเกษตรจากข้อมูลราคา สภาพอากาศ ต้นทุน
        และองค์ความรู้ภาคสนามในที่เดียว
      </p>
      <div className={styles.featureCards}>
        {FEATURE_CARDS.map(({ icon: Icon, title, description, prompt }) => (
          <button
            type="button"
            className={styles.featureCard}
            key={title}
            onClick={() => onPrompt(prompt)}
          >
            <span className={styles.featureIcon}>
              <Icon size={20} />
            </span>
            <span className={styles.featureTitle}>{title}</span>
            <span className={styles.featureText}>{description}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const {
    sessions, activeSession, messages, streaming, loadingSessions,
    fetchSessions, loadSession, newSession, deleteSession, sendMessage, stopStream,
  } = useChat()

  const bottomRef = useRef(null)

  useEffect(() => {
    fetchSessions()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="app-layout">
      <Sidebar
        sessions={sessions}
        activeSession={activeSession}
        onSelectSession={loadSession}
        onNewChat={newSession}
        onDeleteSession={deleteSession}
        loadingSessions={loadingSessions}
      />

      <main className={styles.main}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <Sprout size={18} className={styles.headerIcon} />
            <div>
              <h2 className={styles.headerTitle}>
                {activeSession ? activeSession.title : 'แชทใหม่'}
              </h2>
              {activeSession && (
                <p className={styles.headerSub}>Session #{activeSession.id}</p>
              )}
            </div>
          </div>
          {streaming && (
            <div className={styles.streamingBadge}>
              <span className={styles.dot} />
              กำลังตอบ...
            </div>
          )}
        </header>

        <div className={styles.content}>
          <div className={styles.messages}>
            {messages.length === 0 ? (
              <WelcomeScreen onPrompt={sendMessage} />
            ) : (
              messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))
            )}
            <div ref={bottomRef} />
          </div>

          <aside className={styles.weatherPanel}>
            <WeatherWidget />
            <MarketPriceWidget />
          </aside>
        </div>

        <ChatInput
          onSend={sendMessage}
          streaming={streaming}
          onStop={stopStream}
          hasMessages={messages.length > 0}
        />
      </main>
    </div>
  )
}
