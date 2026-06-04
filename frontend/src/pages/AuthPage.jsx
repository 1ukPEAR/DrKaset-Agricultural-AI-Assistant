import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sprout, Eye, EyeOff, Mail, Lock, ArrowRight, Loader } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import styles from './AuthPage.module.css'

export default function AuthPage() {
  const [mode, setMode] = useState('login') // login | register
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const { login, register } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email || !password) return
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(email, password)
        toast.success('เข้าสู่ระบบสำเร็จ!')
      } else {
        await register(email, password)
        toast.success('สมัครสมาชิกสำเร็จ!')
      }
      navigate('/chat')
    } catch (err) {
      const msg = err.response?.data?.detail || 'เกิดข้อผิดพลาด กรุณาลองใหม่'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      {/* Decorative background */}
      <div className={styles.bg}>
        <div className={styles.bgCircle1} />
        <div className={styles.bgCircle2} />
        <div className={styles.bgPattern} />
      </div>

      <div className={styles.card}>
        {/* Logo */}
        <div className={styles.logo}>
          <div className={styles.logoIcon}><Sprout size={28} /></div>
          <div>
            <h1 className={styles.logoText}>DrKaset</h1>
            <p className={styles.logoSub}>ผู้ช่วยเกษตรกรอัจฉริยะ</p>
          </div>
        </div>

        {/* Tabs */}
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${mode === 'login' ? styles.tabActive : ''}`}
            onClick={() => setMode('login')}
          >เข้าสู่ระบบ</button>
          <button
            className={`${styles.tab} ${mode === 'register' ? styles.tabActive : ''}`}
            onClick={() => setMode('register')}
          >สมัครสมาชิก</button>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          {/* Email */}
          <div className={styles.field}>
            <label className={styles.label}>อีเมล</label>
            <div className={styles.inputWrap}>
              <Mail size={16} className={styles.inputIcon} />
              <input
                type="email"
                className={`input ${styles.input}`}
                placeholder="farmer@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
          </div>

          {/* Password */}
          <div className={styles.field}>
            <label className={styles.label}>รหัสผ่าน</label>
            <div className={styles.inputWrap}>
              <Lock size={16} className={styles.inputIcon} />
              <input
                type={showPass ? 'text' : 'password'}
                className={`input ${styles.input}`}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />
              <button type="button" className={styles.eyeBtn} onClick={() => setShowPass(!showPass)}>
                {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button type="submit" className={`btn btn-primary ${styles.submitBtn}`} disabled={loading}>
            {loading ? (
              <><Loader size={16} className={styles.spin} /> กำลังดำเนินการ...</>
            ) : (
              <>{mode === 'login' ? 'เข้าสู่ระบบ' : 'สมัครสมาชิก'} <ArrowRight size={16} /></>
            )}
          </button>
        </form>

        <p className={styles.footer}>
          ระบบ AI เพื่อเกษตรกรไทย · ข้อมูลปลอดภัย ไม่แชร์ต่อ
        </p>
      </div>
    </div>
  )
}
