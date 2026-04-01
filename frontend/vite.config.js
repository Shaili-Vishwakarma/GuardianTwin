import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { spawn } from 'child_process'
import path from 'path'
import fs from 'fs'

// Find the correct Python executable
function findPython() {
  const candidates = [
    'C:\\Users\\hp\\AppData\\Local\\Programs\\Python\\Python311\\python.exe',
    process.env.PYTHON || '',
    'python3',
    'python',
  ]
  for (const p of candidates) {
    if (!p) continue
    if (p.includes('\\') || p.includes('/')) {
      if (fs.existsSync(p)) return p
    } else {
      return p  // system PATH entry — try it
    }
  }
  return 'python'
}

function backendPlugin() {
  let backendProcess = null

  return {
    name: 'guardian-backend',
    configureServer() {
      const root = path.resolve(__dirname, '..')
      const python = findPython()
      const script = path.join(root, 'backend', 'api', 'local_server.py')

      console.log(`\n[GuardianTwin] Starting backend with: ${python}`)
      console.log(`[GuardianTwin] Script: ${script}\n`)

      backendProcess = spawn(python, [script], {
        cwd: root,
        stdio: 'inherit',
        shell: false,
        env: { ...process.env },
      })

      backendProcess.on('error', err => {
        console.error(`[GuardianTwin] Backend failed to start: ${err.message}`)
        console.error('[GuardianTwin] Run manually: python backend/api/local_server.py')
      })

      backendProcess.on('exit', code => {
        if (code !== 0 && code !== null) {
          console.error(`[GuardianTwin] Backend exited with code ${code}`)
        }
      })

      const cleanup = () => {
        if (backendProcess && !backendProcess.killed) {
          console.log('\n[GuardianTwin] Stopping backend...')
          backendProcess.kill('SIGTERM')
        }
      }
      process.on('exit', cleanup)
      process.on('SIGINT', cleanup)
      process.on('SIGTERM', cleanup)
    },
  }
}

export default defineConfig({
  plugins: [react(), backendPlugin()],
  server: {
    port: 5173,
    proxy: {
      '/query':           'http://localhost:8000',
      '/scenario':        'http://localhost:8000',
      '/missions':        'http://localhost:8000',
      '/trigger_mission': 'http://localhost:8000',
      '/mission_status':  'http://localhost:8000',
      '/start_simulation':'http://localhost:8000',
      '/reset':           'http://localhost:8000',
      '/state':           'http://localhost:8000',
      '/health':          'http://localhost:8000',
      '/logs':            { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
