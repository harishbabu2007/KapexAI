type TabBlockedOverlayProps = {
  onClaim: () => void
}

/**
 * Full-screen blocker shown when the same account is already open in another
 * tab. Keeps the chat from being driven from two tabs at once.
 */
export function TabBlockedOverlay({ onClaim }: TabBlockedOverlayProps) {
  return (
    <div className="tab-blocked-overlay">
      <div className="tab-blocked-card">
        <div className="tab-blocked-icon" aria-hidden="true">
          K
        </div>
        <h2 className="tab-blocked-title">Already open in another tab</h2>
        <p className="tab-blocked-text">
          KapexAI keeps you to a single active tab so your chat doesn’t get
          mixed up. Close this tab — or take over the session here.
        </p>
        <button type="button" className="send-btn tab-blocked-cta" onClick={onClaim}>
          Use this tab instead
        </button>
      </div>
    </div>
  )
}
