import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './styles/global.css'
import './styles/theme-orchid.css';
// PWA service worker registration (only active when vite-plugin-pwa is enabled)
// import { registerSW } from 'virtual:pwa-register';
// registerSW({ immediate: true });
ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
