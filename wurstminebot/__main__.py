#!/usr/bin/env python3
"""Minecraft IRC bot.

Usage:
  wurstminebot [options] [start | stop | restart | status]
  wurstminebot -h | --help
  wurstminebot --version

Options:
  -h, --help         Print this message and exit.
  --config=<config>  Path to the config file [default: /opt/wurstmineberg/config/wurstminebot.json].
  --version          Print version info and exit.
"""
import sys

sys.path.append('/opt/py')

from wurstminebot import core
import daemon
from docopt import docopt
from wurstminebot import loops
import os
import signal

__version__ = core.__version__

def newDaemonContext(pidfilename):
    if not os.geteuid() == 0:
        sys.exit('[!!!!] Only root can start/stop the daemon!')
    pidfile = daemon.pidlockfile.PIDLockFile(pidfilename)
    logfile = open('/opt/wurstmineberg/log/wurstminebot.log', 'a')
    daemoncontext = daemon.DaemonContext(working_directory='/opt/wurstmineberg/', pidfile=pidfile, uid=1000, gid=1000, stdout=logfile, stderr=logfile)
    daemoncontext.files_preserve = [logfile]
    daemoncontext.signal_map = {
        signal.SIGTERM: bot.stop,
        signal.SIGHUP: bot.stop,
    }
    return daemoncontext

def start(context):
    print('[....] Starting wurstminebot version', __version__, end='\r', flush=True)
    if status(context.pidfile):
        print('[FAIL]')
        print('[ !! ] Wurstminebot is already running!')
        return
    else:
        print('[ ok ]')
        # Removes the PID file
        stop(context)
    print('[....] Daemonizing', end='\r', flush=True)
    with context:
        print('[ ok ]')
        core.run()
        print('[ ** ] Terminating')

def stop(context):
    loops.input_loop.stop()
    loops.time_loop.stop()
    if core.status(context.pidfile):
        print('[....] Stopping the service', end='\r', flush=True)
        if context.is_open:
            context.close()
        else:
            # We don't seem to be able to stop the context so we just kill the bot
            os.kill(context.pidfile.read_pid(), signal.SIGKILL)
        try:
            context.pidfile.release()
        except lockfile.NotMyLock:
            context.pidfile.break_lock()
    if context.pidfile.is_locked():
        print('[FAIL]')
        print('[....] Service did not shutdown correctly. Cleaning up', end='\r', flush=True)
        context.pidfile.break_lock()
        print('[ ok ]')
    else:
        print('[ ok ]')

if __name__ == '__main__':
    arguments = docopt(__doc__, version='wurstminebot ' + __version__)
    core.state['config_path'] = arguments['--config']
    pidfilename = "/var/run/wurstmineberg/wurstminebot.pid"
    if arguments['start']:
        context = newDaemonContext(pidfilename)
        start(context)
    elif arguments['stop']:
        context = newDaemonContext(pidfilename)
        stop(context)
    elif arguments['restart']:
        context = newDaemonContext(pidfilename)
        stop(context)
        start(context)
    elif arguments['status']:
        pidfile = daemon.pidlockfile.PIDLockFile(pidfilename)
        print('[info] wurstminebot ' + ('is' if core.status(pidfile) else 'is not') + ' running.')
    else:
        core.run()
