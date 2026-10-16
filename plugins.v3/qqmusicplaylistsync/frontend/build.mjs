/** Reproduce the plain Vue render-function ESM assets without bundling host Vue. */
import {readFile, writeFile, mkdir, access} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const source = new URL('./', import.meta.url);
const target = new URL('../dist/assets/', import.meta.url);
await mkdir(target, {recursive: true});
for (const name of ['view.js', 'remoteEntry.js', 'style.css']) {
  const path = new URL(name, source);
  if (name.endsWith('.js')) {
    const check = spawnSync(process.execPath, ['--check', fileURLToPath(path)], {stdio: 'inherit'});
    if (check.status !== 0) process.exit(check.status || 1);
  }
  await writeFile(new URL(name, target), await readFile(path));
}
await access(new URL('MusicPlaylistSync-1.7.1.png', target));
console.log('Vue ESM assets built; shared Vue stays supplied by MoviePilot.');
