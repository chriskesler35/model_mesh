// PM2 launcher for Next.js dev server on Windows
// Uses shell:true so .cmd scripts work correctly
const { spawn } = require('child_process')
const path = require('path')

const child = spawn('npm', ['run', 'dev'], {
  stdio: 'inherit',
  shell: true,          // required on Windows for .cmd scripts
  cwd: __dirname,
})

child.on('exit', (code) => process.exit(code ?? 0))
process.on('SIGINT',  () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
