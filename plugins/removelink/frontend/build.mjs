import {mkdir, readFile, writeFile} from 'node:fs/promises';
const target = new URL('../dist/assets/', import.meta.url);
await mkdir(target, {recursive: true});
for (const name of ['view.js', 'style.css', 'remoteEntry.js']) {
  await writeFile(new URL(name, target), await readFile(new URL(name, import.meta.url)));
}
console.log('RemoveLink shared Vue assets built.');
