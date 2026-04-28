import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ContentList from './screens/ContentList'
import EmailCopy from './screens/EmailCopy'
import CloneCompare from './screens/CloneCompare'
import About from './screens/About'
import { Screen } from './types'

export type ThemeMode = 'light' | 'dark' | 'system'

const THEME_KEY = 'clg-theme'

function getSystemDark() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function applyTheme(mode: ThemeMode) {
  const dark = mode === 'system' ? getSystemDark() : mode === 'dark'
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}

function loadTheme(): ThemeMode {
  const saved = localStorage.getItem(THEME_KEY) as ThemeMode | null
  return saved ?? 'system'
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('content-list')
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const t = loadTheme()
    applyTheme(t)
    return t
  })

  useEffect(() => {
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => applyTheme('system')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  const cycleTheme = () => {
    const next: ThemeMode = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light'
    setTheme(next)
    applyTheme(next)
    localStorage.setItem(THEME_KEY, next)
  }

  return (
    <div className="app-container">
      <Sidebar active={screen} onNav={setScreen} theme={theme} onCycleTheme={cycleTheme} />
      <main className="main-content">
        {screen === 'content-list'  && <ContentList />}
        {screen === 'email-copy'    && <EmailCopy />}
        {screen === 'clone-compare' && <CloneCompare />}
        {screen === 'about'         && <About />}
      </main>
    </div>
  )
}
