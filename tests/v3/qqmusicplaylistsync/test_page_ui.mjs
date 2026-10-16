import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const source = await readFile(new URL('../../../plugins.v3/qqmusicplaylistsync/dist/assets/view.js', import.meta.url), 'utf8');
const {filterSongs, paginate, downloadStatus, applySongStates, createPlaylistCover} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const songs = Array.from({length:321}, (_, i) => ({id:String(i),title:`歌曲${i}`,artists:['歌手'],album:'专辑',
  playlist_ids:i%2 ? ['one'] : ['one','two'],status:i<20 ? 'library' : 'searching'}));

test('search matches song artist and album while combining playlist and status filters', () => {
  assert.equal(filterSongs(songs,'歌曲３２０ 歌手 专辑','two','searching')[0].id, '320');
  assert.equal(filterSongs(songs,'','two','library').length,10);
  assert.equal(filterSongs(songs,'不存在').length,0);
  assert.equal(filterSongs([...songs,{...songs[0],status:'failed'}],'','','unresolved').length,302);
});

test('pagination retains all 321 unique songs including final page and clamps stale pages', () => {
  const ids=[];
  for (let p=1;p<=33;p++) ids.push(...paginate(songs,p).rows.map(song=>song.id));
  assert.equal(new Set(ids).size,321);
  assert.deepEqual(ids,songs.map(song=>song.id));
  assert.equal(paginate(songs,100).page,33);
  assert.equal(paginate([],9).start,0);
});

test('download completion comes from actual progress rather than the plugin submission phase', () => {
  assert.equal(downloadStatus({phase:'started',progress:null}).text,'已核对选曲');
  assert.equal(downloadStatus({state:'stalledDL',progress:.82}).text,'下载中');
  assert.equal(downloadStatus({state:'stoppedDL',progress:.82}).text,'已暂停');
  assert.equal(downloadStatus({state:'stalledUP',progress:1}).text,'下载完成');
  assert.equal(downloadStatus({state:'missing',progress:null}).text,'下载器中未找到');
  assert.equal(downloadStatus({state:'checkingUP',progress:1}).text,'校验中');
});

test('the Vue settings form preserves unknown fields and blank MP defaults when saving', async () => {
  const {createConfig} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  const Vue = {defineComponent:value=>value, reactive:value=>value, ref:value=>({value}), onMounted:()=>{},
    h:(type,props,children)=>({type,props,children})};
  const emitted=[];
  const render=createConfig(Vue).setup({initialConfig:{enabled:true,dry_run:false,playlist_urls:'one\ntwo',
    netease_playlist_urls:'https://music.163.com/#/my/m/music/playlist?id=80068278',
    downloader:'',save_path:'',library_path:'',future_option:'keep'}}, {emit:(...args)=>emitted.push(args)});
  const tree=render();
  const visit=node=>{
    if (!node || typeof node!=='object') return;
    if (node.type==='button' && node.props?.['aria-label']==='保存设置') node.props.onClick();
    for (const child of [node.props,node.children].flat()) if (child && typeof child==='object') visit(child);
  };
  visit(tree);
  const saved=emitted.find(item=>item[0]==='save')[1];
  assert.equal(saved.future_option,'keep');
  assert.equal(saved.playlist_urls,'one\ntwo');
  assert.equal(saved.netease_playlist_urls,'https://music.163.com/#/my/m/music/playlist?id=80068278');
  assert.equal(saved.enabled,true);
  assert.equal(saved.dry_run,false);
  for (const key of ['downloader','save_path','library_path']) assert.equal(saved[key],'');
});

test('live song updates replace subscription labels with actual lifecycle while preserving search metadata', () => {
  const data={songs:songs.slice(0,3).map(song=>({...song,status:'searching'})),downloads:[],status_counts:{searching:3}};
  const before=structuredClone(data);
  const next=applySongStates(data,{song_states:{
    '0':{status:'downloading',status_label:'下载中',progress:.35},
    '1':{status:'library',status_label:'已入库',progress:null},
    '2':{status:'downloaded',status_label:'待入库',progress:1},
    'unknown-id':{status:'library'}},status_updated_at:100});
  assert.equal(next.songs[0].progress,.35);
  assert.equal(next.songs[1].status,'library');
  assert.equal(next.songs[2].status,'downloaded');
  assert.equal(filterSongs(next.songs,'','two','downloading').length,1);
  assert.equal(filterSongs(next.songs,'','','unresolved').length,2);
  assert.deepEqual(next.status_counts,{downloading:1,library:1,downloaded:1});
  assert.deepEqual(data,before);
  const later=applySongStates(next,{song_states:{'0':{status:'library',progress:null}},status_updated_at:115});
  assert.equal(later.status_counts.library,2);
  assert.equal(later.songs[1].title,data.songs[1].title);
  assert.equal(later.status_updated_at,115);
});

test('playlist covers use MP caching, fall back after load failure, and retry when the platform changes the cover', () => {
  const Vue = {defineComponent:value=>value, ref:value=>({value}), h:(type,props,children)=>({type,props,children})};
  const playlist = {title:'我的歌单', cover_url:'https://p1.music.126.net/cover.jpg?a=1&b=2'};
  const render = createPlaylistCover(Vue).setup({playlist,index:0});
  const image = () => render().children.find(child=>child?.type==='img');
  const img = image();
  const sourceUrl = new URL(img.props.src,'https://moviepilot.test');
  assert.equal(sourceUrl.pathname,'/api/v1/system/img/0');
  assert.equal(sourceUrl.searchParams.get('imgurl'),playlist.cover_url);
  assert.equal(sourceUrl.searchParams.get('cache'),'true');
  assert.equal(img.props.alt,'我的歌单的封面');
  img.props.onError();
  assert.equal(image(),undefined);
  assert.equal(render().children[0].type,'svg');
  playlist.cover_url = 'https://p1.music.126.net/new.jpg';
  assert.ok(image());
  playlist.cover_url = '';
  assert.equal(image(),undefined);
});
