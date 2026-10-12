"""Single-container Railway/Docker launcher.

Runs the webhook API and, when explicitly enabled, one scheduler process.
Do not run more than one replica with SQLite or the local scheduler.
"""
import os
import signal
import subprocess
import sys
import time


def run():
    enabled = os.getenv('PPM_SCHEDULER_ENABLED','false').strip().lower() == 'true'
    port = int(os.getenv('PORT', '8080'))
    workers = []

    def stop(*_):
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
        for worker in workers:
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if enabled:
            workers.append(subprocess.Popen([sys.executable, '-m', 'app.scheduler']))
            print('PPM scheduler enabled (publishing still controlled by separate gate).', flush=True)
        else:
            print('PPM scheduler disabled. Enable with PPM_SCHEDULER_ENABLED=true after testing.', flush=True)
        workers.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                         '--host', '0.0.0.0', '--port', str(port), '--workers', '1']))
        while True:
            for worker in workers:
                status = worker.poll()
                if status is not None:
                    print(f'PPM child exited with code {status}; restarting is required.', flush=True)
                    stop()
            time.sleep(1)
    finally:
        stop()

if __name__ == '__main__':
    run()
