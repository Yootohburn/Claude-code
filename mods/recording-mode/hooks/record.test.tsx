import { expect, mock, test } from 'claude-code/testing'

const MESSAGE = {
  plugin: 'recording-mode',
  component: 'AssistantMessage',
  requestId: 'm1',
  props: {
    text: 'Your GitHub email is jane.doe@example.com and the price went from $29 to $39. Key: sk-abcdefghijklmnop1234',
    isFirstOfReply: true,
  },
} as const

test('/record on masks the screen, /record off shows it again', async ($, on) => {
  mock.store(on)
  on('command.register', () => ({ value: { command: 'record' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  // What the engine would draw: the text it was handed.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    const props = e.props as { text?: string }

    return <Text>{props.text ?? ''}</Text>
  })

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  await $.command.run({ command: 'record', args: 'on' })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...MESSAGE, surface })
    const row = await ui.find({ type: 'Text', text: /email/ })
    expect(row?.text).not.toContain('jane.doe@example.com')
    expect(row?.text).not.toContain('$29')
    expect(row?.text).not.toContain('$39')
    expect(row?.text).not.toContain('sk-abcdefghijklmnop1234')
    await ui.unmount()
  }

  await $.command.run({ command: 'record', args: 'off' })
  const ui = await $.ui.mount({ ...MESSAGE, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /email/ }))?.text).toContain('jane.doe@example.com')
  await ui.unmount()
})
