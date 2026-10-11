import React from 'react'

export interface RobotMascotProps {
  isLoading?: boolean
  isSpeaking?: boolean
  className?: string
  size?: number
}

export const RobotMascot: React.FC<RobotMascotProps> = ({
  isLoading = false,
  isSpeaking = false,
  className = '',
  size = 48,
}) => {
  const showThinking = isLoading && !isSpeaking
  return (
    <div
      className={`mascot-animated inline-flex items-center justify-center cursor-pointer select-none ${className}`}
      style={{
        animation: showThinking
          ? 'mascot-fast-bob 0.85s ease-in-out infinite'
          : isSpeaking
          ? 'mascot-bob 1.5s ease-in-out infinite'
          : 'mascot-bob 3s ease-in-out infinite',
      }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        className="overflow-visible drop-shadow-md"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Antenna Stem */}
        <line x1="32" y1="14" x2="32" y2="6" stroke="#FAF5FF" strokeWidth="2.5" strokeLinecap="round" />
        {/* Pulsing Antenna Ball */}
        <circle
          cx="32"
          cy="5"
          r={showThinking ? '4' : '3.5'}
          fill={showThinking ? '#FDE047' : isSpeaking ? '#C084FC' : '#38BDF8'}
          className="robot-antenna"
        />
        <circle cx="32" cy="5" r="2" fill="#FAF5FF" />

        {/* Ears */}
        <rect x="12" y="22" width="4" height="8" rx="2" fill="#C084FC" />
        <rect x="48" y="22" width="4" height="8" rx="2" fill="#C084FC" />

        {/* Head */}
        <rect x="16" y="14" width="32" height="24" rx="8" fill="#FFFFFF" />
        {/* Head Screen / Visor */}
        <rect x="20" y="18" width="24" height="14" rx="5" fill="#090D16" />

        {/* Blinking Eyes */}
        <circle
          cx="27"
          cy="24"
          r="2.5"
          fill="#38BDF8"
          className="robot-eye"
        />
        <circle
          cx="37"
          cy="24"
          r="2.5"
          fill={showThinking ? '#D946EF' : '#38BDF8'}
          className="robot-eye"
        />

        {/* Mouth */}
        {showThinking || isSpeaking ? (
          <path d="M28 29 Q32 27 36 29" stroke="#38BDF8" strokeWidth="1.5" strokeLinecap="round" />
        ) : (
          <path d="M28 27 Q32 30 36 27" stroke="#38BDF8" strokeWidth="1.5" strokeLinecap="round" />
        )}

        {/* Neck */}
        <rect x="29" y="38" width="6" height="3" rx="1.5" fill="#C084FC" />

        {/* Body */}
        <rect x="18" y="41" width="28" height="16" rx="6" fill="#F1F1F7" />
        {/* Chest Panel */}
        <rect x="23" y="44" width="18" height="9" rx="3" fill="#090D16" />
        <circle cx="28" cy="48.5" r="1.5" fill="#D946EF" />
        <circle cx="32" cy="48.5" r="1.5" fill="#8B5CF6" />
        <circle cx="36" cy="48.5" r="1.5" fill="#22C55E" />
      </svg>
    </div>
  )
}
