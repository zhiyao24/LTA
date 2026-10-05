import type { ContentState } from '../types/api'

interface HeaderProps {
  backendState: ContentState
}

export function Header({ backendState }: HeaderProps) {
  const connected = backendState === 'ready'

  return (
    <header className="app-header">
      <div className="header-inner">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">JN</div>
          <div className="brand-copy">
            <p>Local operations</p>
            <h1>Jetson Nano control</h1>
          </div>
        </div>

        <div className="header-tools">
          <span className={`demo-badge ${connected ? '' : 'demo-badge--offline'}`}>
            {connected ? 'FastAPI connected' : 'Backend unavailable'}
          </span>
          <span className="header-note">HTTP polling · local only</span>
        </div>
      </div>
    </header>
  )
}
