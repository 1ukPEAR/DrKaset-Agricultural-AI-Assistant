import { useState, useRef, useEffect } from 'react'
import { Send, Square } from 'lucide-react'
import styles from './ChatInput.module.css'

const SUGGESTIONS = [
  'ขอราคาข้อมูลย้อนหลังของข้าวโพดหน่อย',
  'ต้นทุนต่อไร่ของมังคุดประมาณเท่าไหร่',
  'ดินทรายฝนน้อย ระหว่างมันสำปะหลังกับข้าวโพดควรปลูกอะไร',
  'สวนมะพร้าวลูกร่วงก่อนแก่ เกิดจากขาดน้ำหรือแมลงลง',
  'ที่ดินดินเหนียวควรปลูกอ้อยโรงงานได้ผลดีไหม',
]

export default function ChatInput({ onSend, streaming, onStop, hasMessages }) {
  const [text, setText] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + 'px'
    }
  }, [text])

  const handleSubmit = () => {
    if (!text.trim() || streaming) return
    onSend(text.trim())
    setText('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className={styles.wrapper}>
      {!hasMessages && (
        <div className={styles.suggestions} aria-label="คำถามแนะนำ">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              className={styles.suggestion}
              onClick={() => onSend(suggestion)}
              type="button"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <div className={styles.inputBox}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKey}
          placeholder="ถามเรื่องราคา ต้นทุน โรคพืช ดิน น้ำ หรือแผนเพาะปลูก..."
          rows={1}
          disabled={streaming}
        />
        <div className={styles.actions}>
          {streaming ? (
            <button
              className={`${styles.actionBtn} ${styles.stopBtn}`}
              onClick={onStop}
              type="button"
              aria-label="หยุดตอบ"
              title="หยุดตอบ"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              className={`${styles.actionBtn} ${styles.sendBtn}`}
              onClick={handleSubmit}
              disabled={!text.trim()}
              type="button"
              aria-label="ส่งข้อความ"
              title="ส่งข้อความ"
            >
              <Send size={16} />
            </button>
          )}
        </div>
      </div>
      <p className={styles.hint}>
        DrKaset ใช้ AI ช่วยตอบคำถามเกษตร ข้อมูลราคาและอากาศอาจเปลี่ยนแปลงได้
      </p>
    </div>
  )
}
