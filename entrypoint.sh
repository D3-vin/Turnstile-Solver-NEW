#!/bin/bash

start_xrdp_services() {
	rm -rf /var/run/xrdp-sesman.pid
	rm -rf /var/run/xrdp.pid
	rm -rf /var/run/xrdp/xrdp-sesman.pid
	rm -rf /var/run/xrdp/xrdp.pid

	xrdp-sesman &
	xrdp -n &

	echo "X server initialization requested."
}

stop_xrdp_services() {
	echo "Stopping services..."
	xrdp --kill
	xrdp-sesman --kill

	pkill -f "python3 api_solver.py"
	exit 0
}

trap "stop_xrdp_services" SIGTERM SIGHUP SIGINT EXIT

start_xrdp_services

echo "Starting API solver in headful mode..."

# 将 xvfb-run 的输出重定向到标准输出和标准错误，使其在后台运行也能看到输出
xvfb-run -a python3 api_solver.py --browser_type camoufox --host 0.0.0.0 >/proc/self/fd/1 2>/proc/self/fd/2 &

wait
