import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sprout, User, TrendingUp, BarChart2, BookOpen, HelpCircle } from 'lucide-react'
import styles from './ChatMessage.module.css'

const INTENT_META = {
  profit: { icon: TrendingUp, label: 'กำไร/ต้นทุน', color: 'amber' },
  compare: { icon: BarChart2, label: 'เปรียบเทียบ', color: 'sky' },
  knowledge: { icon: BookOpen, label: 'ความรู้เกษตร', color: 'green' },
  fallback: { icon: HelpCircle, label: 'ทั่วไป', color: 'gray' },
}

function TypingCursor() {
  return <span className={styles.cursor}>|</span>
}

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user'
  const intent = message.intent ? INTENT_META[message.intent] : null

  return (
    <div className={`${styles.wrapper} ${isUser ? styles.userWrapper : styles.assistantWrapper} fade-in`}>
      <div className={styles.avatar}>
        {isUser ? <User size={16} /> : <Sprout size={16} />}
      </div>

      <div className={styles.bubble}>
        {intent && (
          <div className={`badge badge-${intent.color} ${styles.intentBadge}`}>
            <intent.icon size={10} />
            {intent.label}
          </div>
        )}

        {message.loading && !message.content ? (
          <div className={styles.typingIndicator}>
            <span /><span /><span />
          </div>
        ) : (
          <div className={styles.content}>
            {isUser ? (
              <p>{message.content}</p>
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => <p className={styles.mdP}>{children}</p>,
                  ul: ({ children }) => <ul className={styles.mdUl}>{children}</ul>,
                  ol: ({ children }) => <ol className={styles.mdOl}>{children}</ol>,
                  li: ({ children }) => <li className={styles.mdLi}>{children}</li>,
                  code: ({ inline, children }) =>
                    inline
                      ? <code className={styles.mdInlineCode}>{children}</code>
                      : <pre className={styles.mdPre}><code>{children}</code></pre>,
                  strong: ({ children }) => <strong className={styles.mdStrong}>{children}</strong>,
                  h1: ({ children }) => <h3 className={styles.mdH}>{children}</h3>,
                  h2: ({ children }) => <h3 className={styles.mdH}>{children}</h3>,
                  h3: ({ children }) => <h4 className={styles.mdH}>{children}</h4>,
                  blockquote: ({ children }) => <blockquote className={styles.mdQuote}>{children}</blockquote>,
                  table: ({ children }) => <div className={styles.mdTableWrap}><table className={styles.mdTable}>{children}</table></div>,
                  th: ({ children }) => <th className={styles.mdTh}>{children}</th>,
                  td: ({ children }) => <td className={styles.mdTd}>{children}</td>,
                }}
              >
                {message.content}
              </ReactMarkdown>
            )}
            {message.loading && <TypingCursor />}
          </div>
        )}

        <span className={styles.time}>
          {new Date(message.created_at).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  )
}
