#!/usr/bin/env python3
"""Wurstminebot init script.

Usage:
  init.py start | stop | restart | status
  init.py -h | --help
  init.py --version

Options:
  -h, --help  Print this message and exit.
  --version   Print version info and exit.
"""

import sys

sys.path.append('/opt/py')

from docopt import docopt
import os
import os.path
import signal
import subprocess

KEEPALIVE = '/var/local/wurstmineberg/wurstminebot_keepalive'

def _fork(func):
    #FROM http://stackoverflow.com/a/6011298/667338
    # do the UNIX double-fork magic, see Stevens' "Advanced Programming in the UNIX Environment" for details (ISBN 0201563177)
    try:
        pid = os.fork()
        if pid > 0:
            # parent process, return and keep running
            return
    except OSError as e:
        print("fork #1 failed: %d (%s)" % (e.errno, e.strerror), file=sys.stderr)
        sys.exit(1)
    os.setsid()
    # do second fork
    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent
            sys.exit(0)
    except OSError as e:
        print("fork #2 failed: %d (%s)" % (e.errno, e.strerror), file=sys.stderr)
        sys.exit(1)
    with open(os.path.devnull) as devnull:
        sys.stdin = devnull
        sys.stdout = devnull
        func() # do stuff
        os._exit(os.EX_OK) # all done

def start():
    def _start():
        with open(KEEPALIVE, 'a'):
            pass # create the keepalive file
        while os.path.exists(KEEPALIVE):
            with open(os.path.devnull) as devnull:
                p = subprocess.Popen('wurstminebot < /var/local/wurstmineberg/irc', shell=True, stdout=devnull)
                with open(KEEPALIVE, 'a') as keepalive:
                    print(str(p.pid), file=keepalive)
                p.communicate()
    
    _fork(_start)

def status():
    return os.path.exists(KEEPALIVE)

def stop():
    pid = None
    try:
        with open(KEEPALIVE) as keepalive:
            for line in keepalive:
                pid = int(line.strip())
    except FileNotFoundError:
        return # not running
    else:
        os.remove(KEEPALIVE)
        if pid is not None:
            os.kill(pid, signal.SIGKILL)

if __name__ == '__main__':
    arguments = docopt(__doc__, version='0.1.0')
    if arguments['start']:
        start()
    elif arguments['stop']:
        stop()
    elif arguments['restart']:
        stop()
        start()
    elif arguments['status']:
        print('wurstminebot ' + ('is' if status() else 'is not') + ' running.')
