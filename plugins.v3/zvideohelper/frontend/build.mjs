import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const source = new URL('./', import.meta.url), target = new URL('../dist/assets/', import.meta.url);
await mkdir(target, {recursive: true});
for (const name of ['view.js', 'remoteEntry.js', 'style.css']) {
  if (name.endsWith('.js')) {
    const check = spawnSync(process.execPath, ['--check', fileURLToPath(new URL(name, source))], {stdio: 'inherit'});
    if (check.status) process.exit(check.status);
  }
  await writeFile(new URL(name, target), await readFile(new URL(name, source)));
}
