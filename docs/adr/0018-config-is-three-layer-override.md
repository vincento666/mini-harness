---
status: accepted
---

# 配置是三层覆盖，不是 patch 层叠；工具表是筛选，不是注册；密钥缺失当场失败

M9 把「一次运行的设置从哪儿来」定成三层**逐键**覆盖（内置默认 < 工作区根 `mini.config.toml` < 命令行 flag；一份文件，不合并、不继承），工具表定成对内置定义的**筛选**而不是可注册的清单，密钥定成装配的必需项：变量未设或为空就在会话开始之前当场失败，不建日志、不发请求。三处都选「当场失败」而不是「跑起来再撞错」，因为装配错了没有一次运行值得被记录；配置文件里因此只放设置类字段，`prompt` 与 `fixture`（属于这一轮，不属于设置）与 `api_key`（密钥只走环境变量的名字）出现即参数错误。

Considered options：照 DSH 做 patch 层叠加环境变量覆盖（否：DSH 那套的动机是多租户与运行时热改，mini 版没有这两个需求，一份 TOML 三层就够，多出来的合并语义全是成本）；配置文件按目录向上找（否：工作区边界是不变量 E 的地基，配置文件在边界之外被捡到等于边界由目录树决定）；`tools` 做成可注册的外部工具（否：M9 没有外部工具，把「筛掉」写成「注册」会让 seam ② 的注册表提前长出插件形状）；密钥缺失照旧发请求、撞 401 再报 `PROVIDER_HTTP_STATUS`（否：那是把装配错误伪装成 provider 故障，且已经建了日志、已经发了请求）；密钥缺失用独立的 `MISSING_API_KEY` 码（否：黑盒里六条配置失败码共用 `INVALID_ARGUMENT` 这一个词已经够判，多一个码只是多一条要判的可达性）。

Consequences：配置文件里的 `sandbox` / `approval` 与命令行同受围栏词表约束——这一条是 `code-review` Spec 轴查出来的：argparse 的 `choices` 只守命令行那一层，配置写 `sandbox = "banana"` 会让围栏既不落 `read-only` 也不落 `workspace-write`，工作区边界那一支整个跳过，等价 `danger-full-access`；实现轮补了 CLI 层的词表判据（退出码 2、`INVALID_ARGUMENT`），词表本身住在 `loop/settings.py` 的 `SANDBOX_LEVELS` / `APPROVAL_MODES`，argparse 的 `choices` 用同一份；`tomllib` 不吃 UTF-8 BOM，Windows 上记事本与 PowerShell 5.1 默认写的 UTF-8 都带 BOM，这种文件报的是「Invalid statement (at line 1, column 1)」而不是「这是 BOM」——要不要在读这一层剥掉 BOM 留给后续裁决（M9 人手验收记下了这条别扭，未动实现）；`ConfigFailure.code` 那六个值只在 seam ② 可见，seam ⑥ 只看得到 `INVALID_ARGUMENT` 与一段文本。
