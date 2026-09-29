"""进程级 JVM 与参考数据生命周期。"""

from pathlib import Path
from threading import Lock

_lock = Lock()
_data_root: Path | None = None


def initialize_orekit(data_dir: str | Path | None = None) -> Path:
    """显式初始化，重复调用幂等；同一进程禁止静默切换参考数据。

    默认使用 uv 安装的 orekitdata 包；也可指定解压后的数据目录。
    不关闭 JVM，不清空调用者已注册的数据提供器。
    """
    global _data_root
    with _lock:
        if _data_root is not None:
            if data_dir is not None and Path(data_dir).resolve() != _data_root:
                raise RuntimeError("本进程已初始化其他 Orekit 数据目录，请使用新进程")
            return _data_root

        if data_dir is None:
            import orekitdata

            root = Path(orekitdata.__path__[0]).resolve()
        else:
            root = Path(data_dir).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Orekit 数据目录不存在：{root}")

        import jpype
        import orekit_jpype

        if not jpype.isJVMStarted():
            orekit_jpype.initVM()

        from java.io import File
        from org.orekit.data import DataContext, DirectoryCrawler
        from org.orekit.time import TimeScalesFactory

        manager = DataContext.getDefault().getDataProvidersManager()
        provider = DirectoryCrawler(File(str(root)))
        manager.addProvider(provider)
        try:
            # 提前验证最基本的 UTC 数据，避免到第一次传播时才发现缺失。
            TimeScalesFactory.getUTC()
        except Exception:
            manager.removeProvider(provider)
            raise
        _data_root = root
        return root


def require_initialized() -> None:
    if _data_root is None:
        raise RuntimeError("请先调用 initialize_orekit() 初始化 JVM 和参考数据")
