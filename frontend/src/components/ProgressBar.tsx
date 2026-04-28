interface ProgressBarProps {
  percent: number
  animated?: boolean
}

export default function ProgressBar({ percent, animated }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, percent * 100))
  return (
    <div className="progress-bar">
      <div
        className={`progress-fill${animated ? ' animated' : ''}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}
