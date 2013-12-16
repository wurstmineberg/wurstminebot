**wurstminebot** is an IRC bot for Minecraft. It was written for [wurstmineberg](http://wurstmineberg.de/) and may require some tweaking to run on your server. It also has some dependencies which we haven't added to this repository yet.

This is `wurstminebot` version 2.7.4 ([semver](http://semver.org/)). The versioned API includes the usage patterns of [`wurstminebot.py`](wurstminebot.py) and [`nicksub.py`](nicksub.py), as found in the respective docstrings, as well as the commands, as explained in the `help` command.

Requirements
============

*   [Python](http://python.org/) 3.2
*   [Python-IRC-Bot-Framework](https://github.com/fenhl/Python-IRC-Bot-Framework)
*   [TwitterAPI](https://github.com/geduldig/TwitterAPI) 2.1
*   [docopt](http://docopt.org/)
*   [init-minecraft](https://github.com/wurstmineberg/init-minecraft) 2.13
*   [requests](http://www.python-requests.org/) 2.1

Configuration
=============

If your system has `service`, you can move [`wurstminebot.py`](wurstminebot.py) to `/etc/init.d/wurstminebot`. You can then start, stop, or restart the bot with `service wurstminebot start` etc.
