import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { spawn } from 'child_process'
import path from 'path'

// Auto-start backend when Vite dev server starts
function backendPlugin() {
  let backendProcess = null

  return {
    name: 'guardian-backend',
    configureServer(server) {
      const root = path.resolve(__dirname, '..')

      console.log('[GuardianTwin] Starting backend...')
      backendProcess = spawn(
        'python',
        ['backend/api/local_server.py'],
        {
          cwd: root,
          stdio: 'inherit',   // pipe backend logs to same terminal
          shell: true,
        }
      )

      backendProcess.on('error', err => {
        console.error('[GuardianTwin] Backend failed to start:', err.message)
      })

      // Kill backend when Vite shuts down
      const cleanup = () => {
        if (backendProcess) {
          console.log('[GuardianTwin] Stopping backend...')
          backendProcess.kill()
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
  server: { port: 5173 },
})
