import { useId } from 'react'
import { PickFolder } from '../../wailsjs/go/main/App'

interface FolderPickerProps {
  label: string
  value: string
  onChange: (path: string) => void
  placeholder?: string
  disabled?: boolean
}

export default function FolderPicker({ label, value, onChange, placeholder, disabled }: FolderPickerProps) {
  const inputId = useId()
  const browse = async () => {
    try {
      const path = await PickFolder(label)
      if (path) onChange(path)
    } catch {
      // user cancelled dialog
    }
  }

  return (
    <div className="field">
      <label className="field-label" htmlFor={inputId}>{label}</label>
      <div className="field-row">
        <input
          id={inputId}
          className="text-input monospace"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder ?? 'Choose a folder…'}
          disabled={disabled}
        />
        <button className="btn btn-outline btn-sm" onClick={browse} disabled={disabled}>
          Browse
        </button>
      </div>
    </div>
  )
}
