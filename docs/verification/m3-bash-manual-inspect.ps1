# M3 manual acceptance evidence dump. Run once after each scenario and paste the whole output.
#   powershell -NoProfile -ExecutionPolicy Bypass -File .tmp/m3-manual/inspect.ps1
# Read the exit code FIRST (echo "exit=$LASTEXITCODE") - external commands below overwrite it.
# All strings here are ASCII on purpose: Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI.

$dir = ".tmp\m3-manual\sessions"
$log = Get-ChildItem $dir -Filter *.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1
if ($null -eq $log) {
    Write-Output "no log found in $dir"
    exit 1
}

$records = Get-Content $log.FullName -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json }

"session:  $($log.BaseName)"
"records:  $($records.Count)"
$t0 = [datetime]::Parse($records[0].ts)
$t1 = [datetime]::Parse($records[-1].ts)
"wall clock (log ts): {0:N2} s" -f ($t1 - $t0).TotalSeconds
""
"--- event sequence ---"
foreach ($e in $records) {
    $p = $e.payload
    $extra = "$($p.outcome) $($p.decision) $($p.code) $($p.stop_reason) $($p.error_code)".Trim()
    "{0,18}  {1,3}  {2,4}  {3}" -f $e.type, $p.turn_id, $p.tool_call_id, $extra
}
""
"--- last 6 records (raw) ---"
Get-Content $log.FullName -Encoding UTF8 -Tail 6
""
"--- python processes still alive ---"
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Select-Object ProcessId, CommandLine |
    Format-Table -AutoSize -Wrap
