// PM2 launcher for Next.js dev server on Windows
// Uses execFile with the .cmd path directly — no shell window spawned
const { execFile } = require('child_process')
const fs = require('fs')
const path = require('path')

const nextCmd = path.join(__dirname, 'node_modules', '.bin', 'next.cmd')
const nextCache = path.join(__dirname, '.next', 'cache')

try {
  fs.rmSync(nextCache, { recursive: true, force: true })
} catch {}

const child = execFile(nextCmd, ['dev', '-p', '3001'], {
  cwd: __dirname,
  stdio: 'inherit',
  windowsHide: true,   // suppress any cmd windows
})

child.stdout?.pipe(process.stdout)
child.stderr?.pipe(process.stderr)
child.on('exit', (code) => process.exit(code ?? 0))
process.on('SIGINT',  () => child.kill())
process.on('SIGTERM', () => child.kill())
