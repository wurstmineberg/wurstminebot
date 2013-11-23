**wurstminebot** is an IRC bot for Minecraft. It was written for [wurstmineberg](http://wurstmineberg.de/) and may require some tweaking to run on your server. It also has some dependencies which we haven't added to this repository yet.

This is `wurstminebot` version 2.1.8 ([semver](http://semver.org/)). The versioned API includes the usage pattern, as found in the docstring of [`wurstminebot.py`](wurstminebot.py), as well as the commands, as explained in the `help` command.

Requirements
============

*   [Python](http://python.org/) 3.2
*   [Python-IRC-Bot-Framework](https://github.com/fenhl/Python-IRC-Bot-Framework)
*   [TwitterAPI](https://github.com/geduldig/TwitterAPI)
*   [docopt](http://docopt.org/)
*   [init-minecraft](https://github.com/wurstmineberg/init-minecraft) 2.11
*   [requests](http://www.python-requests.org/) 1.2

Configuration
=============

If your system has `service`, you can move [`wurstminebot.py`](wurstminebot.py) to `/etc/init.d/wurstminebot`. You can then start, stop, or restart the bot with `service wurstminebot start` etc.
