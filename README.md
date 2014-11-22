**wurstminebot** is an IRC bot for Minecraft. It was written for [Wurstmineberg](http://wurstmineberg.de/) and may require some tweaking to run on your server.

This is `wurstminebot` version 3.9.9 ([semver](http://semver.org/)). The versioned API includes the usage patterns of [`__main__.py`](wurstminebot/__main__.py), as found in the docstring, as well as the commands, as explained in the `help` command.

Requirements
============

*   [Python](http://python.org/) 3.2
*   [Python-IRC-Bot-Framework](https://github.com/fenhl/Python-IRC-Bot-Framework)
*   [TwitterAPI](https://github.com/geduldig/TwitterAPI) 2.1 (for Tweet command and other Twitter funcionality)
*   [docopt](http://docopt.org/)
*   [init-minecraft](https://github.com/wurstmineberg/init-minecraft) 2.19
*   [loops](https://gitlab.com/fenhl/python-loops) 1.2
*   [minecraft-api](https://github.com/wurstmineberg/minecraft-api) 1.1 (required for Cloud command only)
*   [requests](http://www.python-requests.org/) 2.1

Configuration
=============

If your system has `service`, you can symlink [`__main__.py`](wurstminebot/__main__.py) to `/etc/init.d/wurstminebot`. You can then start, stop, or restart the bot with `service wurstminebot start` etc.
