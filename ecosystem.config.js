module.exports = {
  apps: [
    {
      name: 'devforgeai-backend',
      // Use venv python if it exists, otherwise fall back to system python
      script: (() => {
        const fs = require('fs')
        const path = require('path')
        const venvWin   = path.join(__dirname, 'backend', 'venv', 'Scripts', 'python.exe')
        const venvUnix  = path.join(__dirname, 'backend', 'venv', 'bin', 'python')
        if (fs.existsSync(venvWin))  return venvWin
        if (fs.existsSync(venvUnix)) return venvUnix
        return process.platform === 'win32' ? 'python' : 'python3'
      })(),
      args: '-m uvicorn app.main:app --host 0.0.0.0 --port 19000 --reload',
      cwd: './backend',
      interpreter: 'none',
      watch: false,
      autorestart: true,
      restart_delay: 2000,
      max_restarts: 10,
      windowsHide: true,
      env: {
        PYTHONUNBUFFERED: '1',
      },
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      error_file: '../logs/backend-error.log',
      out_file: '../logs/backend-out.log',
      merge_logs: true,
    },
    {
      name: 'devforgeai-frontend',
      script: 'node_modules/next/dist/bin/next',
      args: 'dev -p 3001',
      cwd: './frontend',
      interpreter: 'node',
      watch: false,
      autorestart: true,
      restart_delay: 2000,
      max_restarts: 10,
      windowsHide: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      error_file: '../logs/frontend-error.log',
      out_file: '../logs/frontend-out.log',
      merge_logs: true,
    },
  ],
}
