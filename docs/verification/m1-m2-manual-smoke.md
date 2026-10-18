# M1–M2 手测清单（CLI 黑盒）

自动化门禁跑 pytest；这份清单跑**真实命令**：`uv run minihns run` / `replay`，看退出码、看 JSONL 日志、看工作区文件真的变了没有。下面每个退出码与每条日志证据都是 2026-10-18 在 Windows 上实测得到的，不是推测。

前提：仓库根目录、`uv` 可用。脚手架与日志都在 `.tmp/`（已 gitignore）。fixture 是 JSON 数组，每条 = 一次 `AssistantTurn`（`content` / `finish_reason` / `tool_calls[].{id,name,arguments}`）。

---

## 一、一键跑完 11 个场景

整段可直接粘进 PowerShell。最后一行 `mismatches=0` 就是这一轮全对上了。

```powershell
$fx='.tmp/smoke/fixtures'; $sd='.tmp/smoke/sessions'
Remove-Item .tmp/smoke -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $fx -Force | Out-Null

function Call($id,$name,$argMap){ @{ id=$id; name=$name; arguments=$argMap } }
function Turn($content,$calls,$finish='tool_calls'){ @{ content=$content; finish_reason=$finish; tool_calls=$calls } }
# 本机 ConvertTo-Json 没有 -AsArray，用 -InputObject 保住「数组」这个形状
function Save($path,$fixtures){ ConvertTo-Json -InputObject @($fixtures) -Depth 6 | Set-Content $path -Encoding utf8 }
# 每个场景一个干净工作区：上一轮改过的文件会把下一轮的 old_string 变成「找不到」
function Reset-Ws($ws){
  Remove-Item $ws -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Path "$ws/sub" -Force | Out-Null
  Set-Content "$ws/notes.md" -Encoding utf8 -Value "# Notes`n`nTODO: one`nTODO: two`nBody line that stays.`n"
  Set-Content "$ws/sub/other.md" -Encoding utf8 -Value "TODO: three`n"
}

Save "$fx/m1-single.json" @((Turn 'no tool' @() 'stop'))
Save "$fx/m1-maxturns.json" @(
  (Turn 'glob 1' @(Call g1 glob @{ pattern='*.md' })),
  (Turn 'glob 2' @(Call g2 glob @{ pattern='*.md' })),
  (Turn 'glob 3' @(Call g3 glob @{ pattern='*.md' })),
  (Turn 'stop' @() 'stop'))
Save "$fx/m2-ten-ok.json" @(
  (Turn 'ten calls' @(
    (Call a1 read  @{ file_path='notes.md' }),
    (Call a2 edit  @{ file_path='notes.md'; old_string='TODO: one';  new_string='DONE: one' }),
    (Call a3 read  @{ file_path='notes.md' }),
    (Call a4 edit  @{ file_path='notes.md'; old_string='TODO: two';  new_string='DONE: two' }),
    (Call a5 read  @{ file_path='notes.md' }),
    (Call a6 edit  @{ file_path='notes.md'; old_string='Body line that stays.'; new_string='Body line edited.' }),
    (Call a7 read  @{ file_path='sub/other.md' }),
    (Call a8 edit  @{ file_path='sub/other.md'; old_string='TODO: three'; new_string='DONE: three' }),
    (Call a9 glob  @{ pattern='**/*.md' }),
    (Call a10 grep @{ pattern='DONE' }))),
  (Turn 'done' @() 'stop'))
Save "$fx/m2-stale.json" @(
  (Turn 'read once' @(Call d1 read @{ file_path='notes.md' })),
  (Turn 'two edits' @(
    (Call d2 edit @{ file_path='notes.md'; old_string='TODO: one'; new_string='DONE: one' }),
    (Call d3 edit @{ file_path='notes.md'; old_string='TODO: two'; new_string='DONE: two' }))),
  (Turn 'stop' @() 'stop'))
Save "$fx/m2-io.json" @(
  (Turn 'io' @(Call c1 write @{ file_path='notes.md/child.md'; content='x' })),
  (Turn 'stop' @() 'stop'))
Save "$fx/m2-outside.json" @(
  (Turn 'escape' @(Call b1 write @{ file_path='../escape.md'; content='x' })),
  (Turn 'stop' @() 'stop'))
Save "$fx/m2-readonly.json" @(
  (Turn 'read then overwrite' @(
    (Call e1 read  @{ file_path='notes.md' }),
    (Call e2 write @{ file_path='notes.md'; content='overwritten' }))),
  (Turn 'stop' @() 'stop'))
Save "$fx/m2-exhaust.json" @((Turn 'one turn only' @(Call f1 glob @{ pattern='*.md' })))
Save "$fx/m2-badfixture.json" @(@{ content=123 })

$cases=@(
 @{n='single';         f='m1-single.json';     e=@();                                   want=0},
 @{n='max-turns';      f='m1-maxturns.json';   e=@('--max-turns','2');                 want=0},
 @{n='ten-ok';         f='m2-ten-ok.json';     e=@('--yes');                           want=0},
 @{n='stale-edit';     f='m2-stale.json';      e=@('--yes');                           want=0},
 @{n='io-failure';     f='m2-io.json';         e=@('--yes');                           want=0},
 @{n='outside';        f='m2-outside.json';    e=@('--yes');                           want=3},
 @{n='read-only';      f='m2-readonly.json';   e=@('--yes','--sandbox','read-only');   want=3},
 @{n='danger-outside'; f='m2-outside.json';    e=@('--yes','--sandbox','danger-full-access'); want=0},
 @{n='exhausted';      f='m2-exhaust.json';    e=@('--yes');                           want=1},
 @{n='bad-fixture';    f='m2-badfixture.json'; e=@();                                   want=2},
 @{n='ask-no-tty';     f='m2-ten-ok.json';     e=@();                                   want=3})

$bad=0
foreach($c in $cases){
  $ws='.tmp/smoke/ws'; Reset-Ws $ws
  $out = uv run minihns run -p smoke --provider mock --fixture "$fx/$($c.f)" `
             --workspace $ws --session-dir $sd --events jsonl @($c.e) 2>&1
  $code=$LASTEXITCODE; $oc=''
  if($code -ne 2){
    $log = Get-ChildItem $sd -Filter '*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $m = Select-String -Path $log.FullName -Pattern '"outcome": "([A-Z_]+)"' -AllMatches
    if($m){ $oc = (($m.Matches | ForEach-Object { $_.Groups[1].Value }) -join ',') }
    $s = Select-String -Path $log.FullName -Pattern 'session/end.*stop_reason": "([A-Z_]+)"'
    if($s){ $oc += '  session/end=' + ($s.Line -replace '.*stop_reason": "([A-Z_]+)".*','$1') }
  } else { $oc = 'no log; stderr: ' + (($out | Select-Object -First 1) -replace '\s+',' ') }
  if($code -ne $c.want){ $bad++ }
  Write-Output ("{0} {1,-15} exit={2} want={3}  {4}" -f $(if($code -eq $c.want){'OK '}else{'BAD'}),$c.n,$code,$c.want,$oc)
  Remove-Item .tmp/smoke/escape.md -ErrorAction SilentlyContinue
}
Write-Output "mismatches=$bad"
```

---

## 二、每个场景在证明什么（实测值）

| 场景 | 退出码 | 日志证据 | 证明的是 |
|---|---|---|---|
| `single` | 0 | `session/end` = `MODEL_COMPLETED` | M1 回合循环能跑完、日志有头有尾 |
| `max-turns` | 0 | `session/end` = `MAX_TURNS` | 回合上限是**停止原因**，不是异常（不变量 C） |
| `ten-ok` | 0 | 10 个 `outcome: OK`；`notes.md` 三处改到位、`sub/other.md` 变 `DONE: three` | M2 完成判据：一轮 10 次 read+edit 全 OK |
| `stale-edit` | 0 | `OK, OK, STALE_EDIT` | 一次 `read` 只授权一次 `edit`；CAS 比的是读到的窗口（ADR-0004） |
| `io-failure` | 0 | `TOOL_IO_FAILED`，**没有** `error/*`，照走到 `MODEL_COMPLETED` | 不变量 B：执行段的 I/O 失败也是结果（M2 审查修的那条） |
| `outside` | 3 | `DENIED_BY_FENCE` + `code: OUTSIDE_WORKSPACE`；`..` 下没有新文件 | 工作区边界 |
| `read-only` | 3 | 同批 `read` 是 `OK`、`write` 是 `DENIED_BY_FENCE` + `SANDBOX_DENIES_WRITE` | 档位只约束改东西的工具，读不受约束（不变量 E 两轴独立） |
| `danger-outside` | 0 | `outcome: OK`，文件真写到工作区外 | 档位放开边界，但写前必读 CAS 照管（测完删掉 `escape.md`） |
| `exhausted` | 1 | `code: PROVIDER_EXHAUSTED`、`session/end` = `PROVIDER_ERROR` | Provider 失败也是结果，落到退出码 |
| `bad-fixture` | 2 | 走 stderr 的 `FIXTURE_INVALID: … 第 1 条不符合 AssistantTurn 形状`，**不产生日志** | 输入不合法在起跑前就被拒 |
| `ask-no-tty` | 3 | `DENIED_BY_APPROVAL` + `code: APPROVAL_UNAVAILABLE` | 没有 tty 时问人失败 = 拒绝，不是放行 |

退出码表：0 正常 · 1 内部失败 · 2 参数 / 输入不合法 · 3 围栏或问人拒绝 · 5 取消（4 预留）。

**重放（M1 的另一半）**，用上面任意一条跑出来的 session：

```powershell
$id = (Get-ChildItem $sd -Filter '*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).BaseName
uv run minihns replay $id --session-dir $sd      # 退出码 0
uv run minihns replay deadbeef --session-dir $sd # 退出码 2，SESSION_NOT_FOUND
```

实测 `replay` 输出：逐条 `verified seq=…: OK`、每回合 `turn t1: TOOL_CALLS` / `turn t2: MAX_TURNS`、最后一行 `final_context` 带 `header_fingerprint`。`verified` 就是「日志只追加、没被改写」（不变量 A）的机器版检查。

---

## 三、只有真终端能做的两条

脚本化环境做不了，必须人坐在终端前。

**问人（approval）**：不加 `--yes` 跑 `ten-ok`。每次 mutating 调用前 stderr 出一行询问。

- 输入 `y` → 继续，最终退出码 0。
- 输入 `n` → 退出码 **3**，日志 `DENIED_BY_APPROVAL`、`session/end` = `FENCE_DENIED`。
- 没有 tty（管道、CI、`< NUL`）→ 退出码 **3** + `APPROVAL_UNAVAILABLE`。这条已实测（上表 `ask-no-tty`）。
- `--yes` 只关掉问人，**不放开围栏**：`read-only` 加 `--yes` 仍是 3。

**Ctrl-C**：跑一条要好几轮的 session，中途按 Ctrl-C。期望退出码 **5**、`stop_reason: ABORTED`、`error/abort` 带 `code: ABORTED`。这条**没有黑盒测试**，是已知缺口（`docs/CURRENT.md`）。

---

## 四、读日志的三条技巧

```powershell
$log = (Get-ChildItem $sd -Filter '*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
Select-String $log -Pattern '"outcome": "([A-Z_]+)"' -AllMatches   # 每次工具调用的结果词表（14 值）
Select-String $log -Pattern '"code": "([A-Z_]+)"'    -AllMatches   # 围栏 / Provider / 取消的码
Select-String $log -Pattern '"stop_reason"'                          # 回合与 session 怎么停的
```

`seq` 从 0 连续递增、`session/start` 只有一条、最后一行是 `session/end`——三条同时成立才说明日志没被改写。`session/start` 里还能核对档位与 approval 实际生效值（`"sandbox": "workspace-write", "approval": "ask"`）。

---

## 五、本机做不了的手测

- **符号链接 / junction 的边界键规范化**：这台机器上没建成功（需要额外权限），所以「工作区内的链接指向工作区外」只有单元测试，没有手测。
- **OS 级拦截**：围栏不是安全边界（ADR 写明）。手测只能证明「harness 自己拒绝」，不能证明「操作系统拦住了」。
