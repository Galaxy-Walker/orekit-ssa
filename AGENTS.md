# AGENTS.md

## 项目定位

基于 **Orekit 13.1** 的 Python 空间态势感知（SSA）原型仓库（早期阶段，无测试/无 lint/无 CI）。

- `main.py` — 唯一示例：开普勒轨道传播，已验证可运行
- `docs/tutorials/` — 自写中文教程（官方 Java 教程 ↔ `orekit_jpype` 对照），含本仓库踩坑经验，动手前先查
- `docs/orekit-javadoc/`、`data/orekit-data-main/` — 本地参考副本（均未纳入 git，勿视为源）
- `data/orekit-data-main/` 自带独立 `pyproject.toml`（嵌套 uv 项目），不要在其中执行 uv 命令

## 常用命令

```bash
uv sync                              # 安装依赖（含 git 源 orekitdata）
uv run python main.py                # 运行示例
```

无测试框架。改完代码用 `uv run python main.py` 手动验证。

## orekit_jpype 关键约束（容易踩坑）

- v13 起模块名是 **`orekit_jpype`**，老资料里的 `import orekit` 已过时
- `initVM()` 每进程只能调用一次；**所有 `org.*`/`java.*` 导入必须在 `initVM()` 之后**（故 main.py 把导入写在函数内）
- JVM 里的 Java 包对静态分析器不可见：`reportMissingImports` 等误报属正常（.vscode/settings.json 已关闭），不要尝试"修复"成真实依赖
- 需本机已装 JDK 11+（当前环境为 JDK 21）
- Python 实现 Java 接口必须用 `@JImplements` + `@JOverride`，且**接口内所有方法（含 default 方法）都要实现**，否则 Java 侧报 `NoSuchMethodError`
- 角度一律**弧度**（`FastMath.toRadians`）；double 字面量要写 `.0`（如 `8000000.0`），否则可能命中错误的重载方法
- 数据加载两种等价方式：`orekit_jpype.pyhelpers.setup_orekit_data()`（教程用），或手动 `DirectoryCrawler(orekitdata.__path__)`（main.py 用）

## 其他事实

- Python 3.14（`.python-version`），包管理只用 uv
- 教程的"运行方式"示例指向 `docs/tutorials/0X-*.py`，但这些 **.py 文件并不存在**，代码需从 md 中复制
- 代码注释与 git 提交信息使用中文；README.md 为空
