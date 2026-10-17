"""M2 approval 真实 tty smoke 夹具（不属于测试套件，手工执行）。

子进程用 CREATE_NEW_CONSOLE 得到自己的真实控制台，父进程 AttachConsole 到该控制台、
打开 CONIN$，用 WriteConsoleInput 投递 y / n 的按键事件——于是 approval 门看到的
是一个真 tty，回答来自真按键，不是管道也不是重定向文件。

跑法（仓库根）：

    uv run python docs/verification/m2-file-tools-and-fences-approval-smoke-harness.py

它打印两次运行的退出码与关键事件，并在结束时清掉临时工作区与会话目录。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import shutil
import sys
import time
from pathlib import Path

k32 = ctypes.windll.kernel32
CREATE_NEW_CONSOLE = 0x00000010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
SHARE_READ_WRITE = 0x3
OPEN_EXISTING = 3
KEY_EVENT = 0x0001
VK_Y = 0x59
VK_N = 0x4E
VK_RETURN = 0x0D
INVALID = ctypes.c_void_p(-1).value
FIXTURE = "tests/fixtures/scenarios/read_then_write/turns.json"


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wt.BOOL),
        ("wRepeatCount", wt.WORD),
        ("wVirtualKeyCode", wt.WORD),
        ("wVirtualScanCode", wt.WORD),
        ("UnicodeChar", wt.WCHAR),
        ("dwControlKeyState", wt.DWORD),
    ]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wt.WORD), ("KeyEvent", KEY_EVENT_RECORD)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wt.HANDLE),
        ("hThread", wt.HANDLE),
        ("dwProcessId", wt.DWORD),
        ("dwThreadId", wt.DWORD),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("lpReserved", wt.LPWSTR),
        ("lpDesktop", wt.LPWSTR),
        ("lpTitle", wt.LPWSTR),
        ("dwX", wt.DWORD),
        ("dwY", wt.DWORD),
        ("dwXSize", wt.DWORD),
        ("dwYSize", wt.DWORD),
        ("dwXCountChars", wt.DWORD),
        ("dwYCountChars", wt.DWORD),
        ("dwFillAttribute", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("wShowWindow", wt.WORD),
        ("cbReserved2", wt.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wt.HANDLE),
        ("hStdOutput", wt.HANDLE),
        ("hStdError", wt.HANDLE),
    ]


k32.CreateProcessW.argtypes = [
    wt.LPCWSTR,
    wt.LPWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wt.BOOL,
    wt.DWORD,
    ctypes.c_void_p,
    wt.LPCWSTR,
    ctypes.POINTER(STARTUPINFOW),
    ctypes.POINTER(PROCESS_INFORMATION),
]
k32.CreateFileW.restype = wt.HANDLE
k32.CreateFileW.argtypes = [
    wt.LPCWSTR,
    wt.DWORD,
    wt.DWORD,
    ctypes.c_void_p,
    wt.DWORD,
    wt.DWORD,
    wt.HANDLE,
]
k32.WriteConsoleInputW.argtypes = [
    wt.HANDLE,
    ctypes.POINTER(INPUT_RECORD),
    wt.DWORD,
    ctypes.POINTER(wt.DWORD),
]
k32.AttachConsole.argtypes = [wt.DWORD]
k32.FreeConsole.argtypes = []
k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.CloseHandle.argtypes = [wt.HANDLE]


def key_records(text: str) -> list[INPUT_RECORD]:
    """把每个字符展开成按下与松开两条 KEY_EVENT 记录。"""
    records: list[INPUT_RECORD] = []
    for char in text:
        virtual = VK_RETURN if char == "\r" else (VK_Y if char == "y" else VK_N)
        for down in (True, False):
            record = INPUT_RECORD()
            record.EventType = KEY_EVENT
            record.KeyEvent.bKeyDown = 1 if down else 0
            record.KeyEvent.wRepeatCount = 1
            record.KeyEvent.wVirtualKeyCode = virtual
            record.KeyEvent.UnicodeChar = char
            records.append(record)
    return records


def main() -> int:
    repo = Path.cwd()
    python = repo / ".venv" / "Scripts" / "python.exe"
    workspace = repo / ".smoke-ws"
    session_dir = repo / ".smoke-sessions"
    fixture = repo / FIXTURE

    for answer, typed in (("y", "y\r"), ("n", "n\r")):
        for directory in (workspace, session_dir):
            if directory.exists():
                shutil.rmtree(directory)
        (workspace / "notes").mkdir(parents=True)
        target = workspace / "notes" / "plan.md"
        target.write_text("# 计划\n\n待办：改这一行。\n", encoding="utf-8")
        before = target.read_bytes()

        command = (
            f'"{python}" -m mini_harness.cli.main run -p 任务 --provider mock '
            f'--fixture "{fixture}" --workspace "{workspace}" --session-dir "{session_dir}"'
        )
        startup = STARTUPINFOW()
        startup.cb = ctypes.sizeof(STARTUPINFOW)
        info = PROCESS_INFORMATION()
        ok = k32.CreateProcessW(
            None,
            command,
            None,
            None,
            False,
            CREATE_NEW_CONSOLE,
            None,
            str(repo),
            ctypes.byref(startup),
            ctypes.byref(info),
        )
        if not ok:
            print(f"CreateProcessW failed: {k32.GetLastError()}", file=sys.stderr)
            return 1

        time.sleep(2.0)  # 等子进程把提问写到它自己的控制台并阻塞在读取上
        k32.FreeConsole()
        if not k32.AttachConsole(info.dwProcessId):
            print(f"AttachConsole failed: {k32.GetLastError()}", file=sys.stderr)
            return 1
        handle = k32.CreateFileW(
            "CONIN$",
            GENERIC_READ | GENERIC_WRITE,
            SHARE_READ_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle is None or handle == INVALID:
            print(f"open CONIN$ failed: {k32.GetLastError()}", file=sys.stderr)
            return 1
        records = key_records(typed)
        array = (INPUT_RECORD * len(records))(*records)
        written = wt.DWORD()
        if not k32.WriteConsoleInputW(handle, array, len(records), ctypes.byref(written)):
            print(f"WriteConsoleInput failed: {k32.GetLastError()}", file=sys.stderr)
        k32.CloseHandle(handle)
        k32.FreeConsole()

        k32.WaitForSingleObject(info.hProcess, 30000)
        code = wt.DWORD()
        k32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        k32.CloseHandle(info.hThread)
        k32.CloseHandle(info.hProcess)

        log = max(session_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
        events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        print(f"=== answer={answer} injected={written.value} exit={code.value} ===")
        print("  类型序列: " + " → ".join(str(event["type"]) for event in events))
        for event in events:
            if str(event["type"]) in {"approval/response", "tool/result", "error/fence"}:
                payload = json.dumps(event["payload"], ensure_ascii=False)
                print(f"  {event['type']} seq={event['seq']} {payload}")
        print(f"  plan.md 改动: {before!r} -> {target.read_bytes()!r}")

    for directory in (workspace, session_dir):
        if directory.exists():
            shutil.rmtree(directory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
