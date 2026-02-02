import nebiusLogo from '../assets/nebius-logo.svg';

interface NebiusLogoProps {
  className?: string;
  height?: number;
}

export function NebiusLogo({ className = '', height = 32 }: NebiusLogoProps) {
  return (
    <img
      src={nebiusLogo}
      alt="Nebius"
      className={className}
      height={height}
    />
  );
}

// Alias for backwards compatibility
export function NebiusLogoBox({ className = '' }: { className?: string }) {
  return <NebiusLogo className={className} />;
}
