# monitor_npm_cache_orphans.ps1 — npm cache 孤儿目录只读诊断
# 用法：powershell -File tools\dev\monitor_npm_cache_orphans.ps1
#
# 输出 4 块：
#   1. npm config cache 路径（确认 L1 junction 是否被污染）
#   2. cwd 顶层可疑目录扫描（继承 check_orphan_caches 的 3 类信号）
#   3. 当前所有 node.exe 进程 + 父进程链（找孤儿源头）
#   4. 结论摘要
#
# 只读，绝不修改 / 杀进程 / 删目录。

$ErrorActionPreference = 'Continue'
$cwd = (Get-Location).Path
Write-Output "=== npm cache 孤儿监控 ==="
Write-Output "CWD: $cwd"
Write-Output "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output ""

# ── 1. npm config 状态 ──
Write-Output "─── 1. npm config cache 路径 ───"
$npmCache = npm config get cache 2>$null
Write-Output "npm config cache = $npmCache"
if ($npmCache -like "$cwd*") {
  Write-Output "  ⚠️  WARN: cache 路径在 cwd 内，会绕过 L1 junction"
} else {
  Write-Output "  ✓ cache 路径不在 cwd（junction 可生效）"
}
Write-Output ""

# ── 2. cwd 顶层扫描 ──
Write-Output "─── 2. cwd 顶层可疑目录（孤儿 cache 签名） ───"
$knownGood = @('src','tests','docs','data','tools','scripts','scripts_bak',
  '.venv','node_modules','static','dist','build',
  '.pytest_cache','.ruff_cache','.mypy_cache','.tox',
  'vet-game-frontend','vet-game-frontend_backup',
  'cvs-reference','Bioflow_Labs_Platform-main','Medicina-main',
  '.claude','.codegraph','.cursor','.vscode','.idea',
  'results','.tmp','paper_rewriting_output',
  'experiments','_tools_dev')

$found = $false
Get-ChildItem -Path $cwd -Directory -Force -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
  $n = $_.Name
  if ($n.StartsWith('.')) { return }
  if ($knownGood -contains $n) { return }

  $signals = @()
  if ((Test-Path "$_\cacache") -and (Test-Path "$_\logs")) {
    $signals += 'npm-cache-signature'
  }
  if ($n -match '[＀-￯]') {
    $signals += 'fullwidth-unicode'
  }
  if ($n -match '^[A-Z]:') {
    $signals += 'drive-letter-prefix'
  }

  if ($signals.Count -gt 0) {
    $found = $true
    $mtime = $_.LastWriteTime.ToString('HH:mm:ss')
    $size = '{0:N0}KB' -f ((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1024)
    Write-Output "  ⚠  $n  (mtime=$mtime, size=$size)"
    Write-Output "     signals: $($signals -join ', ')"
  }
}
if (-not $found) { Write-Output "  ✓ 无可疑目录" }
Write-Output ""

# ── 3. node.exe 进程链 ──
Write-Output "─── 3. node.exe 进程列表（找孤儿源头） ───"
# 已知合法进程白名单（按 cmdline 子串匹配）
# 模式：npx-cli 包装器 + 各种 MCP / IDE / 工具 server
$knownGood = @(
  'token-optimizer-mcp',  # Claude Code token optimizer MCP
  'npx-cli.js',           # npx 包装器（所有 npx 启动的进程合法）
  '@anthropic-ai/claude-code',
  '@openai/codex',         # Codex 扩展
  'vscode',                # VS Code 内置
  'github-mcp'             # GitHub MCP
)
$nodes = Get-Process node -ErrorAction SilentlyContinue | Sort-Object StartTime
Write-Output "  Total node.exe: $($nodes.Count)"
$orphanCount = 0
$unknownOrphan = @()
foreach ($p in $nodes) {
  $w = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue
  $pp = if ($w) { $w.ParentProcessId } else { 0 }
  $pn = if ($pp -gt 0) {
    $pp2 = Get-CimInstance Win32_Process -Filter "ProcessId=$pp" -ErrorAction SilentlyContinue
    if ($pp2) { $pp2.Name } else { '?' }
  } else { '?' }
  $cmd = if ($w) { $w.CommandLine } else { '' }
  if ($cmd.Length -gt 120) { $cmd = $cmd.Substring(0, 120) + '...' }

  $isOrphan = ($pn -eq '?' -or $pp -eq 0)
  $isKnown = $false
  foreach ($kw in $knownGood) {
    if ($cmd -like "*$kw*") { $isKnown = $true; break }
  }
  $tag = ''
  if ($isOrphan -and $isKnown) { $tag = ' [ORPHAN-known-safe]' }
  elseif ($isOrphan) {
    $tag = ' [ORPHAN-unknown!]'
    $orphanCount++
    $unknownOrphan += "PID=$($p.Id) cmd=$cmd"
  }
  Write-Output ("  PID={0,-6} Start={1,-19} Mem={2,7}KB Parent={3,-15}{4}" -f $p.Id, $p.StartTime.ToString('HH:mm:ss'), [int]($p.WorkingSet64/1024), $pn, $tag)
  if ($cmd) { Write-Output "         cmd: $cmd" }
}
Write-Output ""

# ── 4. 结论 ──
Write-Output "─── 4. 结论摘要 ───"
Write-Output "  npm config cache: $npmCache"
Write-Output "  孤儿目录数: $(if ($found) { 1 } else { 0 })"
Write-Output "  node.exe 总数: $($nodes.Count)"
Write-Output "  未知孤儿 node 数: $orphanCount  (已知合法已白名单过滤)"
if ($unknownOrphan.Count -gt 0) {
  Write-Output "  ⚠ 以下孤儿需人工判断："
  foreach ($u in $unknownOrphan) { Write-Output "    $u" }
}
Write-Output ""
Write-Output "下一步："
Write-Output "  - 孤儿目录: rm -rf -- <name>  (确认无进程持有后)"
Write-Output "  - 未知孤儿进程: taskkill /F /PID <pid>  (你手动执行)"
