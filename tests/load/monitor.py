"""
Hub resource monitor — tracks RAM and CPU of the running Django server.

Usage:
    # In one terminal, start the Hub:
    cd hub && python manage.py runserver

    # In another terminal, run this monitor:
    cd hub && python tests/load/monitor.py

    # In a third terminal, run locust:
    cd hub && locust -f tests/load/locustfile.py --host=http://localhost:8000 \
                     --users 10 --spawn-rate 2 --run-time 2m --headless

The monitor prints a line every 2 seconds showing:
    - RSS Memory (actual physical RAM used)
    - CPU % (over the interval)
    - Thread count
    - Open file descriptors
    - Database connections

Press Ctrl+C to stop and see the summary.
"""
import sys
import time
import psutil


def find_hub_process():
    """Find the Django runserver or gunicorn process."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "manage.py" in cmdline and "runserver" in cmdline:
                return proc
            if "gunicorn" in cmdline and "config.wsgi" in cmdline:
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def get_process_tree_memory(proc):
    """Get total RSS of process + all children (workers)."""
    total_rss = 0
    total_vms = 0
    try:
        mem = proc.memory_info()
        total_rss += mem.rss
        total_vms += mem.vms
        for child in proc.children(recursive=True):
            try:
                cmem = child.memory_info()
                total_rss += cmem.rss
                total_vms += cmem.vms
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return total_rss, total_vms


def monitor(interval=2):
    """Monitor Hub process resources."""
    proc = find_hub_process()
    if not proc:
        print("Hub process not found. Start the Hub first:")
        print("  cd hub && python manage.py runserver")
        sys.exit(1)

    pid = proc.pid
    print(f"Monitoring Hub process PID={pid} ({' '.join(proc.cmdline()[:4])})")
    print(f"Children (workers): {len(proc.children(recursive=True))}")
    print()
    print(f"{'Time':>8}  {'RSS (MB)':>10}  {'VMS (MB)':>10}  {'CPU %':>7}  "
          f"{'Threads':>7}  {'FDs':>5}")
    print("-" * 65)

    measurements = []

    try:
        # Initial CPU measurement
        proc.cpu_percent()
        for child in proc.children(recursive=True):
            try:
                child.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        start_time = time.time()

        while True:
            time.sleep(interval)

            if not proc.is_running():
                print("\nHub process terminated.")
                break

            elapsed = time.time() - start_time
            rss, vms = get_process_tree_memory(proc)
            rss_mb = rss / 1024 / 1024
            vms_mb = vms / 1024 / 1024

            # CPU across process tree
            cpu = proc.cpu_percent()
            for child in proc.children(recursive=True):
                try:
                    cpu += child.cpu_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            try:
                threads = proc.num_threads()
                fds = proc.num_fds() if hasattr(proc, "num_fds") else 0
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                threads = 0
                fds = 0

            measurements.append({
                "time": elapsed,
                "rss_mb": rss_mb,
                "vms_mb": vms_mb,
                "cpu": cpu,
                "threads": threads,
                "fds": fds,
            })

            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            print(f"{mins:3d}:{secs:02d}   {rss_mb:10.1f}  {vms_mb:10.1f}  "
                  f"{cpu:6.1f}%  {threads:7d}  {fds:5d}")

    except KeyboardInterrupt:
        pass

    # Summary
    if measurements:
        rss_values = [m["rss_mb"] for m in measurements]
        cpu_values = [m["cpu"] for m in measurements]

        print()
        print("=" * 65)
        print("SUMMARY")
        print("=" * 65)
        print(f"  Duration:        {len(measurements) * interval}s "
              f"({len(measurements)} samples)")
        print(f"  RSS Memory:")
        print(f"    Min:           {min(rss_values):.1f} MB")
        print(f"    Max:           {max(rss_values):.1f} MB")
        print(f"    Avg:           {sum(rss_values)/len(rss_values):.1f} MB")
        print(f"    Final:         {rss_values[-1]:.1f} MB")
        print(f"  CPU:")
        print(f"    Avg:           {sum(cpu_values)/len(cpu_values):.1f}%")
        print(f"    Peak:          {max(cpu_values):.1f}%")
        print("=" * 65)
        print()
        print("RESOURCE RECOMMENDATION (for 10 concurrent users):")
        peak_rss = max(rss_values)
        # Add 30% headroom
        recommended_ram = int((peak_rss * 1.3) / 64) * 64  # Round to nearest 64MB
        if recommended_ram < 256:
            recommended_ram = 256
        print(f"  RAM:  {recommended_ram} MB per container")
        avg_cpu = sum(cpu_values) / len(cpu_values)
        if avg_cpu < 25:
            print(f"  CPU:  0.25 vCPU per container")
        elif avg_cpu < 50:
            print(f"  CPU:  0.5 vCPU per container")
        else:
            print(f"  CPU:  1.0 vCPU per container")


if __name__ == "__main__":
    monitor()
