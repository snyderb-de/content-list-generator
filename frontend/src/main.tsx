import React from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import App from './App'

const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')

const container = document.getElementById('root')!
createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
