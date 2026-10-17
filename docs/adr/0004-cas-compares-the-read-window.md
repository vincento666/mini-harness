# `edit` 的 CAS 比的是那次 `read` 返回的窗口，不是整个文件

M2（change `m2-file-tools-and-fences`）的写前必读与 CAS 依赖一个事实载体：日志里那次 `read` 的 `tool/result.content`。它只有窗口的内容，所以 `edit` 的比对也只能是窗口——后来的人看到「文件被别人改过而 `edit` 仍然成功」时，这不是漏判，是这条取舍的结果。

1. **比对的形状。** `tools/file_tools.py::edit_file` 把当前文件按那次 `read` 的 `offset` 与 `limit` 重新切出窗口（`_numbered_window(body, prior.offset, prior.limit)`），与那次 `read` 返回的内容逐行比对，不一致才是 `STALE_EDIT`。**窗口之外的改动不触发 `STALE_EDIT`**：实测 `read` 用 `offset=1 limit=1` 读过第 1 行后，把第 3 行改掉，`edit` 仍是 `OK` 并改写文件。
2. **为什么这样判。** 「算不算读过」与「读到的是什么」只由日志前缀派生（ADR-0002 第 5 条那条不变量的具体化），载体就是那条 `tool/result`。要比整个文件，就得把全文指纹写进日志：`read` 的默认窗口是 2000 行、本身可能截断，指纹进日志让日志变大，也让「日志只追加事实」多出一类派生事实。
3. **代价与判据现状。** 「读过之后文件在 session 之外被改动」只在**窗口被改动**那一半有判据（`tests/test_file_edit.py::test_editing_a_file_changed_outside_the_session_is_stale`）；**窗口外**那一半既没有判据、也没有测试钉住现状行为，记在 `docs/CURRENT.md` 的已知缺口里。规格里的措辞「替换时的文件内容 MUST 与该次 `read` 返回的内容一致」按窗口读法解释——这条读法本身是决定，不是规格自带的。

Considered options：把全文哈希写进 `tool/result` 再比整文件（否：改 payload 形状、日志变大，而默认 2000 行窗口下「整文件」本来就不一定在日志里）；要求 `edit` 之前必须是整读（否：大文件整读超窗口，等于禁止改大文件）；接受窗口语义并把它写进规格与这份 ADR（选了）。

M3 若要收紧，改的是 CAS 的比对对象（`tool/result` 里加内容指纹，或规定 `edit` 只接受整读前缀），不是加新的 `ToolOutcome` 取值。

覆盖的 change：`openspec/changes/m2-file-tools-and-fences/`（specs/file-tools 的「`edit` 是字面替换且受 CAS 约束」那条 Requirement）。
