let shared = {}, runtime, views;
export function init(scope) { shared = scope; }
export async function get(name) {
  if (!['./Page', './Config'].includes(name)) throw new Error('Unknown CleanInvalidSeed view');
  if (!runtime) {
    const providers = shared.vue || globalThis.__federation_shared__?.default?.vue;
    const provider = providers && Object.values(providers)[0];
    if (!provider) throw new Error('MoviePilot Vue runtime unavailable');
    runtime = Promise.resolve(provider.get()).then(factory => factory());
  }
  const href = new URL('./style.css?v=3.0.4', import.meta.url).href;
  if (!Array.from(document.querySelectorAll('link[rel="stylesheet"]')).some(link => link.href === href)) {
    const link = document.createElement('link'); link.rel = 'stylesheet'; link.href = href; document.head.appendChild(link);
  }
  views ||= import(new URL('./view.js?v=3.0.4', import.meta.url).href);
  const [Vue, module] = await Promise.all([runtime, views]);
  const component = name === './Page' ? module.createPage(Vue) : module.createConfig(Vue);
  return () => component;
}
