interface PlaceholderStepProps {
  title: string;
  subtitle: string;
  description: string;
  onContinue?: () => void;
  onBack?: () => void;
  continueLabel?: string;
  isLast?: boolean;
}

export function PlaceholderStep({
  title,
  subtitle,
  description,
  onContinue,
  onBack,
  continueLabel = 'Continue',
  isLast = false,
}: PlaceholderStepProps) {
  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">{title}</h1>
          <p className="content-subtitle">{subtitle}</p>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Coming Soon</h3>
          <span className="card-badge">In Development</span>
        </div>
        <p style={{ color: 'var(--color-gray-500)' }}>{description}</p>
      </div>

      <div className="step-actions">
        {onBack && (
          <button className="btn btn-ghost" onClick={onBack}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M12.5 15l-5-5 5-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Back
          </button>
        )}
        {onContinue && !isLast && (
          <button className="btn btn-secondary btn-lg" onClick={onContinue}>
            {continueLabel}
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M7.5 15l5-5-5-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
        {isLast && (
          <button className="btn btn-secondary btn-lg" disabled>
            Workflow Complete
          </button>
        )}
      </div>
    </div>
  );
}
