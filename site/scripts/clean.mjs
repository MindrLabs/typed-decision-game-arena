// Remove the previous build from ../webui while keeping ../webui/data (written by `arena export`).
import { rmSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const webui = fileURLToPath(new URL('../../webui/', import.meta.url))
for (const entry of ['index.html', 'assets']) {
  rmSync(join(webui, entry), { recursive: true, force: true })
}
