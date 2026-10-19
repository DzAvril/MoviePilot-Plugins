export const DEFAULTS = {
  enabled: false, notify: false, delete_scrap_infos: false, delete_torrents: false, delete_history: false,
  delayed_deletion: true, delay_seconds: 30, monitor_dirs: '', exclude_dirs: '', exclude_keywords: '',
  custom_scrap_extensions: '', monitor_strm_deletion: false, strm_path_mappings: '',
};
export function configPayload(config) {
  const delay = Number(config.delay_seconds);
  if (!Number.isInteger(delay) || delay < 10 || delay > 86400) throw new Error('等待时间需为 10 至 86400 之间的整数秒。');
  return {...config, delay_seconds: delay};
}
const lineCount = value => String(value ?? '').split(/\r?\n/).filter(line => line.trim()).length;
const NAV = [['general', '运行设置'], ['links', '硬链接'], ['strm', 'STRM 联动'], ['cleanup', '清理选项']];

export function createConfig(Vue) {
  const {defineComponent, h, reactive, ref, computed, onMounted} = Vue;
  return defineComponent({
    name: 'RemoveLinkConfig', props: {api: Object, pluginId: String, initialConfig: Object}, emits: ['layout', 'save', 'close'],
    setup(props, {emit}) {
      const config = reactive({...DEFAULTS, ...JSON.parse(JSON.stringify(props.initialConfig || {}))});
      const active = ref('links'), error = ref('');
      const snapshot = JSON.stringify({...config, delay_seconds: Number(config.delay_seconds)});
      const dirty = computed(() => JSON.stringify({...config, delay_seconds: Number(config.delay_seconds)}) !== snapshot);
      onMounted(() => emit('layout', {maxWidth: '1120px'}));
      const icon = (name, size = 20) => h('svg', {viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': true}, [
        h('path', {d: {
          link: 'm10 13 4-4m-6 6-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 2 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0',
          folder: 'M3 7V4h7l3 3h8v13H3V7Z', shield: 'M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7L12 3Zm-4 9 3 3 5-6',
          clock: 'M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z', check: 'm5 12 4 4L19 6', close: 'm6 6 12 12M6 18 18 6',
          file: 'M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 13h8M8 17h5', arrow: 'M4 12h16m-6-6 6 6-6 6',
        }[name] || 'M12 4v16M4 12h16'}),
      ]);
      const button = (label, onClick, primary = false, name = '') => h('button', {type: 'button', class: `rml-btn${primary ? ' rml-primary' : ''}`, onClick}, [name && icon(name, 17), label]);
      const badge = (label, enabled = true) => h('span', {class: `rml-badge${enabled ? '' : ' rml-muted'}`}, label);
      const panel = (title, detail, content, name = '') => h('section', {class: 'rml-panel'}, [
        h('div', {class: 'rml-section-title'}, [h('div', {class: 'rml-section-heading'}, [name && icon(name), h('h3', title)]), detail && h('p', detail)]), ...content,
      ]);
      const toggle = (key, title, detail) => h('label', {class: 'rml-toggle'}, [
        h('div', [h('strong', title), h('p', detail)]),
        h('input', {type: 'checkbox', role: 'switch', 'aria-label': title, checked: !!config[key], onChange: event => {config[key] = event.target.checked;}}),
      ]);
      const area = (key, label, detail, rows = 3, placeholder = '', disabled = false) => h('label', {class: 'rml-field'}, [
        h('span', label), h('textarea', {'aria-label': label, rows, placeholder, disabled, value: config[key] ?? '', onInput: event => {config[key] = event.target.value;}}), h('small', detail),
      ]);
      const save = () => {
        try {const payload = configPayload(config); error.value = ''; emit('save', payload);}
        catch (reason) {error.value = reason.message; active.value = 'links';}
      };
      const general = () => [
        panel('运行与通知', '设置保存后生效；此页不会直接执行清理。', [
          toggle('enabled', '启用插件', '监听已配置目录的文件删除事件，按规则联动清理。'),
          toggle('notify', '发送结果通知', '联动清理完成后，发送处理结果。'),
        ], 'shield'),
        panel('配置范围', '分别管理两类文件的删除联动。', [
          h('div', {class: 'rml-scope-row'}, [h('div', {class: 'rml-scope-icon'}, icon('link')), h('div', [h('strong', '硬链接'), h('p', '监控源目录与媒体库目录，识别指向同一文件的链接。')]), button('查看规则', () => {active.value = 'links';})]),
          h('div', {class: 'rml-scope-row'}, [h('div', {class: 'rml-scope-icon'}, icon('file')), h('div', [h('strong', 'STRM 联动'), h('p', '根据路径映射，联动处理存储中的对应视频。')]), button('查看映射', () => {active.value = 'strm';})]),
        ]),
      ];
      const links = () => [
        h('div', {class: 'rml-columns'}, [
          panel('监控目录', '源目录和媒体库目录都要加入，才能识别同一文件的硬链接。', [
            area('monitor_dirs', '目录列表', '每行一个绝对路径；现有路径按原样保留。', 6, '/downloads\n/media/movies\n/media/tv'),
            h('div', {class: 'rml-inline-note'}, [icon('folder', 17), h('span', `已填写 ${lineCount(config.monitor_dirs)} 个监控目录`)]),
          ], 'folder'),
          panel('延迟复核', '等待后再次确认，减少重新整理期间的误清理。', [
            toggle('delayed_deletion', '启用延迟删除', '文件被删除后，等待指定时间再检查。'),
            h('label', {class: 'rml-field'}, [h('span', '等待时间（秒）'), h('div', {class: 'rml-number'}, [
              h('input', {type: 'number', min: 10, max: 86400, step: 1, disabled: !config.delayed_deletion, 'aria-label': '等待时间（秒）', value: config.delay_seconds, onInput: event => {config.delay_seconds = event.target.value;}}), h('span', '秒'),
            ]), h('small', '10 秒至 24 小时，默认 30 秒。')]),
            h('p', {class: 'rml-note'}, '重新整理时，文件可能短暂消失后重新出现。延迟复核可减少这类事件触发的联动清理。'),
          ], 'clock'),
        ]),
        panel('保护与排除', '指定需要保留的目录或名称。', [h('div', {class: 'rml-form-grid'}, [
          area('exclude_dirs', '受保护目录', '目录内文件不被联动删除；保留源文件时，把源目录填在这里。', 3, '每行一个目录'),
          area('exclude_keywords', '排除名称关键词', '匹配的文件保留，每行一个关键词。', 3, '每行一个关键词'),
        ])], 'shield'),
      ];
      const strm = () => [
        panel('STRM 文件监控', '通过路径映射，将本地 STRM 与存储中的视频对应起来。', [
          toggle('monitor_strm_deletion', '启用 STRM 文件监控', '本地 STRM 被删除时，联动删除映射存储中的对应视频。'),
        ], 'file'),
        h('div', {class: 'rml-columns'}, [
          panel('路径映射', '监控目录自动取自这里填写的 STRM 目录。', [
            area('strm_path_mappings', 'STRM 路径映射', '每行：STRM目录:存储类型:视频目录。', 6, '/ssd/strm:u115:/media\n/nas/strm:alipan:/阿里云盘/媒体'),
            h('div', {class: 'rml-inline-note'}, [icon('link', 17), h('span', `已填写 ${lineCount(config.strm_path_mappings)} 组映射`)]),
          ], 'link'),
          panel('映射示例', '按 STRM 文件的相对路径，找到对应的视频。', [
            h('div', {class: 'rml-example'}, [h('small', '本地 STRM'), h('code', '/ssd/strm/test.strm'), icon('arrow', 20), h('small', '115 视频路径前缀'), h('code', '/media/test')]),
            h('p', {class: 'rml-note'}, '示例映射：/ssd/strm:u115:/media'),
            h('div', {class: 'rml-storage'}, ['local', 'u115', 'alipan', 'rclone', 'alist'].map(name => badge(name))),
          ]),
        ]),
      ];
      const cleanup = () => [
        panel('关联内容', '随文件删除事件，一并处理所选的关联内容。', [
          toggle('delete_scrap_infos', '清理刮削文件', '删除对应的元数据、图片、字幕与预览目录。'),
          toggle('delete_history', '删除转移记录', '删除对应的 MoviePilot 整理记录。'),
          toggle('delete_torrents', '联动删除种子', '需安装「下载器助手」，并启用监听源文件事件。'),
        ], 'file'),
        panel('额外清理的文件后缀', '与内置的 .nfo、.jpg、.srt 等后缀合并使用。', [
          area('custom_scrap_extensions', '自定义后缀', '每行或逗号分隔一个后缀；仅在清理刮削文件开启时生效。', 4, '.txt\n.json\n-mediainfo.json', !config.delete_scrap_infos),
        ]),
      ];
      return () => h('form', {class: 'rml-root', onSubmit: event => {event.preventDefault(); save();}}, [
        h('header', {class: 'rml-header'}, [
          h('div', {class: 'rml-brand'}, [h('div', {class: 'rml-logo'}, icon('link', 34)), h('div', [h('div', {class: 'rml-eyebrow'}, 'LIBRARY · CARE'), h('h2', '媒体清理设置'), h('p', '管理硬链接、STRM 与关联文件')])]),
          h('div', {class: 'rml-actions'}, [button('取消', () => emit('close'), false, 'close'), button('保存设置', save, true, 'check')]),
        ]),
        h('div', {class: 'rml-overview'}, [
          ['general', '运行开关', config.enabled ? '已开启' : '未开启', '目录删除事件监控'],
          ['links', '硬链接目录', `${lineCount(config.monitor_dirs)} 个`, '源目录与媒体库目录'],
          ['strm', 'STRM 联动', `${lineCount(config.strm_path_mappings)} 组`, config.monitor_strm_deletion ? '已开启映射监控' : '映射监控未开启'],
          ['cleanup', '关联清理', `${['delete_scrap_infos', 'delete_history', 'delete_torrents'].filter(key => config[key]).length} 项`, '刮削文件、记录与种子'],
        ].map(([key, title, value, detail]) => h('button', {type: 'button', class: `rml-stat${active.value === key ? ' rml-stat-active' : ''}`, 'aria-label': `查看${NAV.find(item => item[0] === key)[1]}`, onClick: () => {active.value = key;}}, [h('span', title), h('strong', value), h('small', detail)]))),
        h('div', {class: 'rml-context'}, [badge(dirty.value ? '有未保存的修改' : '配置已载入', dirty.value), h('span', '下方展示当前设置，保存后生效。')]),
        h('nav', {class: 'rml-tabs', 'aria-label': '设置分区'}, NAV.map(([key, label]) => h('button', {type: 'button', 'aria-current': active.value === key ? 'true' : undefined, class: active.value === key ? 'rml-tab-active' : '', onClick: () => {active.value = key;}}, label))),
        error.value && h('div', {class: 'rml-alert', role: 'alert'}, error.value),
        h('div', {class: 'rml-content', role: 'region', 'aria-label': NAV.find(item => item[0] === active.value)[1]}, {general, links, strm, cleanup}[active.value]()),
        h('footer', {class: 'rml-footer'}, [icon('shield', 16), h('span', '取消不会更改已保存的设置。')]),
      ]);
    },
  });
}
