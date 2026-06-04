import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Leaf, MessageSquare, Plus, Activity,
  LogOut, ChevronRight, Sprout, History, X, Menu, Trash2
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import styles from './Sidebar.module.css'

export default function Sidebar({ sessions, activeSession, onSelectSession, onNewChat, onDeleteSession, loadingSessions }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navItems = [
    { icon: MessageSquare, label: 'แชท', path: '/chat' },
    { icon: Activity, label: 'สถานะระบบ', path: '/health' },
  ]

  return (
    <>
      {/* Mobile toggle */}
      <button className={styles.mobileToggle} onClick={() => setMobileOpen(!mobileOpen)}>
        {mobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {mobileOpen && <div className={styles.overlay} onClick={() => setMobileOpen(false)} />}

      <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''} ${mobileOpen ? styles.mobileOpen : ''}`}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.logo}>
            <div className={styles.logoIcon}>
              <Sprout size={22} />
            </div>
            {!collapsed && <span className={styles.logoText}>DrKaset</span>}
          </div>
          <button className={styles.collapseBtn} onClick={() => setCollapsed(!collapsed)}>
            <ChevronRight size={16} style={{ transform: collapsed ? 'rotate(0deg)' : 'rotate(180deg)', transition: 'transform .2s' }} />
          </button>
        </div>

        {/* Nav */}
        <nav className={styles.nav}>
          {navItems.map(({ icon: Icon, label, path }) => (
            <button
              key={path}
              className={`${styles.navItem} ${window.location.pathname === path ? styles.active : ''}`}
              onClick={() => { navigate(path); setMobileOpen(false) }}
              title={collapsed ? label : ''}
            >
              <Icon size={18} />
              {!collapsed && <span>{label}</span>}
            </button>
          ))}
        </nav>

        {/* Sessions */}
        {!collapsed && (
          <div className={styles.sessions}>
            <div className={styles.sessionsHeader}>
              <History size={14} />
              <span>ประวัติการสนทนา</span>
              <button className={styles.newChatBtn} onClick={onNewChat} title="แชทใหม่">
                <Plus size={14} />
              </button>
            </div>
            <div className={styles.sessionsList}>
              {loadingSessions ? (
                <div className={styles.loading}>
                  {[...Array(3)].map((_, i) => <div key={i} className={styles.skeleton} />)}
                </div>
              ) : sessions.length === 0 ? (
                <p className={styles.empty}>ยังไม่มีประวัติการสนทนา</p>
              ) : (
                sessions.map((s) => (
                  <div
                    key={s.id}
                    className={`${styles.sessionRow} ${activeSession?.id === s.id ? styles.activeSession : ''}`}
                  >
                    <button
                      className={styles.sessionItem}
                      onClick={() => { onSelectSession(s); setMobileOpen(false) }}
                    >
                      <Leaf size={13} />
                      <span>{s.title || `Session #${s.id}`}</span>
                    </button>
                    <button
                      className={styles.deleteSessionBtn}
                      title="ลบแชต"
                      onClick={(event) => {
                        event.stopPropagation()
                        if (window.confirm('ลบแชตนี้ใช่ไหม?')) onDeleteSession?.(s)
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className={styles.footer}>
          {!collapsed && (
            <div className={styles.userInfo}>
              <div className={styles.avatar}>{user?.email?.[0]?.toUpperCase() || 'U'}</div>
              <span className={styles.email}>{user?.email}</span>
            </div>
          )}
          <button className={styles.logoutBtn} onClick={handleLogout} title="ออกจากระบบ">
            <LogOut size={16} />
            {!collapsed && <span>ออกจากระบบ</span>}
          </button>
        </div>
      </aside>
    </>
  )
}
