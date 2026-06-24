#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"

case "${cmd}" in
    start)
        sudo systemctl start bms
        ;;
    stop)
        sudo systemctl stop bms
        ;;
    restart)
        sudo systemctl restart bms
        ;;
    status)
        sudo systemctl status bms
        ;;
    logs)
        journalctl -u bms -f
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}" >&2
        exit 1
        ;;
esac
