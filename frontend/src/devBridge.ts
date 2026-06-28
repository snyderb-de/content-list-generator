type DevCallback = (...args: any[]) => void

const listeners = new Map<string, Set<DevCallback>>()

function emit(eventName: string, ...args: any[]) {
  listeners.get(eventName)?.forEach(callback => callback(...args))
}

function on(eventName: string, callback: DevCallback, maxCallbacks = -1) {
  const eventListeners = listeners.get(eventName) ?? new Set<DevCallback>()
  listeners.set(eventName, eventListeners)

  let callCount = 0
  const wrapped = (...args: any[]) => {
    callback(...args)
    callCount += 1
    if (maxCallbacks > 0 && callCount >= maxCallbacks) {
      eventListeners.delete(wrapped)
    }
  }

  eventListeners.add(wrapped)
  return () => eventListeners.delete(wrapped)
}

function off(eventName: string, ...additionalEventNames: string[]) {
  ;[eventName, ...additionalEventNames].forEach(name => listeners.delete(name))
}

function installDevBridge() {
  const globalWindow = window as any
  if (globalWindow.go?.main?.App || globalWindow.runtime) return

  const appApi = {
    CancelCloneCompare: async () => {},
    CancelEmailCopy: async () => {},
    CancelScan: async () => {},
    CheckForUpdates: async () => ({ supported: false, readyToRestart: false, updateAvailable: false, message: 'Updates are disabled in browser dev mode.' }),
    CheckOutputExists: async () => false,
    GetAppVersion: async () => 'dev',
    GetScanDefaults: async () => ({ releaseFolder: 'X:\\Apps' }),
    OpenPath: async () => {},
    PickFolder: async () => '',
    ResumeCloneWithDriveB: async () => {},
    RestartToApplyUpdate: async () => {},
    SaveReleaseFolder: async () => {},
    SaveSettings: async () => {},
    StartCloneCompare: async () => {},
    StartEmailCopy: async () => {},
    StartScan: async () => {},
    ValidateScanPaths: async () => '',
  }

  const runtimeApi: Record<string, any> = {
    BrowserOpenURL: (url: string) => window.open(url, '_blank', 'noopener,noreferrer'),
    EventsEmit: emit,
    EventsOff: off,
    EventsOffAll: () => listeners.clear(),
    EventsOnMultiple: on,
  }

  globalWindow.go = { main: { App: appApi } }
  globalWindow.runtime = new Proxy(runtimeApi, {
    get(target, prop) {
      const key = String(prop)
      return key in target ? target[key] : () => undefined
    },
  })
}

if (import.meta.env.DEV) {
  installDevBridge()
}
