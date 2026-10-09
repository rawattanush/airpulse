import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import '@fontsource-variable/archivo'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './styles/base.css'
import './styles/landing.css'
import './styles/market.css'
import './styles/intelligence.css'
import './styles/operations.css'
import './styles/research.css'
import Shell from './components/Shell.jsx'
import { Loading } from './components/bits.jsx'
import Landing from './pages/Landing.jsx'
import Overview from './pages/Overview.jsx'

// Each destination is its own chunk: a visitor to the landing page downloads only the landing page.
const Market = lazy(() => import('./pages/Market.jsx'))
const Forecast = lazy(() => import('./pages/Forecast.jsx'))
const WeeklyFuel = lazy(() => import('./pages/WeeklyFuel.jsx'))
const NewsOutlook = lazy(() => import('./pages/NewsOutlook.jsx'))
const Trends = lazy(() => import('./pages/Trends.jsx'))
const History = lazy(() => import('./pages/History.jsx'))
const FuelPrices = lazy(() => import('./pages/FuelPrices.jsx'))
const AirTraffic = lazy(() => import('./pages/AirTraffic.jsx'))
const RoutePage = lazy(() => import('./pages/RoutePage.jsx'))
const RoutesPage = lazy(() => import('./pages/RoutesPage.jsx'))
const Replay = lazy(() => import('./pages/Replay.jsx'))
const Estimate = lazy(() => import('./pages/Estimate.jsx'))
const Methodology = lazy(() => import('./pages/Methodology.jsx'))
const DataPage = lazy(() => import('./pages/DataPage.jsx'))
const NotFound = lazy(() => import('./pages/NotFound.jsx'))

const page = (el) => <Suspense fallback={<Loading what="the page" />}>{el}</Suspense>

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || undefined}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route element={<Shell />}>
          <Route path="/dashboard" element={<Overview />} />
          <Route path="/market" element={page(<Market />)} />
          <Route path="/market/forecast" element={page(<Forecast />)} />
          <Route path="/market/weekly" element={page(<WeeklyFuel />)} />
          <Route path="/market/news" element={page(<NewsOutlook />)} />
          <Route path="/market/trends" element={page(<Trends />)} />
          <Route path="/market/history" element={page(<History />)} />
          <Route path="/market/fuel" element={page(<FuelPrices />)} />
          <Route path="/operations" element={page(<AirTraffic />)} />
          <Route path="/operations/route/:id" element={page(<RoutePage />)} />
          <Route path="/routes" element={page(<RoutesPage />)} />
          <Route path="/replay" element={page(<Replay />)} />
          <Route path="/estimate" element={page(<Estimate />)} />
          <Route path="/methodology" element={page(<Methodology />)} />
          <Route path="/data" element={page(<DataPage />)} />
          {/* addresses of the earlier version */}
          <Route path="/forecast" element={<Navigate to="/market/forecast" replace />} />
          <Route path="/intelligence/drivers" element={<Navigate to="/market/fuel" replace />} />
          <Route path="/history" element={<Navigate to="/market/history" replace />} />
          <Route path="/data-health" element={<Navigate to="/data" replace />} />
          <Route path="*" element={page(<NotFound />)} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
