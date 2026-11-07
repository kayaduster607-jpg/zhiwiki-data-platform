"""Read-only single-host deployment preflight; never opens environment files."""

import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

from .common import load_service_settings, safe_path


def _check(code, status, message):
    return {"code": code, "status": status, "message": message}


def _directory_checks(settings, backup_dir):
    """Inspect existing paths only; do not create files or modify the database."""
    checks = []
    data = safe_path(settings.data_dir)
    if not data.is_dir():
        checks.append(_check("data_directory", "fail", "数据目录不存在或不是目录。"))
    else:
        access = os.access(data, os.R_OK | os.W_OK | os.X_OK)
        checks.append(_check("data_directory", "pass" if access else "fail",
                             "当前进程的目录权限检查通过；部署账户需另行验证。" if access else "当前进程无所需的目录访问权限。"))
        try:
            free = shutil.disk_usage(data).free
            checks.append(_check("free_space", "pass" if free >= 512 * 1024 * 1024 else "fail",
                                 "可用空间达到最低 512 MiB 检查线。" if free >= 512 * 1024 * 1024 else "可用空间不足 512 MiB。"))
        except OSError:
            checks.append(_check("free_space", "fail", "无法读取数据目录可用空间。"))
    if not backup_dir:
        checks.append(_check("backup_directory", "fail", "必须显式指定已存在的备份根目录。"))
    else:
        backup = safe_path(backup_dir)
        if backup == data or data in backup.parents or backup in data.parents:
            checks.append(_check("backup_directory", "fail", "备份根目录须与数据目录互不包含。"))
        elif not backup.is_dir() or not os.access(backup, os.W_OK | os.X_OK):
            checks.append(_check("backup_directory", "fail", "备份根目录不存在或当前进程不能写入。"))
        else:
            checks.append(_check("backup_directory", "pass", "备份根目录独立且当前进程可访问；未执行备份。"))
    return checks


def _worker_checks(settings):
    worker = Path(settings.worker_python)
    if not worker.is_file() or not os.access(worker, os.X_OK):
        return [_check("worker_interpreter", "fail", "配置的 worker 解释器不存在或当前进程不可执行。")]
    checks = [_check("worker_interpreter", "pass", "已找到 worker 解释器；尚未启动或验证其运行状态。")]
    try:
        same_interpreter = worker.resolve() == Path(sys.executable).resolve()
    except OSError:
        same_interpreter = False
    if same_interpreter:
        found = importlib.util.find_spec("pypdf") is not None
        checks.append(_check("pdf_parser", "pass" if found else "fail",
                             "当前解释器可以定位 pypdf；版本和子进程运行仍需验证。" if found else "当前解释器缺少 pypdf，PDF 导入不能运行。"))
    else:
        checks.append(_check("pdf_parser", "unknown", "独立 worker 环境的 pypdf 和实际运行状态需要现场验证。"))
    return checks


def run_preflight(config_path, backup_dir=None):
    """Return evidence with explicit unknowns; never claim enterprise readiness."""
    if not config_path:
        raise ValueError("需要显式提供 JSON 配置路径")
    settings = load_service_settings(config_path)
    checks = []
    checks.append(_check("secure_cookie", "pass" if settings.cookie_secure else "fail",
                         "Secure Cookie 已启用。" if settings.cookie_secure else "Secure Cookie 未启用，仅适合本机演示。"))
    domains = [host for host in settings.allowed_hosts if host not in ("localhost", "127.0.0.1", "testserver")]
    valid_domains = [host for host in domains if not host.endswith(".example")]
    checks.append(_check("deployment_host", "pass" if valid_domains else "fail",
                         "已配置非示例主机名；域名归属与 DNS 需另行验证。" if valid_domains else "请配置实际主机名，不能只使用本机或示例域名。"))
    checks.extend(_directory_checks(settings, backup_dir))
    checks.extend(_worker_checks(settings))
    for code, message in (
        ("tls_proxy", "TLS 证书、反向代理及转发头覆盖需要实际部署验证。"),
        ("worker_health", "worker 进程监督、心跳和失败告警需要运行环境验证。"),
        ("backup_restore", "定时备份、隔离副本、恢复演练和 RPO/RTO 未由本命令验证。"),
        ("storage_security", "部署账户权限、磁盘加密、容量配额和异地隔离需要验证。"),
        ("monitoring", "指标持久化、告警、日志保留和当班响应需要验证。"),
    ):
        checks.append(_check(code, "unknown", message))
    return {"checks": checks, "blocking_checks_passed": not any(item["status"] == "fail" for item in checks),
            "production_ready": False, "note": "未知项及目标环境验收完成前，不可认定生产就绪。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="单机团队服务只读部署预检，不读取 .env")
    parser.add_argument("--config", required=True, help="显式 JSON 配置路径")
    parser.add_argument("--backup-dir", help="已存在的备份根目录")
    args = parser.parse_args(argv)
    try:
        report = run_preflight(args.config, args.backup_dir)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Config content and filesystem paths must not enter logs.
        report = {"checks": [_check("configuration", "fail", "配置不可读、无效或路径不允许。")],
                  "blocking_checks_passed": False, "production_ready": False}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["blocking_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
