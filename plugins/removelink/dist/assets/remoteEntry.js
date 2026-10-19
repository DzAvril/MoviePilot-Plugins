let shared = {}, runtime, views;
export function init(scope) {shared = scope;}
export async function get(name) {
  if (name !== './Config') throw new Error('Unknown RemoveLink view');
  if (!runtime) {
    const providers = shared.vue || globalThis.__federation_shared__?.default?.vue;
    const provider = providers && Object.values(providers)[0];
    if (!provider) throw new Error('MoviePilot Vue runtime unavailable');
    runtime = Promise.resolve(provider.get()).then(factory => factory());
  }
  const href = new URL('./style.css?v=2.18', import.meta.url).href;
  if (!Array.from(document.querySelectorAll('link[rel="stylesheet"]')).some(link => link.href === href)) {
    const link = document.createElement('link'); link.rel = 'stylesheet'; link.href = href; document.head.appendChild(link);
  }
  views ||= import(new URL('./view.js?v=2.18', import.meta.url).href);
  const [Vue, module] = await Promise.all([runtime, views]);
  return () => module.createConfig(Vue);
}
