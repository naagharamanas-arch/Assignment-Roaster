interface ScoreRingProps {
  score: number
  size?: number
}

// Theme tokens exposed by Chakra as CSS variables (see src/theme.ts)
const GOLD = 'var(--chakra-colors-gold-500)'
const INK_TRACK = 'var(--chakra-colors-ink-700)'

export function ScoreRing({ score, size = 140 }: ScoreRingProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)))
  const stroke = 12
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - clamped / 100)
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`Score ${clamped} out of 100`}
    >
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={INK_TRACK} strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={GOLD}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" fontSize={size / 3} fontWeight="700" fill="currentColor">
        {clamped}
      </text>
    </svg>
  )
}
