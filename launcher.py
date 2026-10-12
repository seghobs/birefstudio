"""Install, build and supervise the local studio using one Windows launcher."""
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from windows_job import WindowsJob

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
LOGS = ROOT / "logs"
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run(command, cwd=ROOT, env=None):
    result = subprocess.run(command, cwd=cwd, env=env)
    if result.returncode:
        raise RuntimeError("Kurulum veya derleme basarisiz. Yukaridaki hata mesajini kontrol edin.")


def wait_http(url, child, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError("Sunucu baslatilamadi. logs klasorundeki kayitlari kontrol edin.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError("Sunucu zamaninda acilmadi. logs klasorunu kontrol edin.")


def main():
    if not (3, 12) <= sys.version_info[:2] < (3, 14):
        raise RuntimeError("Python 3.12 veya 3.13 kurun (onerilen: 3.12).")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    node = shutil.which("node")
    if not npm or not node:
        raise RuntimeError("Node.js 22 veya 24 LTS kurun: https://nodejs.org")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    if tuple(int(p) for p in version.split(".")[:2]) < (20, 9):
        raise RuntimeError("Node.js surumu en az 20.9 olmali; 22 veya 24 LTS onerilir.")
    api_port = int(os.environ.get("STUDIO_API_PORT", "8000"))
    web_port = int(os.environ.get("STUDIO_WEB_PORT", "3000"))
    if api_port == web_port or not all(1024 <= p <= 65535 for p in (api_port, web_port)):
        raise RuntimeError("Web ve API icin farkli, 1024-65535 arasi portlar kullanin.")
    for port in (api_port, web_port):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeError(f"{port} portu kullanimda. Acik studyo penceresini kapatin veya baska port secin.") from None
    LOGS.mkdir(exist_ok=True)
    if not PYTHON.exists():
        print("[1/4] Python ortami hazirlaniyor...", flush=True)
        run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    forced_device = os.environ.get("STUDIO_DEVICE", "auto").lower()
    if forced_device not in {"auto", "cpu", "cuda"}:
        raise RuntimeError("STUDIO_DEVICE auto, cpu veya cuda olmali.")
    nvidia = shutil.which("nvidia-smi")
    cuda = False
    if nvidia and forced_device != "cpu":
        try:
            cuda = subprocess.run([nvidia, "--query-gpu=name", "--format=csv,noheader"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    if forced_device == "cuda" and not cuda:
        raise RuntimeError("NVIDIA ekran karti/surucusu bulunamadi.")
    torch_req = ROOT / "backend" / ("requirements-torch-cuda.txt" if cuda else "requirements-torch-cpu.txt")
    torch_hash = fingerprint([torch_req])
    torch_marker = ROOT / ".venv/studio-torch.sha256"
    if not torch_marker.exists() or torch_marker.read_text() != torch_hash:
        print(f"[1/4] Yapay zeka motoru hazirlaniyor ({'NVIDIA CUDA' if cuda else 'CPU'})...", flush=True)
        run([str(PYTHON), "-m", "pip", "install", "-r", str(torch_req)])
        torch_marker.write_text(torch_hash)
    req_hash = fingerprint([ROOT / "requirements.txt", ROOT / "backend/requirements.txt", ROOT / "backend/requirements-lock.txt"])
    marker = ROOT / ".venv/studio-requirements.sha256"
    if not marker.exists() or marker.read_text() != req_hash:
        print("[1/4] Python paketleri kuruluyor (ilk acilista internet gerekir)...", flush=True)
        run([str(PYTHON), "-m", "pip", "install", "-r", "requirements.txt"])
        marker.write_text(req_hash)
    package_hash = fingerprint([FRONTEND / "package.json", FRONTEND / "package-lock.json"])
    package_marker = FRONTEND / "node_modules/.studio-packages.sha256"
    if not package_marker.exists() or package_marker.read_text() != package_hash:
        print("[2/4] Arayuz paketleri kuruluyor...", flush=True)
        run([npm, "ci", "--no-fund", "--no-audit"], cwd=FRONTEND)
        package_marker.write_text(package_hash)
    env = os.environ.copy()
    env["API_URL"] = f"http://127.0.0.1:{api_port}"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    source_paths = [p for folder in ("app", "lib", "public") for p in (FRONTEND / folder).rglob("*") if p.is_file()]
    source_paths += [FRONTEND / p for p in ("next.config.ts", "tsconfig.json", "package-lock.json")]
    build_hash = fingerprint(source_paths) + env["API_URL"]
    build_marker = FRONTEND / ".next/studio-build.sha256"
    if not (FRONTEND / ".next/BUILD_ID").exists() or not build_marker.exists() or build_marker.read_text() != build_hash:
        print("[3/4] Arayuz hazirlaniyor...", flush=True)
        run([npm, "run", "build"], cwd=FRONTEND, env=env)
        # Next may update tsconfig during the first build.
        build_marker.write_text(fingerprint(source_paths) + env["API_URL"])
    print("[4/4] Studyo aciliyor...", flush=True)
    processes = []
    handles = []
    process_job = WindowsJob()
    try:
        for name, command, cwd, url in (
            ("backend", [str(PYTHON), "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(api_port)], ROOT, f"http://127.0.0.1:{api_port}/api/health"),
            ("frontend", [node, str(FRONTEND / "node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", str(web_port)], FRONTEND, f"http://127.0.0.1:{web_port}"),
        ):
            handle = (LOGS / f"{name}.log").open("w", encoding="utf-8")
            handles.append(handle)
            child = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            processes.append(child)
            process_job.add(child)
            wait_http(url, child)
        url = f"http://127.0.0.1:{web_port}"
        print(f"\nBiRef Studio hazir: {url}\nKapatmak icin bu pencerede Ctrl+C basin.\nKayitlar: logs klasoru\n", flush=True)
        if os.environ.get("STUDIO_NO_BROWSER") != "1":
            webbrowser.open(url)
        while all(child.poll() is None for child in processes):
            time.sleep(1)
        raise RuntimeError("Sunuculardan biri kapandi. logs klasorunu kontrol edin.")
    except KeyboardInterrupt:
        print("\nStudyo kapatiliyor...", flush=True)
    finally:
        for child in reversed(processes):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for handle in handles:
            handle.close()
        process_job.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nHATA: {error}", file=sys.stderr)
        sys.exit(1)
