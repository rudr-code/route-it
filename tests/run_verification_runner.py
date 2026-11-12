"""Orchestrates local deployment verification on custom PORT 8050."""
import os
import sys
import time
import shutil
import subprocess
import urllib.request

def main():
    test_port = 8050
    test_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "temp_verify_data"))
    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir, ignore_errors=True)
    os.makedirs(test_data_dir, exist_ok=True)

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    env = os.environ.copy()
    env["PORT"] = str(test_port)
    env["DATA_DIR"] = test_data_dir
    env["PYTHONUNBUFFERED"] = "1"
    env["VERIFY_PORT"] = str(test_port)

    server_log_path = os.path.join(test_data_dir, "server.log")
    server_log = open(server_log_path, "w", encoding="utf-8")

    print(f"[Runner] Launching unified production server on port {test_port} with DATA_DIR={test_data_dir}...")
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=root_dir,
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Poll /health until server is ready
    server_ready = False
    for i in range(30):
        time.sleep(0.5)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{test_port}/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    print(f"[Runner] Server is ready after {(i+1)*0.5:.1f}s.")
                    break
        except Exception:
            if proc.poll() is not None:
                out, _ = proc.communicate()
                print(f"[Runner] Server died unexpectedly:\n{out}")
                sys.exit(1)

    if not server_ready:
        print("[Runner] Timed out waiting for server /health.")
        proc.kill()
        sys.exit(1)

    # Run verification test script
    print("[Runner] Executing verify_deployment.py...")
    test_proc = subprocess.run(
        [sys.executable, os.path.join("tests", "verify_deployment.py")],
        cwd=root_dir,
        env=env,
        capture_output=True,
        text=True
    )

    print(test_proc.stdout)
    if test_proc.stderr:
        print("[STDERR]", test_proc.stderr)

    # Shutdown server
    print("[Runner] Shutting down verification server...")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    # Print server log if verification failed
    if test_proc.returncode != 0:
        if os.path.exists(server_log_path):
            server_log.close()
            with open(server_log_path, "r", encoding="utf-8") as f:
                print("\n[SERVER LOG ON FAILURE]:\n", f.read()[-2000:])
        print("[Runner] Verification FAILED.")
        sys.exit(1)
    else:
        server_log.close()
        shutil.rmtree(test_data_dir, ignore_errors=True)
        print("[Runner] Verification SUCCESSFUL.")
        sys.exit(0)

if __name__ == "__main__":
    main()
