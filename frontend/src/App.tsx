import { useEffect, useState } from 'react'
import { LuBookOpen, LuShieldCheck, LuUsers } from 'react-icons/lu'
import { SiBluesky, SiDiscord, SiGithub, SiReact, SiVite, SiX } from 'react-icons/si'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function App() {
  const [count, setCount] = useState(0)
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking')

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => (res.ok ? setApiStatus('online') : setApiStatus('offline')))
      .catch(() => setApiStatus('offline'))
  }, [])

  return (
    <>
      <section id="center">
        <div className="hero" aria-hidden="true">
          <LuShieldCheck className="hero-main" />
          <SiReact className="hero-badge react" />
          <SiVite className="hero-badge vite" />
        </div>
        <div>
          <h1>Get started</h1>
          <p>
            Edit <code>src/App.tsx</code> and save to test <code>HMR</code>
          </p>
          <p>
            Backend API: <strong className={`status status-${apiStatus}`}>{apiStatus}</strong>
          </p>
        </div>
        <button
          type="button"
          className="counter"
          onClick={() => setCount((count) => count + 1)}
        >
          Count is {count}
        </button>
      </section>

      <div className="ticks"></div>

      <section id="next-steps">
        <div id="docs">
          <LuBookOpen className="icon" aria-hidden="true" />
          <h2>Documentation</h2>
          <p>Your questions, answered</p>
          <ul>
            <li>
              <a href="https://vite.dev/" target="_blank" rel="noreferrer">
                <SiVite className="button-icon" aria-hidden="true" />
                Explore Vite
              </a>
            </li>
            <li>
              <a href="https://react.dev/" target="_blank" rel="noreferrer">
                <SiReact className="button-icon" aria-hidden="true" />
                Learn more
              </a>
            </li>
          </ul>
        </div>
        <div id="social">
          <LuUsers className="icon" aria-hidden="true" />
          <h2>Connect with us</h2>
          <p>Join the Vite community</p>
          <ul>
            <li>
              <a href="https://github.com/vitejs/vite" target="_blank" rel="noreferrer">
                <SiGithub className="button-icon" aria-hidden="true" />
                GitHub
              </a>
            </li>
            <li>
              <a href="https://chat.vite.dev/" target="_blank" rel="noreferrer">
                <SiDiscord className="button-icon" aria-hidden="true" />
                Discord
              </a>
            </li>
            <li>
              <a href="https://x.com/vite_js" target="_blank" rel="noreferrer">
                <SiX className="button-icon" aria-hidden="true" />
                X.com
              </a>
            </li>
            <li>
              <a href="https://bsky.app/profile/vite.dev" target="_blank" rel="noreferrer">
                <SiBluesky className="button-icon" aria-hidden="true" />
                Bluesky
              </a>
            </li>
          </ul>
        </div>
      </section>

      <div className="ticks"></div>
      <section id="spacer"></section>
    </>
  )
}

export default App
