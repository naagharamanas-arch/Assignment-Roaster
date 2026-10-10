import { Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import AuthCallbackPage from './pages/AuthCallbackPage'
import { HistoryPage } from './pages/HistoryPage'
import { LandingPage } from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import ProfilePage from './pages/ProfilePage'
import { PublicRoastPage } from './pages/PublicRoastPage'
import RegisterPage from './pages/RegisterPage'
import { SubmissionPage } from './pages/SubmissionPage'
import { SubmitPage } from './pages/SubmitPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/submit" element={<SubmitPage />} />
        <Route path="/submissions/:id" element={<SubmissionPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      <Route path="/r/:slug" element={<PublicRoastPage />} />
    </Routes>
  )
}
