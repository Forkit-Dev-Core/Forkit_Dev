import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { CreatePassportPage } from './pages/CreatePassportPage'
import { DashboardPage } from './pages/DashboardPage'
import { EcosystemsPage } from './pages/EcosystemsPage'
import { LandingPage } from './pages/LandingPage'
import { LineagePage } from './pages/LineagePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PassportDetailPage } from './pages/PassportDetailPage'
import { PassportListPage } from './pages/PassportListPage'
import { RegistryStatsPage } from './pages/RegistryStatsPage'
import { SearchPage } from './pages/SearchPage'
import { VerifyPassportPage } from './pages/VerifyPassportPage'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LandingPage />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="ecosystems" element={<EcosystemsPage />} />
        <Route path="registry" element={<PassportListPage />} />
        <Route path="passports" element={<Navigate to="/registry" replace />} />
        <Route path="passports/create" element={<CreatePassportPage />} />
        <Route path="passports/:passportId" element={<PassportDetailPage />} />
        <Route path="create" element={<Navigate to="/passports/create" replace />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="verify" element={<VerifyPassportPage />} />
        <Route path="lineage" element={<LineagePage />} />
        <Route path="registry/stats" element={<RegistryStatsPage />} />
        <Route path="stats" element={<Navigate to="/registry/stats" replace />} />
        <Route path="home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

export default App
