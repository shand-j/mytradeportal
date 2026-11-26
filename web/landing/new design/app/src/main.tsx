import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import './index.css'
import App from './App.tsx'
import { AnalyticsLifecycle } from './components/AnalyticsLifecycle'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AnalyticsLifecycle />
      <App />
    </BrowserRouter>
  </StrictMode>,
)
