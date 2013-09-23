#!/bin/bash
# move tis file to /etc/init.d/wurstminebot

### BEGIN INIT INFO
# Provides:   wurstminebot
# Required-Start: $local_fs $remote_fs
# Required-Stop: $local_fs $remote_fs
# Should-Start: $network
# Should-Stop: $network
# Short-Description: Minecraft and IRC bot
# Description: Starts wurstminebot, a Minecraft and IRC bot which provides chat synchronization and other features
### END INIT INFO

start() {
    start-stop-daemon --start --exec /opt/wurstmineberg/bin/wurstminebot
}

stop() {
    start-stop-daemon --stop --exec /opt/wurstmineberg/bin/wurstminebot
}

case $1 in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        start
        ;;
esac
