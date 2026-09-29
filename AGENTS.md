# AGENTS.md

## 项目定位

基于 **Orekit 13.1** 的 Python 空间态势感知（SSA）原型仓库（阶段 1，标准库 unittest，无 lint/无 CI）。

- `main.py` — 轨道传播装配入口，支持开普勒 / 数值传播及日月第三体摄动
- `ssa/domain.py`、`ssa/propagation.py` — 纯 Python 数据模型与传播端口，不依赖 Java
- `ssa/orekit/` — JVM、数据、传播器、力模型适配层；Java 对象不得泄漏到核心层
- `docs/architecture/stage-1-propagation.md` — 阶段 1 架构与后续扩展契约
- `tests/` — 传播物理回归与接口契约验证
- `docs/tutorials/` — 自写中文教程（官方 Java 教程 ↔ `orekit_jpype` 对照），含本仓库踩坑经验，动手前先查
- `docs/orekit-javadoc/`、`data/orekit-data-main/` — 本地参考副本（均未纳入 git，勿视为源）
- `data/orekit-data-main/` 自带独立 `pyproject.toml`（嵌套 uv 项目），不要在其中执行 uv 命令

## 常用命令

```bash
uv sync                              # 安装依赖（含 git 源 orekitdata）
uv run python main.py                # 运行示例
uv run python -m unittest discover -s tests -v  # 物理回归与契约验证
```

改完代码运行示例及标准库 unittest 验证。

## orekit_jpype 关键约束（容易踩坑）

- v13 起模块名是 **`orekit_jpype`**，老资料里的 `import orekit` 已过时
- `initVM()` 每进程只能调用一次；**所有 `org.*`/`java.*` 导入必须在 `initVM()` 之后**（统一通过 `initialize_orekit()` 初始化）
- JVM 里的 Java 包对静态分析器不可见：`reportMissingImports` 等误报属正常（.vscode/settings.json 已关闭），不要尝试"修复"成真实依赖
- 需本机已装 JDK 11+（当前环境为 JDK 21）
- Python 实现 Java 接口必须用 `@JImplements` + `@JOverride`，且**接口内所有方法（含 default 方法）都要实现**，否则 Java 侧报 `NoSuchMethodError`
- 角度一律**弧度**（`FastMath.toRadians`）；double 字面量要写 `.0`（如 `8000000.0`），否则可能命中错误的重载方法
- 数据加载两种等价方式：`orekit_jpype.pyhelpers.setup_orekit_data()`（教程用），或 `DirectoryCrawler`（`ssa/orekit/runtime.py` 用）

## 其他事实

- Python 3.14（`.python-version`），包管理只用 uv
- 部分教程提供 `docs/tutorials/py-examples/` 可运行示例；旧的 `docs/tutorials/0X-*.py` 路径不存在
- 代码注释与 git 提交信息使用中文；README.md 提供运行与架构导航
