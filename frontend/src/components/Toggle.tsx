interface ToggleProps {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
  indent?: boolean
}

export default function Toggle({ label, checked, onChange, disabled, indent }: ToggleProps) {
  return (
    <div className={`toggle-row${indent ? ' indented' : ''}`}>
      <span className={`toggle-label${disabled ? ' dimmed' : ''}`}>{label}</span>
      <label className="toggle">
        <input
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          disabled={disabled}
        />
        <span className="toggle-track" />
        <span className="toggle-thumb" />
      </label>
    </div>
  )
}
