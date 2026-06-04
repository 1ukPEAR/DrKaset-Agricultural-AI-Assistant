import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/auth/ProtectedRoute'
import AuthPage from './pages/AuthPage'
import ChatPage from './pages/ChatPage'
import HealthPage from './pages/HealthPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<AuthPage />} />
          <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
          <Route path="/health" element={<ProtectedRoute><HealthPage /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 3000,
          style: {
            fontFamily: "'Sarabun', sans-serif",
            fontSize: '14px',
            borderRadius: '12px',
            boxShadow: '0 8px 24px rgba(5,46,22,.15)',
          },
          success: {
            style: { background: '#f0fdf4', color: '#15803d', border: '1.5px solid #bbf7d0' },
            iconTheme: { primary: '#16a34a', secondary: '#fff' },
          },
          error: {
            style: { background: '#fef2f2', color: '#dc2626', border: '1.5px solid #fecaca' },
          },
        }}
      />
    </AuthProvider>
  )
}
