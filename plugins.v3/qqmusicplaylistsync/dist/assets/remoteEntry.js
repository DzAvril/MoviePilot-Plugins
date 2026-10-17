// MoviePilot supplies its own Vue runtime through the standard federation scope.
let shared = {};
let componentModule;
let runtime;

export function init(scope) {
  shared = scope;
}

export async function get(name) {
  if (!['./Page', './Config'].includes(name)) throw new Error('Unknown QQ Music view');
  if (!runtime) {
    const providers = shared.vue || globalThis.__federation_shared__?.default?.vue;
    const provider = providers && Object.values(providers)[0];
    if (!provider) throw new Error('MoviePilot Vue runtime unavailable');
    runtime = Promise.resolve(provider.get()).then(factory => factory());
  }
  const href = new URL('./style.css?v=1.11.0', import.meta.url).href;
  if (!Array.from(document.querySelectorAll('link[rel="stylesheet"]')).some(link => link.href === href)) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  }
  componentModule ||= import(new URL('./view.js?v=1.11.0', import.meta.url).href);
  const [Vue, views] = await Promise.all([runtime, componentModule]);
  const component = name === './Page' ? views.createPage(Vue) : views.createConfig(Vue);
  return () => component;
}
