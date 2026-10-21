export type RecordingFlag = boolean

declare module 'claude-code' {
  interface PluginState {
    'recording-mode': { isOn: RecordingFlag }
  }
}
