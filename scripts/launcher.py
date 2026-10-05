#!/usr/bin/env python3
"""AI 学习助手 - 跨平台启动器（仅使用 Python 标准库）

用法:
    python scripts/launcher.py setup   [--mirror] [--force]
    python scripts/launcher.py start   [--port 8000] [--host 0.0.0.0] [--no-browser] [--reload] [--mirror]
    python scripts/launcher.py stop    [--port 8000]
    python scripts/launcher.py status  [--port 8000]
    python scripts/launcher.py doctor  [--port 8000]

设计说明:
  * Windows 与 Linux/macOS 共用这一份实现，两个平台各只有极薄的 shell/bat 垫片。
  * 只用标准库，因此在依赖尚未安装（venv 还不存在）时也能运行。
  * 输出**只用 ASCII 标记** [OK] [FAIL] [WARN] [INFO]，
    因为 Windows 控制台默认代码页（GBK/cp936）无法编码对勾、叉号等符号，
    直接打印会抛 UnicodeEncodeError。
"""
import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

# --------------------------------------------------------------------------
# 路径与常量
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
VENV = BACKEND / "venv"
REQUIREMENTS = BACKEND / "requirements.txt"
SMOKE_TEST = BACKEND / "scripts" / "smoke_test.py"
PID_FILE = ROOT / ".uvicorn.pid"
LOG_FILE = BACKEND / "uvicorn.log"
AI_CONFIG = BACKEND / "ai_config.json"
DB_FILE = BACKEND / "study_assistant.db"

IS_WINDOWS = os.name == "nt"
MIN_PYTHON = (3, 9)
MIRROR_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
HEALTH_TIMEOUT = 25.0


# --------------------------------------------------------------------------
# 输出（全 ASCII）
# --------------------------------------------------------------------------
def _prepare_stdout() -> None:
    """尽量把标准输出切到 UTF-8，避免中文在 Windows 控制台乱码"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def say(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def ok(msg: str) -> None:
    say("OK", msg)


def info(msg: str) -> None:
    say("INFO", msg)


def warn(msg: str) -> None:
    say("WARN", msg)


def fail(msg: str) -> None:
    say("FAIL", msg)


def rule(title: str = "") -> None:
    print("=" * 64)
    if title:
        print(title)
        print("=" * 64)


# --------------------------------------------------------------------------
# 平台差异（全部集中在这几个函数里）
# --------------------------------------------------------------------------
def venv_python() -> Path:
    """虚拟环境里的解释器路径"""
    if IS_WINDOWS:
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def running_inside_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == venv_python().resolve()
    except Exception:
        return False


def spawn_detached(cmd, cwd: Path, log_path: Path):
    """启动一个与当前进程脱钩的子进程，输出追加到日志"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8", errors="replace")

    kwargs = dict(
        cwd=str(cwd),
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    if IS_WINDOWS:
        # 脱离当前控制台与进程组，脚本退出后服务继续运行
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(cmd, **kwargs), log


def pid_alive(pid: int) -> bool:
    try:
        if IS_WINDOWS:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=10,
            )
            return str(pid) in (r.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def kill_pid(pid: int, force: bool = False) -> bool:
    try:
        if IS_WINDOWS:
            args = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                args.append("/F")
            r = subprocess.run(args, capture_output=True, text=True, timeout=15)
            return r.returncode == 0
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        return True
    except Exception:
        return False


def pids_on_port(port: int):
    """尽力找出监听该端口的进程 PID（取不到就返回空列表）"""
    pids = []
    try:
        if IS_WINDOWS:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[3].upper() == "LISTENING" \
                        and parts[1].endswith(f":{port}"):
                    try:
                        pids.append(int(parts[4]))
                    except ValueError:
                        pass
        else:
            out = subprocess.run(
                ["ss", "-tlnpH"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            for line in out.splitlines():
                if f":{port} " not in line:
                    continue
                for m in re.finditer(r"pid=(\d+)", line):
                    pids.append(int(m.group(1)))
    except Exception:
        pass
    return sorted(set(pids))


# --------------------------------------------------------------------------
# 共性工具
# --------------------------------------------------------------------------
def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0


def health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=2.5
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def describe_port_owner(port: int) -> str:
    pids = pids_on_port(port)
    if pids:
        return f"PID {'/'.join(str(p) for p in pids)}"
    try:
        if not IS_WINDOWS:
            out = subprocess.run(
                ["ss", "-tlnp"], capture_output=True, text=True, timeout=8
            ).stdout
            for line in out.splitlines():
                if f":{port} " in line:
                    return line.strip()
    except Exception:
        pass
    return ""


def print_log_tail(lines: int = 30) -> None:
    if not LOG_FILE.exists():
        info(f"（暂无日志文件 {LOG_FILE}）")
        return
    try:
        content = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        warn(f"读取日志失败: {e}")
        return
    print("-" * 64)
    for line in content[-lines:]:
        print("  " + line)
    print("-" * 64)


def check_python_version() -> bool:
    v = sys.version_info
    if v < MIN_PYTHON:
        fail(f"Python 版本过低: {v.major}.{v.minor}，需要 "
             f">= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
        info("下载地址: https://www.python.org/downloads/")
        return False
    if v >= (3, 14):
        warn(f"Python {v.major}.{v.minor} 较新，个别依赖可能尚无预编译 wheel；"
             "若安装依赖失败，可尝试 Python 3.12 / 3.13")
    return True


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------
def create_venv() -> bool:
    info(f"创建虚拟环境: {VENV}")
    try:
        import venv as venv_mod
        venv_mod.create(str(VENV), with_pip=True)
    except Exception as e:
        fail(f"创建虚拟环境失败: {e}")
        if not IS_WINDOWS:
            info("Debian/Ubuntu 可能需要先安装: sudo apt install python3-venv")
        info("也可手动执行: python -m venv backend/venv")
        return False
    ok("虚拟环境已创建")
    return True


def cmd_setup(args) -> int:
    rule("AI 学习助手 - 环境准备")
    if not check_python_version():
        return 1

    if running_inside_venv():
        info("检测到当前已在项目虚拟环境中运行")

    info(f"项目根目录: {ROOT}")
    info(f"系统 Python: {sys.version.split()[0]}  ({sys.executable})")
    print()

    if not REQUIREMENTS.exists():
        fail(f"找不到依赖清单: {REQUIREMENTS}")
        return 1

    # 1) 虚拟环境（幂等）
    if VENV.exists() and not args.force:
        ok(f"复用已有虚拟环境: {VENV}")
    else:
        if VENV.exists():
            info("--force 指定：删除并重建虚拟环境")
            shutil.rmtree(VENV, ignore_errors=True)
        if not create_venv():
            return 1

    py = venv_python()
    if not py.exists():
        fail(f"虚拟环境缺少解释器: {py}")
        return 1

    # 2) 依赖
    info("升级 pip ...")
    subprocess.run(
        [str(py), "-m", "pip", "install", "--upgrade", "pip", "-q"],
        cwd=str(BACKEND), check=False,
    )

    cmd = [str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    if args.mirror:
        cmd += ["-i", MIRROR_URL]
        info(f"使用镜像源: {MIRROR_URL}")

    info("安装依赖（首次可能需要几分钟）...")
    rc = subprocess.run(cmd, cwd=str(BACKEND)).returncode
    if rc != 0:
        fail("依赖安装失败")
        if not args.mirror:
            info("国内网络可重试: python scripts/launcher.py setup --mirror")
        return 1
    ok("依赖安装完成")

    # 3) 自检
    print()
    info("运行环境自检 ...")
    if SMOKE_TEST.exists():
        rc = subprocess.run([str(py), str(SMOKE_TEST)], cwd=str(BACKEND)).returncode
        if rc == 0:
            ok("自检通过")
        else:
            warn("自检未通过；启动通常仍可用，但建议按上面的报错排查")
    else:
        warn(f"未找到自检脚本 {SMOKE_TEST}，跳过")

    print()
    ok("环境准备完成")
    info("下一步: python scripts/launcher.py start"
         "   （Windows 双击 start.bat / Linux 执行 ./start.sh）")
    return 0


# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------
def cmd_start(args) -> int:
    rule("AI 学习助手 - 启动")

    py = venv_python()
    if not py.exists():
        info("未检测到虚拟环境，先自动完成环境准备 ...")
        print()
        rc = cmd_setup(argparse.Namespace(mirror=args.mirror, force=False))
        if rc != 0:
            return rc
        print()

    if port_in_use(args.port):
        fail(f"端口 {args.port} 已被占用")
        owner = describe_port_owner(args.port)
        if owner:
            info(f"占用者: {owner}")
        info(f"换个端口: python scripts/launcher.py start --port {args.port + 1}")
        info(f"先停止旧的: python scripts/launcher.py stop --port {args.port}")
        return 1

    cmd = [
        str(py), "-m", "uvicorn", "app.main:app",
        "--host", args.host, "--port", str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")

    info(f"监听地址: {args.host}:{args.port}")
    info(f"日志文件: {LOG_FILE}")

    try:
        proc, log = spawn_detached(cmd, BACKEND, LOG_FILE)
    except Exception as e:
        fail(f"启动失败: {e}")
        return 1
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")

    # 等待真正就绪（而不是假定它起来了）
    deadline = time.time() + HEALTH_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            fail(f"服务进程已退出（退出码 {proc.returncode}）")
            print_log_tail()
            PID_FILE.unlink(missing_ok=True)
            return 1
        if health_ok(args.port):
            log.close()
            print()
            ok("服务已启动")
            url = f"http://localhost:{args.port}"
            info(f"访问地址: {url}")
            info(f"API 文档: {url}/docs")
            info(f"进程 PID: {proc.pid}")
            info(f"停止服务: python scripts/launcher.py stop --port {args.port}")
            print()
            info("首次使用请在页面左下角 [AI 设置] 填入 API 地址与 Key")
            if not args.no_browser:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            return 0
        time.sleep(0.4)

    fail(f"等待服务就绪超时（{HEALTH_TIMEOUT:.0f} 秒）")
    print_log_tail()
    return 1


# --------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------
def cmd_stop(args) -> int:
    rule("AI 学习助手 - 停止")
    stopped = set()

    # 1) 按 PID 文件
    if PID_FILE.exists():
        raw = PID_FILE.read_text(encoding="utf-8", errors="replace").strip()
        try:
            pid = int(raw)
        except ValueError:
            pid = None
            warn(f"PID 文件内容异常，忽略: {raw!r}")
        if pid is not None:
            if pid_alive(pid):
                if kill_pid(pid):
                    stopped.add(pid)
                    ok(f"已请求结束进程 PID {pid}")
                else:
                    warn(f"无法结束 PID {pid}（可能需要管理员权限）")
            else:
                info(f"PID {pid} 已不存在（PID 文件过期）")
        PID_FILE.unlink(missing_ok=True)

    # 2) 兜底：按端口找占用者（可能与上面命中同一个 PID，用集合去重）
    for pid in pids_on_port(args.port):
        if pid in stopped:
            continue
        if kill_pid(pid):
            stopped.add(pid)
            ok(f"已结束占用端口 {args.port} 的进程 PID {pid}")

    # 3) 等待并如实校验端口是否真的释放
    for _ in range(20):
        if not port_in_use(args.port):
            break
        time.sleep(0.3)

    if port_in_use(args.port):
        fail(f"端口 {args.port} 仍被占用，未能停止")
        owner = describe_port_owner(args.port)
        if owner:
            info(f"占用者: {owner}")
        info("可手动结束该进程后重试")
        return 1

    if stopped:
        pids = ", ".join(f"PID {p}" for p in sorted(stopped))
        ok(f"服务已停止（{pids}）")
    else:
        ok("没有正在运行的服务")
    return 0


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
def cmd_status(args) -> int:
    rule("AI 学习助手 - 状态")
    if health_ok(args.port):
        ok(f"服务正在运行，健康检查通过（端口 {args.port}）")
        info(f"访问地址: http://localhost:{args.port}")
        info(f"API 文档: http://localhost:{args.port}/docs")
    elif port_in_use(args.port):
        warn(f"端口 {args.port} 已被占用，但 /health 未通过（可能仍在启动，或不是本服务）")
        owner = describe_port_owner(args.port)
        if owner:
            info(f"占用者: {owner}")
    else:
        info(f"服务未运行（端口 {args.port} 空闲）")

    if PID_FILE.exists():
        info(f"PID 文件: {PID_FILE.read_text(encoding='utf-8', errors='replace').strip()}")
    info(f"日志文件: {LOG_FILE}")
    return 0


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------
def cmd_doctor(args) -> int:
    rule("AI 学习助手 - 环境诊断")
    info(f"操作系统: {platform.platform()}")
    info(f"平台标识: {sys.platform} / os.name={os.name}")
    info(f"Python  : {sys.version.split()[0]}  ({sys.executable})")

    healthy = True

    if sys.version_info < MIN_PYTHON:
        fail(f"Python 版本过低，需要 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
        healthy = False
    else:
        ok("Python 版本满足要求（>= 3.9）")

    print()
    info(f"项目根目录: {ROOT}")
    if BACKEND.exists():
        ok(f"后端目录存在: {BACKEND}")
    else:
        fail(f"后端目录缺失: {BACKEND}")
        healthy = False

    py = venv_python()
    if py.exists():
        ok(f"虚拟环境: {py}")
        r = subprocess.run(
            [str(py), "-c",
             "import fastapi,uvicorn,sqlalchemy,pymupdf,openai,cryptography"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            ok("关键依赖可导入: fastapi uvicorn sqlalchemy pymupdf openai cryptography")
        else:
            fail("关键依赖导入失败")
            tail = (r.stderr or "").strip().splitlines()
            if tail:
                info(f"  最后一行: {tail[-1]}")
            info("  修复: python scripts/launcher.py setup")
            healthy = False
    else:
        warn(f"虚拟环境不存在: {py}")
        info("  修复: python scripts/launcher.py setup")
        healthy = False

    print()
    if port_in_use(args.port):
        warn(f"端口 {args.port} 已被占用")
        owner = describe_port_owner(args.port)
        if owner:
            info(f"  占用者: {owner}")
    else:
        ok(f"端口 {args.port} 空闲")

    print()
    if AI_CONFIG.exists():
        try:
            data = json.loads(AI_CONFIG.read_text(encoding="utf-8"))
            model = data.get("model", "?")
            base = data.get("api_base_url", "?")
            if data.get("api_key"):
                ok(f"AI 已配置  模型={model}  地址={base}")
                info("  （Key 已加密存储，此处不显示）")
            else:
                warn("AI 配置存在但缺少 Key -> 启动后在网页 [AI 设置] 里填写")
        except Exception as e:
            warn(f"ai_config.json 解析失败: {e}")
            healthy = False
    else:
        warn("尚未配置 AI（backend/ai_config.json 不存在）")
        info("  -> 启动服务后，在页面左下角 [AI 设置] 填入 API 地址与 Key")

    print()
    info(f"数据库  : {'已创建' if DB_FILE.exists() else '尚未创建（首次启动会自动建表）'}")
    info(f"           {DB_FILE}")
    info(f"上传目录: {BACKEND / 'uploads'}")
    info(f"日志文件: {LOG_FILE}")
    info(f"PID 文件: {PID_FILE}")

    print()
    if healthy:
        ok("诊断结论: 环境就绪，可以启动")
    else:
        warn("诊断结论: 存在待处理项，见上面的 [FAIL]/[WARN]")
    return 0


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="launcher.py",
        description="AI 学习助手跨平台启动器（setup / start / stop / status / doctor）",
    )
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("setup", help="创建虚拟环境并安装依赖")
    s.add_argument("--mirror", action="store_true", help="使用国内 PyPI 镜像")
    s.add_argument("--force", action="store_true", help="删除并重建虚拟环境")
    s.set_defaults(func=cmd_setup)

    def add_port_host(parser):
        parser.add_argument("--port", type=int, default=8000, help="端口（默认 8000）")
        parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")

    st = sub.add_parser("start", help="启动服务")
    add_port_host(st)
    st.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    st.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重载")
    st.add_argument("--mirror", action="store_true", help="缺环境时用国内镜像安装")
    st.set_defaults(func=cmd_start)

    sp = sub.add_parser("stop", help="停止服务")
    sp.add_argument("--port", type=int, default=8000, help="端口（默认 8000）")
    sp.set_defaults(func=cmd_stop)

    ss = sub.add_parser("status", help="查看服务状态")
    ss.add_argument("--port", type=int, default=8000, help="端口（默认 8000）")
    ss.set_defaults(func=cmd_status)

    dr = sub.add_parser("doctor", help="环境诊断（排查问题的第一步）")
    dr.add_argument("--port", type=int, default=8000, help="端口（默认 8000）")
    dr.set_defaults(func=cmd_doctor)

    return p


def main(argv=None) -> int:
    _prepare_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print()
        info("已取消")
        return 130
    except Exception as e:
        fail(f"意外错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
