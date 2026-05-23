import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import archiver from 'archiver'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const initFilePath = path.join(__dirname, '__init__.py')

function getPluginZipBaseName() {
  if (!fs.existsSync(initFilePath)) {
    throw new Error('缺少必需文件: __init__.py')
  }

  const initContent = fs.readFileSync(initFilePath, 'utf-8')
  const pluginClassMatch = initContent.match(/^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*_PluginBase[^)]*\)\s*:/m)

  if (!pluginClassMatch) {
    throw new Error('无法从 __init__.py 中解析 _PluginBase 子类名称')
  }

  return pluginClassMatch[1].toLowerCase()
}

const pluginZipBaseName = getPluginZipBaseName()
const zipFileName = `${pluginZipBaseName}.zip`
const outputFilePath = path.join(__dirname, zipFileName)
const output = fs.createWriteStream(outputFilePath)
const archive = archiver('zip', {
  zlib: { level: 9 },
})

output.on('close', () => {
  console.log(`\n\x1b[32m[打包成功]\x1b[0m 已生成插件安装包: ${zipFileName}`)
  console.log(`\x1b[36m文件大小:\x1b[0m ${(archive.pointer() / 1024).toFixed(2)} KB`)
  console.log('可以直接在 MoviePilot 插件页面上传此 ZIP 文件。\n')
})

archive.on('warning', err => {
  if (err.code === 'ENOENT') {
    console.warn('\x1b[33m[打包警告]\x1b[0m', err.message)
  } else {
    throw err
  }
})

archive.on('error', err => {
  console.error('\x1b[31m[打包失败]\x1b[0m', err)
  throw err
})

archive.pipe(output)
archive.file(initFilePath, { name: '__init__.py' })

const distDir = path.join(__dirname, 'dist')
if (fs.existsSync(distDir)) {
  archive.directory(distDir, 'dist')
}

archive.finalize()
