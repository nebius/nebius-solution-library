import { NebiusLogoBox } from './NebiusLogo';

interface HeaderProps {
  isConnected: boolean;
}

export function Header({ isConnected }: HeaderProps) {
  return (
    <header className="app-header">
      <div className="app-logo">
        <NebiusLogoBox />
        <span className="app-logo-text">Drug Discovery Demo</span>
      </div>

      <div className="status-indicator">
        <span
          className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}
        />
        <span>{isConnected ? 'Connected' : 'Not Connected'}</span>
      </div>
    </header>
  );
}
