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

from TwitterAPI import TwitterAPI
import daemon
import daemon.pidlockfile
from datetime import datetime
import deaths
from docopt import docopt
from ircbotframe import ircBot
import json
import lockfile
import minecraft
import nicksub
import os
import os.path
import random
import re
import requests
import select
import signal
import socket
import subprocess
import threading
import time
from datetime import timedelta
import traceback
import xml.sax.saxutils

__version__ = nicksub.__version__

CONFIG_FILE = '/opt/wurstmineberg/config/wurstminebot.json'
if __name__ == '__main__':
    arguments = docopt(__doc__, version='wurstminebot ' + __version__)
    CONFIG_FILE = arguments['--config']

def _debug_print(msg):
    if config('debug', False):
        print('DEBUG] ' + msg)

def _logtail(timeout=0.5):
    logpath = os.path.join(config('paths')['minecraft_server'], 'logs', 'latest.log')
    with open(logpath) as log:
        lines_read = len(list(log.read().split('\n'))) - 1 # don't yield lines that already existed
    while True:
        time.sleep(timeout)
        with open(logpath) as log:
            lines = log.read().split('\n')
            if len(lines) <= lines_read: # log has restarted
                lines_read = 0
            for line in lines[lines_read:-1]:
                lines_read += 1
                yield line

def config(key=None, default_value=None):
    default_config = {
        'aliases': {},
        'advanced_comment_lines': {
            'death': [],
            'server_join': []
        },
        'comment_lines': {
            'death': ['Well done.'],
            'server_join': []
        },
        'daily_restart': True,
        'death_games': {
            'logfile': '/opt/wurstmineberg/config/deathgames.json',
            'enabled': False
        },
        'debug': False,
        'irc': {
            'channels': [],
            'dev_channel': None,
            'live_channel': None,
            'live_topic': None,
            'main_channel': '#wurstmineberg',
            'op_nicks': [],
            'password': '',
            'player_list': 'announce',
            'port': 6667,
            'quit_messages': ['brb'],
            'ssl': False,
            'topic': None
        },
        'ops': [],
        'paths': {
            'assets': '/var/www/wurstmineberg.de/assets/serverstatus',
            'deathgames': '/opt/wurstmineberg/log/deathgames.json',
            'keepalive': '/var/local/wurstmineberg/wurstminebot_keepalive',
            'logs': '/opt/wurstmineberg/log',
            'minecraft_server': '/opt/wurstmineberg/server',
            'people': '/opt/wurstmineberg/config/people.json',
            'scripts': '/opt/wurstmineberg/bin'
        },
        'twitter': {
            'screen_name': 'wurstmineberg'
        }
    }
    try:
        with open(CONFIG_FILE) as config_file:
            j = json.load(config_file)
    except:
        j = default_config
    if key is None:
        return j
    return j.get(key, default_config.get(key)) if default_value is None else j.get(key, default_value)

def set_config(config_dict):
    with open(CONFIG_FILE, 'w') as config_file:
        json.dump(config_dict, config_file, sort_keys=True, indent=4, separators=(',', ': '))

def update_config(path, value):
    config_dict = config()
    full_config_dict = config_dict
    if len(path) > 1:
        for key in path[:-1]:
            if not isinstance(config_dict, dict):
                raise KeyError('Trying to update a non-dict config key')
            if key not in config_dict:
                config_dict[key] = {}
            config_dict = config_dict[key]
    if len(path) > 0:
        config_dict[path[-1]] = value
    else:
        full_config_dict = value
    set_config(full_config_dict)

ACHIEVEMENTTWEET = True
DEATHTWEET = True
DST = bool(time.localtime().tm_isdst)
LASTDEATH = ''
LOGLOCK = threading.Lock()
PREVIOUS_TOPIC = None

bot = ircBot(config('irc')['server'], config('irc')['port'], config('irc')['nick'], config('irc')['nick'], password=config('irc')['password'], ssl=config('irc')['ssl'])
bot.log_own_messages = False

twitter = TwitterAPI(config('twitter')['consumer_key'], config('twitter')['consumer_secret'], config('twitter')['access_token_key'], config('twitter')['access_token_secret'])

class errors:
    log = "I can't find that in my chatlog"
    
    @staticmethod
    def argc(expected, given, atleast=False):
        return ('not enough' if given < expected else 'too many') + ' arguments, expected ' + ('at least ' if atleast else '') + str(expected)
    
    @staticmethod
    def unknown(command=None):
        if command is None or command == '':
            return 'Unknown command. Execute “help commands” for a list of commands, or “help aliases” for a list of aliases.'
        else:
            return '“' + str(command) + '” is not a command. Execute “help commands” for a list of commands, or “help aliases” for a list of aliases.'
    
    @staticmethod
    def permission(level=0):
        if level == 1:
            return 'you must be in people.json to do this'
        elif level == 2:
            return 'this command requires a server invite'
        elif level == 3:
            return 'you must be on the whitelist to do this'
        elif level == 4:
            return 'you must be a bot op to do this'
        else:
            return "you don't have permission to do this"

permission_levels = [None, 'sender must be in people.json', 'requires invite', 'whitelisted only', 'bot-ops only']

def update_all(*args, **kwargs):
    minecraft.update_status()
    minecraft.update_whitelist()
    update_topic(force='reply' in kwargs) # force-update the topic if called from fixstatus command
    threading.Timer(20, minecraft.update_status).start()

class TwitterError(Exception):
    def __init__(self, code, message=None, status_code=0):
        self.code = code
        self.message = message
        self.status_code = status_code
    
    def __str__(self):
        return str(self.code) if self.message is None else str(self.message)

def tweet(status):
    r = twitter.request('statuses/update', {'status': status})
    if isinstance(r, TwitterAPI.TwitterResponse):
        j = r.response.json()
    else:
        j = r.json()
    if r.status_code == 200:
        return j['id']
    first_error = j.get('errors', [])[0] if len(j.get('errors', [])) else {}
    raise TwitterError(first_error.get('code', 0), message=first_error.get('message'), status_code=r.status_code)

def pastetweet(status, link=False, tellraw=False):
    r = twitter.request('statuses/show', {'id': status})
    if isinstance(r, TwitterAPI.TwitterResponse):
        j = r.response.json()
    else:
        j = r.json()
    if r.status_code != 200:
        raise TwitterError(j.get('errors', {}).get('code', 0), message=j.get('errors', {}).get('message'), status_code=r.status_code)
    if 'retweeted_status' in j:
        retweeted_request = twitter.request('statuses/show', {'id': j['retweeted_status']['id']})
        if isinstance(retweeted_request, TwitterAPI.TwitterResponse):
            rj = retweeted_request.response.json()
        else:
            rj = retweeted_request.json()
        if retweeted_request.status_code != 200:
            raise TwitterError(rj.get('errors', {}).get('code', 0), message=rj.get('errors', {}).get('message'), status_code=retweeted_request.status_code)
        tweet_author = '<@' + j['user']['screen_name'] + ' RT @' + rj['user']['screen_name'] + '> '
        tweet_author_tellraw = [
            {
                'text': '@' + j['user']['screen_name'],
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'https://twitter.com/' + j['user']['screen_name']
                },
                'color': 'gold'
            },
            {
                'text': ' RT ',
                'color': 'gold'
            },
            {
                'text': '@' + rj['user']['screen_name'],
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'https://twitter.com/' + rj['user']['screen_name']
                },
                'color': 'gold'
            }
        ]
        text = xml.sax.saxutils.unescape(rj['text'])
    else:
        tweet_author = '<@' + j['user']['screen_name'] + '> '
        tweet_author_tellraw = [
            {
                'text': '@' + j['user']['screen_name'],
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'https://twitter.com/' + j['user']['screen_name']
                },
                'color': 'gold'
            }
        ]
        text = xml.sax.saxutils.unescape(j['text'])
    tweet_url = 'https://twitter.com/' + j['user']['screen_name'] + '/status/' + j['id_str']
    if tellraw:
        return {
            'text': '<',
            'color': 'gold',
            'extra': tweet_author_tellraw + [
                {
                    'text': '> ' + text,
                    'color': 'gold'
                }
            ] + ([
                {
                    'text': ' [',
                    'color': 'gold'
                },
                {
                    'text': tweet_url,
                    'clickEvent': {
                        'action': 'open_url',
                        'value': tweet_url
                    },
                    'color': 'gold'
                },
                {
                    'text': ']',
                    'color': 'gold'
                }
            ] if link else [])
        }
    else:
        return tweet_author + text + ((' [' + tweet_url + ']') if link else '')
    pass #TODO

def set_twitter(person, screen_name):
    person.twitter = screen_name
    members_list_id = config('twitter').get('members_list')
    if members_list_id is not None:
        twitter.request('lists/members/create', {'list_id': members_list_id, 'screen_name': screen_name})
    twitter.request('friendships/create', {'screen_name': screen_name})

def parse_timedelta(time_string):
    ret = 0
    time_string = time_string[:]
    while len(time_string) > 0:
        match = re.match('([0-9]+)([dhms])', time_string)
        if not match:
            if re.match('[0-9]+$', time_string):
                return ret + int(time_string)
            else:
                raise ValueError(str(time_string) + ' is not a valid time interval')
        number, unit = match.group(1, 2)
        ret += int(number) * {
            'd': 86400,
            'h': 3600,
            'm': 60,
            's': 1
        }[unit]
        time_string = time_string[len(number) + 1:]
    return ret

class InputLoop(threading.Thread):
    def __init__(self):
        super().__init__(name='wurstminebot InputLoop')
        self.stopped = False
    
    @staticmethod
    def process_log_line(log_line):
        global LASTDEATH
        try:
            # server log output processing
            _debug_print('[logpipe] ' + log_line)
            match = re.match(minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: \\* (' + minecraft.regexes.player + ') (.*)', log_line)
            if match:
                # action
                player, message = match.group(1, 2)
                try:
                    sender_person = nicksub.Person(player, context='minecraft')
                except nicksub.PersonNotFoundError:
                    sender_person = None
                chan = config('irc').get('main_channel', '#wurstmineberg')
                sender = (player if sender_person is None else sender_person.irc_nick())
                subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                bot.log(chan, 'ACTION', sender, [chan], subbed_message)
                bot.say(chan, '* ' + sender + ' ' + subbed_message)
            else:
                match = re.match(minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: <(' + minecraft.regexes.player + ')> (.*)', log_line)
                if match:
                    player, message = match.group(1, 2)
                    try:
                        sender_person = nicksub.Person(player, context='minecraft')
                    except nicksub.PersonNotFoundError:
                        sender_person = None
                    if message.startswith('!') and not re.match('!+$', message):
                        # command
                        cmd = message[1:].split(' ')
                        try:
                            command(cmd[0], args=cmd[1:], sender=player, sender_person=sender_person, context='minecraft')
                        except SystemExit:
                            _debug_print('Exit in log input loop')
                            InputLoop.stop()
                            TimeLoop.stop()
                            raise
                        except Exception as e:
                            minecraft.tellraw('Error: ' + str(e), str(player))
                            _debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(player) + ' to in-game chat:')
                            if config('debug', False):
                                traceback.print_exc()
                    else:
                        # chat message
                        chan = config('irc').get('main_channel', '#wurstmineberg')
                        sender = (player if sender_person is None else sender_person.irc_nick())
                        subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                        bot.log(chan, 'PRIVMSG', sender, [chan], subbed_message)
                        bot.say(chan, '<' + sender + '> ' + subbed_message)
                else:
                    match = re.match('(' + minecraft.regexes.timestamp + ') \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') (left|joined) the game', log_line)
                    if match:
                        # join/leave
                        timestamp, player = match.group(1, 2)
                        joined = bool(match.group(3) == 'joined')
                        with open(os.path.join(config('paths')['logs'], 'logins.log')) as loginslog:
                            for line in loginslog:
                                if player in line:
                                    new_player = False
                                    break
                            else:
                                new_player = True
                        with open(os.path.join(config('paths')['logs'], 'logins.log'), 'a') as loginslog:
                            print(timestamp + ' ' + player + ' ' + ('joined' if joined else 'left') + ' the game', file=loginslog)
                        if joined:
                            if new_player:
                                welcome_message = (0, 2) # The “welcome to the server” message
                            else:
                                welcome_messages = dict(((1, index), 1.0) for index in range(len(config('comment_lines').get('server_join', []))))
                                try:
                                    person = nicksub.Person(player, context='minecraft')
                                except PersonNotFoundError:
                                    welcome_messages[0, -1] = 16.0 # The “how did you do that?” welcome message
                                else:
                                    if person.description is None:
                                        welcome_messages[0, 1] = 1.0 # The “you still don't have a description” welcome message
                                for index, adv_welcome_msg in enumerate(config('advanced_comment_lines').get('server_join', [])):
                                    if 'text' not in adv_welcome_msg:
                                        continue
                                    welcome_messages[2, index] = adv_welcome_msg.get('weight', 1.0) * adv_welcome_msg.get('player_weights', {}).get(player, adv_welcome_msg.get('player_weights', {}).get('@default', 1.0))
                                random_index = random.uniform(0.0, sum(welcome_messages.values()))
                                index = 0.0
                                for welcome_message, weight in welcome_messages.items():
                                    if random_index - index < weight:
                                        break
                                    else:
                                        index += weight
                                else:
                                    welcome_message = (0, 0)
                            if welcome_message == (0, 0):
                                minecraft.tellraw({'text': 'Hello ' + player + '. Um... sup?', 'color': 'gray'}, player)
                            if welcome_message == (0, 1):
                                minecraft.tellraw([
                                    {
                                        'text': 'Hello ' + player + ". You still don't have a description for ",
                                        'color': 'gray'
                                    },
                                    {
                                        'text': 'the people page',
                                        'hoverEvent': {
                                            'action': 'show_text',
                                            'value': 'http://wurstmineberg.de/people'
                                        },
                                        'clickEvent': {
                                            'action': 'open_url',
                                            'value': 'http://wurstmineberg.de/people'
                                        },
                                        'color': 'gray'
                                    },
                                    {
                                        'text': '. ',
                                        'color': 'gray'
                                    },
                                    {
                                        'text': 'Write one today',
                                        'clickEvent': {
                                            'action': 'suggest_command',
                                            'value': '!people ' + person.id + ' description '
                                        },
                                        'color': 'gray'
                                    },
                                    {
                                        'text': '!',
                                        'color': 'gray'
                                    }
                                ], player)
                            elif welcome_message == (0, 2):
                                minecraft.tellraw({
                                    'text': 'Hello ' + player + '. Welcome to the server!',
                                    'color': 'gray'
                                }, player)
                            elif welcome_message[0] == 1:
                                minecraft.tellraw({
                                    'text': 'Hello ' + player + '. ' + config('comment_lines')['server_join'][welcome_message[1]],
                                    'color': 'gray'
                                }, player)
                            elif welcome_message[0] == 2:
                                message_dict = config('advanced_comment_lines')['server_join'][welcome_message[1]]
                                message_list = message_dict['text']
                                if isinstance(message_list, str):
                                    message_list = [{'text': message_list, 'color': 'gray'}]
                                elif isinstance(message_list, dict):
                                    message_list = [message_list]
                                minecraft.tellraw(([
                                    {
                                        'text': 'Hello ' + player + '. ',
                                        'color': 'gray'
                                    }
                                ] if message_dict.get('hello_prefix', True) else []) + message_list, player)
                            else:
                                minecraft.tellraw({
                                    'text': 'Hello ' + player + '. How did you do that?',
                                    'color': 'gray'
                                }, player)
                        if config('irc').get('player_list', 'announce') == 'announce':
                            bot.say(config('irc')['main_channel'], nicksub.sub(player, 'minecraft', 'irc') + ' ' + ('joined' if joined else 'left') + ' the game')
                        update_all()
                    else:
                        match = re.match(minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') has just earned the achievement \\[(.+)\\]$', log_line)
                        if match:
                            # achievement
                            player, achievement = match.group(1, 2)
                            if ACHIEVEMENTTWEET:
                                status = '[Achievement Get] ' + nicksub.sub(player, 'minecraft', 'twitter') + ' got ' + achievement
                                try:
                                    twid = tweet(status)
                                except TwitterError as e:
                                    twid = 'error ' + str(e.status_code) + ': ' + str(e)
                                else:
                                    twid = 'https://twitter.com/wurstmineberg/status/' + str(twid)
                            else:
                                twid = 'achievement tweets are disabled'
                            bot.say(config('irc')['main_channel'], 'Achievement Get: ' + nicksub.sub(player, 'minecraft', 'irc') + ' got ' + achievement + ' [' + twid + ']')
                        else:
                            try:
                                death = deaths.Death(log_line)
                            except ValueError:
                                pass # no death, continue parsing here or ignore this line
                            else:
                                with open(os.path.join(config('paths')['logs'], 'deaths.log'), 'a') as deathslog:
                                    print(death.timestamp.strftime('%Y-%m-%d %H:%M:%S') + ' ' + death.message(), file=deathslog)
                                if DEATHTWEET:
                                    if death.message() == LASTDEATH:
                                        comment = 'Again.' # This prevents botspam if the same player dies lots of times (more than twice) for the same reason.
                                    elif (death.id == 'slain-player-using' and death.groups[1] == 'Sword of Justice') or (death.id == 'shot-player-using' and death.groups[1] == 'Bow of Justice'): # Death Games success
                                        comment = 'And loses a diamond http://wiki.wurstmineberg.de/Death_Games'
                                        try:
                                            target = nicksub.Person(death.groups[0], context='minecraft')
                                        except nicksub.PersonNotFoundError:
                                            pass # don't automatically log
                                        else:
                                            death_games_log(death.person, target, success=True)
                                    else:
                                        death_comments = dict(((1, index), 1.0) for index in range(len(config('comment_lines').get('death', []))))
                                        for index, adv_death_comment in enumerate(config('advanced_comment_lines').get('death', [])):
                                            if 'text' not in adv_death_comment:
                                                continue
                                            try:
                                                death_comments[2, index] = adv_death_comment.get('weight', 1.0) * adv_death_comment.get('player_weights', {}).get(death.player.id, adv_death_comment.get('player_weights', {}).get('@default', 1.0)) * adv_death_comment.get('type_weights', {}).get(death.id, adv_death_comment.get('type_weights', {}).get('@default', 1.0))
                                            except:
                                                continue
                                        random_index = random.uniform(0.0, sum(death_comments.values()))
                                        index = 0.0
                                        for comment_index, weight in death_comments.items():
                                            if random_index - index < weight:
                                                break
                                            else:
                                                index += weight
                                        else:
                                            comment_index = (0, 0)
                                        if comment_index == (0, 0):
                                            comment = 'Well done.'
                                        elif comment_index[0] == 1:
                                            comment = config('comment_lines')['death'][comment_index[1]]
                                        elif comment_index[0] == 2:
                                            comment = config('advanced_comment_lines')['death'][comment_index[1]]['text']
                                        else:
                                            comment = "I don't even."
                                    LASTDEATH = death.message()
                                    status = death.tweet(comment=comment)
                                    try:
                                        twid = tweet(status)
                                    except TwitterError as e:
                                        twid = 'error ' + str(e.status_code) + ': ' + str(e)
                                        minecraft.tellraw([
                                            {
                                                'text': 'Your fail has ',
                                                'color': 'gold'
                                            },
                                            {
                                                'text': 'not',
                                                'color': 'red'
                                            },
                                            {
                                                'text': ' been reported because of ',
                                                'color': 'gold'
                                            },
                                            {
                                                'text': 'reasons',
                                                'hoverEvent': {
                                                    'action': 'show_text',
                                                    'value': str(e.status_code) + ': ' + str(e)
                                                },
                                                'color': 'gold'
                                            },
                                            {
                                                'text': '.',
                                                'color': 'gold'
                                            }
                                        ])
                                    else:
                                        twid = 'https://twitter.com/wurstmineberg/status/' + str(twid)
                                        minecraft.tellraw({
                                            'text': 'Your fail has been reported. Congratulations.',
                                            'color': 'gold',
                                            'clickEvent': {
                                                'action': 'open_url',
                                                'value': twid
                                            }
                                        })
                                else:
                                    twid = 'deathtweets are disabled'
                                bot.say(config('irc')['main_channel'], death.irc_message(tweet_info=twid))
        except SystemExit:
            _debug_print('Exit in log input loop')
            InputLoop.stop()
            TimeLoop.stop()
            raise
        except:
            _debug_print('Exception in log input loop:')
            if config('debug', False):
                traceback.print_exc()
    
    def run(self):
        for log_line in _logtail():
            InputLoop.process_log_line(log_line)
            if self.stopped or not bot.keepGoing:
                break
    
    def start(self):
        self.stopped = False
        super().start()
    
    def stop(self):
        self.stopped = True

InputLoop = InputLoop()

class TimeLoop(threading.Thread):
    def __init__(self):
        super().__init__(name='wurstminebot TimeLoop')
        self.stopped = False
    
    def run(self):
        #FROM http://stackoverflow.com/questions/9918972/running-a-line-in-1-hour-intervals-in-python
        # modified to work with leap seconds
        while not self.stopped:
            # sleep for the remaining seconds until the next hour
            time_until_hour = 3601 - time.time() % 3600
            while time_until_hour >= 60:
                time.sleep(60)
                if self.stopped:
                    break
                time_until_hour -= 60
            while time_until_hour >= 1:
                time.sleep(1)
                if self.stopped:
                    break
                time_until_hour -= 1
            if self.stopped:
                break
            telltime(comment=True, restart=config('daily_restart', True))
    
    def start(self):
        self.stopped = False
        super().start()
    
    def stop(self):
        self.stopped = True

TimeLoop = TimeLoop()

def telltime(func=None, comment=False, restart=False):
    if func is None:
        def func(msg):
            for line in msg.splitlines():
                try:
                    minecraft.tellraw({'text': line, 'color': 'gold'})
                except socket.error:
                    bot.say(config('irc').get('main_channel', '#wurstmineberg'), 'Warning: telltime is disconnected from Minecraft')
                    break
        
        custom_func = False
    else:
        custom_func = True
    def warning(msg):
        if custom_func:
            func(msg)
        else:
            for line in msg.splitlines():
                try:
                    minecraft.tellraw({'text': line, 'color': 'red'})
                except socket.error:
                    bot.say(config('irc').get('main_channel', '#wurstmineberg'), 'Warning: telltime is disconnected from Minecraft')
                    break
    
    global DST
    global PREVIOUS_TOPIC
    localnow = datetime.now()
    utcnow = datetime.utcnow()
    dst = bool(time.localtime().tm_isdst)
    if dst != DST:
        if dst:
            func('Daylight saving time is now in effect.')
        else:
            func('Daylight saving time is no longer in effect.')
    func('The time is ' + localnow.strftime('%H:%M') + ' (' + utcnow.strftime('%H:%M') + ' UTC)')
    if comment:
        if dst != DST:
            pass
        elif localnow.hour == 0:
            func('Dark outside, better play some Minecraft.')
        elif localnow.hour == 1:
            func("You better don't stay up all night again.")
        elif localnow.hour == 2:
            func('Some late night mining always cheers me up.')
            time.sleep(10)
            func('...Or redstoning. Or building. Whatever floats your boat.')
        elif localnow.hour == 3:
            func('Seems like you are having fun.')
            time.sleep(60)
            func("I heard that zombie over there talk trash about you. Thought you'd wanna know...")
        elif localnow.hour == 4:
            func('Getting pretty late, huh?')
        elif localnow.hour == 5:
            warning('It is really getting late. You should go to sleep.')
        elif localnow.hour == 6:
            func('Are you still going, just starting or asking yourself the same thing?')
        elif localnow.hour == 11 and localnow.minute < 5 and restart:
            players = minecraft.online_players()
            if len(players):
                warning('The server is going to restart in 5 minutes.')
                time.sleep(240)
                warning('The server is going to restart in 60 seconds.')
                time.sleep(50)
            PREVIOUS_TOPIC = (config('irc')['topic'] + ' | ' if 'topic' in config('irc') and config('irc')['topic'] is not None else '') + 'The server is restarting…'
            bot.topic(config('irc')['main_channel'], PREVIOUS_TOPIC)
            if minecraft.restart(reply=func):
                if len(players):
                    irc_players = []
                    for player in players:
                        try:
                            irc_players.append(nicksub.Person(player, context='minecraft').irc_nick(respect_highlight_option=False))
                        except:
                            irc_players.append(player)
                    bot.say(config('irc').get('main_channel', '#wurstmineberg'), ', '.join(irc_players) + ': The server has restarted.')
            else:
                bot.say(config('irc').get('main_channel', '#wurstmineberg'), 'Please help! Something went wrong with the server restart!')
            update_topic()
    DST = dst

def update_topic(force=False):
    global PREVIOUS_TOPIC
    main_channel = config('irc').get('main_channel')
    if main_channel is None:
        return
    players = []
    for mcnick in (minecraft.online_players() if config('irc').get('player_list', 'announce') == 'topic' else []):
        try:
            person = nicksub.Person(mcnick, context='minecraft').irc_nick(respect_highlight_option=False)
        except nicksub.PersonNotFoundError:
            person = mcnick
        players.append(person)
    player_list = ('Currently online: ' + ', '.join(players)) if len(players) else ''
    topic = config('irc').get('topic')
    if topic is None:
        new_topic = player_list
    elif len(players):
        new_topic = topic + ' | ' + player_list
    else:
        new_topic = topic
    if force or PREVIOUS_TOPIC != new_topic:
        bot.topic(main_channel, new_topic)
    PREVIOUS_TOPIC = new_topic

def mwiki_lookup(article=None, args=[], permission_level=0, reply=None, sender=None, sender_person=None):
    if reply is None:
        def reply(*args, **kwargs):
            pass
    
    if article is None:
        if args is None:
            article = ''
        if isinstance(args, str):
            article = args
        elif isinstance(args, list):
            article = '_'.join(args)
        else:
            reply('Unknown article')
            return 'Unknown article'
    match = re.match('http://(?:minecraft\\.gamepedia\\.com|minecraftwiki\\.net(?:/wiki)?)/(.*)', article)
    if match:
        article = match.group(1)
    request = requests.get('http://minecraft.gamepedia.com/' + article, params={'action': 'raw'})
    if request.status_code == 200:
        if request.text.lower().startswith('#redirect'):
            match = re.match('#[Rr][Ee][Dd][Ii][Rr][Ee][Cc][Tt] \\[\\[(.+)(\\|.*)?\\]\\]', request.text)
            if match:
                redirect_target = 'http://minecraft.gamepedia.com/' + re.sub(' ', '_', match.group(1))
                reply('Redirect ' + redirect_target)
                return 'Redirect ' + redirect_target
            else:
                reply('Broken redirect')
                return 'Broken redirect'
        else:
            reply('Article http://minecraft.gamepedia.com/' + article)
            return 'Article http://minecraft.gamepedia.com/' + article
    else:
        reply('Error ' + str(request.status_code))
        return 'Error ' + str(request.status_code)

def death_games_log(attacker, target, success=True):
    with open(config('paths').get('deathgames', '/opt/wurstmineberg/log/deathgames.json')) as logfile:
        log = json.load(logfile)
    log['log'].append({
        'attacker': attacker.id,
        'date': datetime.utcnow().strftime('%Y-%m-%d'),
        'success': success,
        'target': target.id
    })
    with open(config('paths').get('deathgames', '/opt/wurstmineberg/log/deathgames.json'), 'w') as logfile:
        json.dump(log, logfile, sort_keys=True, indent=4, separators=(',', ': '))
    minecraft.tellraw([
        {
            'text': '[Death Games]',
            'clickEvent': {
                'action': 'open_url',
                'value': 'http://wiki.wurstmineberg.de/Death_Games'
            },
            'color': 'gold'
        },
        {
            'text': ' ',
            'color': 'gold'
        },
        {
            'text': attacker.minecraft,
            'clickEvent': {
                'action': 'suggest_command',
                'value': attacker.minecraft + ': '
            },
            'color': 'gold'
        },
        {
            'text': "'s attempt on ",
            'color': 'gold'
        },
        {
            'text': target.minecraft,
            'clickEvent': {
                'action': 'suggest_command',
                'value': target.minecraft + ': '
            },
            'color': 'gold'
        },
        {
            'text': (' succeeded.' if success else ' failed.'),
            'color': 'gold'
        }
    ])
    bot.say(config('irc').get('main_channel', '#wurstmineberg'), '[Death Games] ' + attacker.irc_nick() + "'s attempt on " + target.irc_nick() + (' succeeded.' if success else ' failed.'))

def command(cmd, args=[], context=None, chan=None, reply=None, reply_format=None, sender=None, sender_person=None, addressing=None):
    if reply is None:
        if reply_format == 'tellraw' or (reply_format is None and context == 'minecraft'):
            reply_format = 'tellraw'
            def reply(msg):
                if isinstance(msg, str):
                    for line in msg.splitlines():
                        minecraft.tellraw({'text': line, 'color': 'gold'}, '@a' if sender is None else sender)
                else:
                    minecraft.tellraw(msg, '@a' if sender is None else sender)
        else:
            def reply(msg):
                if context == 'irc':
                    if not sender:
                        for line in msg.splitlines():
                            bot.say(config('irc')['main_channel'] if chan is None else chan, line)
                    elif chan:
                        for line in msg.splitlines():
                            bot.say(chan, sender + ': ' + line)
                    else:
                        for line in msg.splitlines():
                            bot.say(sender, line)
                else:
                    _debug_print('[command reply] ' + msg)
    
    def warning(msg):
        if reply_format == 'tellraw':
            reply({'text': msg, 'color': 'red'})
        else:
            reply(msg)
    
    def _command_achievementtweet(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        global ACHIEVEMENTTWEET
        if not len(args):
            reply('Achievement tweeting is currently ' + ('enabled' if ACHIEVEMENTTWEET else 'disabled'))
        elif args[0] == 'on':
            ACHIEVEMENTTWEET = True
            reply('Achievement tweeting is now enabled')
        elif args[0] == 'off':
            def _reenable_achievement_tweets():
                global ACHIEVEMENTTWEET
                ACHIEVEMENTTWEET = True
            
            if len(args) > 2:
                warning('Usage: achievementtweet [on | off [<time>]]')
                return
            elif len(args) == 2:
                number = parse_timedelta(str(args[1]))
                if number > 86400 and permission_level < 4:
                    warning(errors.permission(4))
                    return
                threading.Timer(number, _reenable_achievement_tweets).start()
            elif permission_level < 4:
                warning(errors.permission(4))
                return
            ACHIEVEMENTTWEET = False
            reply('Achievement tweeting is now disabled')
        else:
            warning('Usage: achievementtweet [on | off [<time>]]')
    
    def _command_alias(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        aliases = config('aliases')
        if len(args) == 0:
            warning('Usage: alias <alias_name> [<text>...]')
        elif len(args) == 1:
            if permission_level >= 4:
                if str(args[0]) in aliases:
                    deleted_alias = str(aliases[str(args[0])])
                    del aliases[str(args[0])]
                    update_config(['aliases'], aliases)
                    reply('Alias deleted. (Was “' + deleted_alias + '”)')
                else:
                    warning('The alias you' + (' just ' if random.randrange(0, 1) else ' ') + 'tried to delete ' + ("didn't" if random.randrange(0, 1) else 'did not') + (' even ' if random.randrange(0, 1) else ' ') + 'exist' + (' in the first place!' if random.randrange(0, 1) else '!') + (" So I guess everything's fine then?" if random.randrange(0, 1) else '')) # fun with randomized replies
            else:
                warning(errors.permission(4))
        elif str(args[0]) in aliases and permission_level < 4:
            warning(errors.permission(4))
        else:
            alias_existed = str(args[0]) in aliases
            aliases[str(args[0])] = ' '.join(args[1:])
            update_config(['aliases'], aliases)
            reply('Alias ' + ('edited' if alias_existed else 'added') + ', but hidden because there is a command with the same name.' if str(args[0]).lower() in commands + ['help'] else 'Alias added.')
    
    def _command_command(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if args[0]:
            reply(minecraft.command(args[0], args[1:]))
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_deathtweet(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        global DEATHTWEET
        if not len(args):
            reply('Deathtweeting is currently ' + ('enabled' if DEATHTWEET else 'disabled'))
        elif args[0] == 'on':
            DEATHTWEET = True
            reply('Deathtweeting is now enabled')
        elif args[0] == 'off':
            def _reenable_death_tweets():
                global DEATHTWEET
                DEATHTWEET = True
            
            if len(args) > 2:
                warning('Usage: achievementtweet [on | off [<time>]]')
                return
            elif len(args) == 2:
                number = parse_timedelta(str(args[1]))
                if number > 86400 and permission_level < 4:
                    warning(errors.permission(4))
                    return
                threading.Timer(number, _reenable_death_tweets).start()
            elif permission_level < 4:
                warning(errors.permission(4))
                return
            DEATHTWEET = False
            reply('Deathtweeting is now disabled')
        else:
            warning('Usage: deathtweet [on | off [<time>]]')
    
    def _command_dg(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args) not in [2, 3] or args[0].lower() not in ['win', 'fail']:
            warning('Usage: dg (win | fail) [<attacker>] <target>')
            return
        success = args[0].lower() == 'win'
        if len(args) == 3:
            try:
                attacker = nicksub.Person(args[1], context=context)
            except nicksub.PersonNotFoundError:
                try:
                    attacker = nicksub.Person(args[1])
                except nicksub.PersonNotFoundError:
                    warning('Target not found')
                    return
            try:
                target = nicksub.Person(args[2], context=context)
            except nicksub.PersonNotFoundError:
                try:
                    target = nicksub.Person(args[2])
                except nicksub.PersonNotFoundError:
                    warning('Target not found')
                    return
        else:
            if sender_person is None:
                warning(errors.permission(3))
                return
            attacker = sender_person
            try:
                target = nicksub.Person(args[1], context=context)
            except nicksub.PersonNotFoundError:
                try:
                    target = nicksub.Person(args[1])
                except nicksub.PersonNotFoundError:
                    warning('Target not found')
                    return
        death_games_log(attacker, target, success)
    
    def _command_join(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args) != 1:
            warning('Usage: join <channel>')
            return
        chans = sorted(config('irc').get('channels', []))
        if str(args[0]) in chans:
            bot.joinchan(str(args[0]))
            warning('I am already in ' + str(args[0]))
            return
        chans.append(str(args[0]))
        chans = sorted(chans)
        update_config(['irc', 'channels'], chans)
        bot.joinchan(str(args[0]))
    
    def _command_lastseen(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        global LAST
        if len(args):
            player = args[0]
            try:
                person = nicksub.Person(player, context=context)
            except (ValueError, nicksub.PersonNotFoundError):
                try:
                    person = nicksub.Person(player, context='minecraft')
                except (ValueError, nicksub.PersonNotFoundError):
                    try:
                        person = nicksub.Person(player)
                    except nicksub.PersonNotFoundError:
                        warning('No such person')
                        return
            if person.minecraft is None:
                warning('No Minecraft nick for this person')
                return
            if person.minecraft in minecraft.online_players():
                if reply_format == 'tellraw':
                    reply([
                        {
                            'text': player,
                            'hoverEvent': {
                                'action': 'show_text',
                                'value': person.minecraft + ' in Minecraft'
                            },
                            'clickEvent': {
                                'action': 'suggest_command',
                                'value': person.minecraft + ': '
                            },
                            'color': 'gold',
                        },
                        {
                            'text': ' is currently on the server.',
                            'color': 'gold'
                        }
                    ])
                else:
                    reply(player + ' is currently on the server.')
            else:
                with LOGLOCK:
                    lastseen = minecraft.last_seen(person.minecraft)
                    if lastseen is None:
                        reply('I have not seen ' + player + ' on the server yet.')
                    else:
                        if lastseen.date() == datetime.utcnow().date():
                            datestr = 'today at ' + lastseen.strftime('%H:%M UTC')
                            tellraw_date = [
                                {
                                    'text': 'today',
                                    'hoverEvent': {
                                        'action': 'show_text',
                                        'value': lastseen.strftime('%Y-%m-%d')
                                    },
                                    'color': 'gold'
                                },
                                {
                                    'text': ' at ' + lastseen.strftime('%H:%M UTC.'),
                                    'color': 'gold'
                                }
                            ]
                        elif lastseen.date() == datetime.utcnow().date() - timedelta(days=1):
                            datestr = 'yesterday at ' + lastseen.strftime('%H:%M UTC')
                            tellraw_date = [
                                {
                                    'text': 'yesterday',
                                    'hoverEvent': {
                                        'action': 'show_text',
                                        'value': lastseen.strftime('%Y-%m-%d')
                                    },
                                    'color': 'gold'
                                },
                                {
                                    'text': ' at ' + lastseen.strftime('%H:%M UTC.'),
                                    'color': 'gold'
                                }
                            ]
                        else:
                            datestr = lastseen.strftime('on %Y-%m-%d at %H:%M UTC')
                            tellraw_date = [
                                {
                                    'text': datestr + '.',
                                    'color': 'gold'
                                }
                            ]
                        if reply_format == 'tellraw':
                            reply([
                                {
                                    'text': player,
                                    'hoverEvent': {
                                        'action': 'show_text',
                                        'value': person.minecraft + ' in Minecraft'
                                    },
                                    'color': 'gold',
                                },
                                {
                                    'text': ' was last seen ',
                                    'color': 'gold'
                                }
                            ] + tellraw_date)
                        else:
                            reply(player + ' was last seen ' + datestr + '.')
        else:
            warning(errors.argc(1, len(args)))
    
    def _command_leak(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        messages = [(msg_type, msg_sender, msg_text) for msg_type, msg_sender, msg_headers, msg_text in bot.channel_data[config('irc')['main_channel']]['log'] if msg_type == 'ACTION' or (msg_type == 'PRIVMSG' and (not msg_text.startswith('!')) and (not msg_text.startswith(config('irc')['nick'] + ': ')) and (not msg_text.startswith(config('irc')['nick'] + ', ')))]
        if len(args) == 0:
            if len(messages):
                messages = [messages[-1]]
            else:
                warning(errors.log)
                return
        elif len(args) == 1:
            if re.match('[0-9]+$', args[0]) and len(messages) >= int(args[0]):
                messages = messages[-int(args[0]):]
            else:
                warning(errors.log)
                return
        else:
            warning(errors.argc(1, len(args)))
            return
        status = '\n'.join(((('* ' + nicksub.sub(msg_sender, 'irc', 'twitter') + ' ') if msg_type == 'ACTION' else ('<' + nicksub.sub(msg_sender, 'irc', 'twitter') + '> ')) + nicksub.textsub(message, 'irc', 'twitter')) for msg_type, msg_sender, message in messages)
        if len(status + ' #ircleaks') <= 140:
            if '\n' in status:
                status += '\n#ircleaks'
            else:
                status += ' #ircleaks'
        try:
            twid = tweet(status)
        except TwitterError as e:
            warning('Error ' + str(e.status_code) + ': ' + str(e))
        else:
            tweet_url = 'https://twitter.com/' + config('twitter').get('screen_name', 'wurstmineberg') + '/status/' + str(twid)
            minecraft.tellraw({
                'text': 'leaked',
                'clickEvent': {
                    'action': 'open_url',
                    'value': tweet_url
                },
                'color': 'gold'
            })
            bot.say(config('irc').get('main_channel', '#wurstmineberg'), 'leaked ' + tweet_url)
    
    def _command_opt(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args) not in [1, 2]:
            warning('Usage: opt <option> [true|false]')
            return
        option = str(args[0])
        if sender_person is None:
            warning(errors.permission(1))
            return None
        if len(args) == 1:
            flag = sender_person.option(args[0])
            is_default = sender_person.option_is_default(args[0])
            reply('option ' + str(args[0]) + ' is ' + ('on' if flag else 'off') + ' ' + ('by default' if is_default else 'for you'))
            return flag
        else:
            flag = bool(args[1] in [True, 1, '1', 'true', 'True', 'on', 'yes', 'y', 'Y'])
            sender_person.set_option(str(args[0]), flag)
            reply('option ' + str(args[0]) + ' is now ' + ('on' if flag else 'off') + ' for you')
            return flag
    
    def _command_pastemojira(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        link = True
        if len(args) == 3 and args[2] == 'nolink':
            link = False
            args = args[:2]
        elif len(args) == 2 and args[1] == 'nolink':
            link = False
            args = [args[0]]
        if len(args) == 2:
            project_key = str(args[0])
            try:
                issue_id = int(args[1])
            except ValueError:
                warning('Invalid issue ID: ' + str(args[0]))
                return
        elif len(args) == 1:
            match = re.match('(https?://mojang.atlassian.net/browse/)?([A-Z]+)-([0-9]+)', str(args[0]))
            if match:
                project_key = str(match.group(2))
                issue_id = int(match.group(3))
            else:
                project_key = 'MC'
                try:
                    issue_id = int(args[0])
                except ValueError:
                    warning('Invalid issue ID: ' + str(args[0]))
        else:
            reply('http://mojang.atlassian.net/browse/MC')
            return
        request = requests.get('http://mojang.atlassian.net/browse/' + project_key + '-' + str(issue_id))
        if request.status_code == 200:
            match = re.match('<title>\\[([A-Z]+)-([0-9]+)\\] (.+) - Mojira</title>', request.text.splitlines()[18])
            if not match:
                warning('could not get title')
                return
            project_key, issue_id, title = match.group(1, 2, 3)
            if reply_format == 'tellraw':
                reply({
                    'text': '[' + project_key + '-' + issue_id + '] ' + title,
                    'color': 'gold',
                    'clickEvent': {
                        'action': 'open_url',
                        'value': 'http://mojang.atlassian.net/browse/' + project_key + '-' + issue_id
                    }
                })
            else:
                reply('[' + project_key + '-' + issue_id + '] ' + title + (' [http://mojang.atlassian.net/browse/' + project_key + '-' + issue_id + ']' if link else ''))
        else:
            warning('Error ' + str(request.status_code))
            return
    
    def _command_pastetweet(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        link = True
        if len(args) == 2 and args[1] == 'nolink':
            link = False
            args = [args[0]]
        if len(args) == 1:
            match = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)', str(args[0]))
            twid = match.group(1) if match else args[0]
            try:
                reply(pastetweet(twid, link=link, tellraw=reply_format == 'tellraw'))
            except TwitterError as e:
                warning('Error ' + str(e.status_code) + ': ' + str(e))
        else:
            warning('Usage: pastetweet (<url> | <status_id>) [nolink]')
    
    def _command_people(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args):
            person = nicksub.Person(str(args[0]))
            can_edit = permission_level >= 4 or sender_person == person
            can_only_edit_self_error = "You can only edit your own profile. Only bot ops can edit someone else's profile."
            if len(args) >= 2:
                if args[1] == 'description':
                    if len(args) == 2:
                        if person.description:
                            reply(person.description)
                        else:
                            reply('no description')
                        return
                    elif can_edit:
                        person.description = ' '.join(args[2:])
                        reply('description updated')
                    else:
                        warning(can_only_edit_self_error)
                        return
                elif args[1] == 'name':
                    if len(args) == 2:
                        if person.name:
                            reply(person.name)
                        else:
                            reply('no name, using id: ' + person.id)
                    elif can_edit:
                        had_name = person.name is not None
                        person.name = ' '.join(args[2:])
                        reply('name ' + ('changed' if had_name else 'added'))
                    else:
                        warning(can_only_edit_self_error)
                        return
                elif args[1] == 'reddit':
                    if len(args) == 2:
                        if person.reddit:
                            reply('/u/' + person.reddit)
                        else:
                            reply('no reddit nick')
                    elif can_edit:
                        had_reddit_nick = person.reddit is not None
                        reddit_nick = args[2][3:] if args[2].startswith('/u/') else args[2]
                        person.reddit = reddit_nick
                        reply('reddit nick ' + ('changed' if had_reddit_nick else 'added'))
                    else:
                        warning(can_only_edit_self_error)
                        return
                elif args[1] == 'twitter':
                    if len(args) == 2:
                        if person.twitter:
                            reply('@' + person.twitter)
                        else:
                            reply('no twitter nick')
                        return
                    elif can_edit:
                        screen_name = args[2][1:] if args[2].startswith('@') else args[2]
                        set_twitter(person, screen_name)
                        reply('@' + config('twitter')['screen_name'] + ' is now following @' + screen_name)
                    else:
                        warning(can_only_edit_self_error)
                        return
                elif args[1] == 'website':
                    if len(args) == 2:
                        if person.website:
                            reply(person.website)
                        else:
                            reply('no website')
                    elif can_edit:
                        had_website = person.website is not None
                        person.website = str(args[2])
                        reply('website ' + ('changed' if had_website else 'added'))
                    else:
                        warning(can_only_edit_self_error)
                        return
                elif args[1] == 'wiki':
                    if len(args) == 2:
                        if person.wiki:
                            reply(person.wiki)
                        else:
                            reply('no wiki account')
                    elif can_edit:
                        had_wiki = person.wiki is not None
                        person.wiki = str(args[2])
                        reply('wiki account ' + ('changed' if had_wiki else 'added'))
                else:
                    warning('no such people attribute: ' + str(args[1]))
                    return
            else:
                if 'name' in person:
                    reply('person with id ' + str(args[0]) + ' and name ' + person['name'])
                else:
                    reply('person with id ' + str(args[0]) + ' and no name (id will be used as name)')
        else:
            reply('http://wurstmineberg.de/people')
    
    def _command_ping(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if random.randrange(1024) == 0:
            reply('BWO' + 'R' * random.randint(3, 20) + 'N' * random.randint(1, 5) + 'G') # PINGCEPTION
        else:
            reply('pong')
    
    def _command_quit(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        quitMsg = ' '.join(args) if len(args) else None
        minecraft.tellraw({
            'text': ('Shutting down the bot: ' + quitMsg) if quitMsg else 'Shutting down the bot...',
            'color': 'red'
        })
        bot.say(config('irc')['main_channel'], ('bye, ' + quitMsg) if quitMsg else random.choice(config('irc').get('quit_messages', ['bye'])))
        bot.disconnect(quitMsg if quitMsg else 'bye')
        bot.stop()
        sys.exit()
    
    def _command_raw(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args):
            bot.send(' '.join(args))
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_restart(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        global PREVIOUS_TOPIC
        if len(args) == 0 or (len(args) == 1 and args[0] == 'bot'):
            # restart the bot
            minecraft.tellraw({
                'text': 'Restarting the bot...',
                'color': 'red'
            })
            bot.say(config('irc')['main_channel'], random.choice(config('irc').get('quit_messages', ['brb'])))
            bot.disconnect('brb')
            bot.stop()
            context = newDaemonContext('/var/run/wurstmineberg/wurstminebot.pid')
            stop(context)
            start(context)
            sys.exit()
        elif len(args) == 1 and args[0] == 'minecraft':
            # restart the Minecraft server
            PREVIOUS_TOPIC = (config('irc')['topic'] + ' | ' if 'topic' in config('irc') and config('irc')['topic'] is not None else '') + 'The server is restarting…'
            bot.topic(config('irc')['main_channel'], PREVIOUS_TOPIC)
            if minecraft.restart(args=args, permission_level=permission_level, reply=reply, sender=sender):
                reply('Server restarted.')
            else:
                reply('Could not restart the server!')
            update_topic()
        else:
            warning('Usage: restart [minecraft | bot]')
    
    def _command_status(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if minecraft.status():
            if context != 'minecraft':
                players = minecraft.online_players()
                if len(players):
                    reply('Online players: ' + ', '.join(nicksub.sub(nick, 'minecraft', context) for nick in players))
                else:
                    reply('The server is currently empty.')
            version = minecraft.version()
            if version is None:
                reply('unknown Minecraft version')
            elif reply_format == 'tellraw':
                reply({
                    'text': 'Minecraft version ',
                    'extra': [
                        {
                            'text': version,
                            'clickEvent': {
                                'action': 'open_url',
                                'value': 'http://minecraft.gamepedia.com/Version_history' + ('/Development_versions#' if 'pre' in version or version[2:3] == 'w' else '#') + version
                            }
                        }
                    ]
                })
            else:
                reply('Minecraft version ' + version)
        else:
            reply('The server is currently offline.')
    
    def _command_stop(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        global PREVIOUS_TOPIC
        if len(args) == 0 or (len(args) == 1 and args[0] == 'bot'):
            # stop the bot
            return _command_quit(args=[], permission_level=permission_level, reply=reply, sender=sender)
        elif len(args) == 1 and args[0] == 'minecraft':
            # stop the Minecraft server
            PREVIOUS_TOPIC = (config('irc')['topic'] + ' | ' if 'topic' in config('irc') and config('irc')['topic'] is not None else '') + 'The server is down for now. Blame ' + str(sender) + '.'
            bot.topic(config('irc')['main_channel'], PREVIOUS_TOPIC)
            if minecraft.stop(args=args, permission_level=permission_level, reply=reply, sender=sender):
                reply('Server stopped.')
            else:
                warning('The server could not be stopped! D:')
        else:
            warning('Usage: stop [minecraft | bot]')
    
    def _command_time(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        telltime(func=reply)
    
    def _command_topic(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args):
            update_config(['irc', 'topic'], ' '.join(str(arg) for arg in args))
            update_topic()
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_tweet(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args):
            status = nicksub.textsub(' '.join(args), context, 'twitter')
            try:
                twid = tweet(status)
            except TwitterError as e:
                warning('Error ' + str(e.status_code) + ': ' + str(e))
            else:
                url = 'https://twitter.com/wurstmineberg/status/' + str(twid)
                if context == 'minecraft':
                    minecraft.tellraw({
                        'text': '',
                        'extra': [
                            {
                                'text': url,
                                'color': 'gold',
                                'clickEvent': {
                                    'action': 'open_url',
                                    'value': url
                                }
                            }
                        ]
                    })
                else:
                    minecraft.tellraw(pastetweet(twid, tellraw=True))
                if context == 'irc' and chan == config('irc')['main_channel']:
                    bot.say(chan, url)
                else:
                    for line in pastetweet(twid).splitlines():
                        bot.say(config('irc')['main_channel'] if chan is None else chan, line)
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_update(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        global PREVIOUS_TOPIC
        
        if len(args):
            if args[0] == 'snapshot':
                if len(args) == 2:
                    PREVIOUS_TOPIC = (config('irc')['topic'] + ' | ' if 'topic' in config('irc') and config('irc')['topic'] is not None else '') + 'The server is being updated, wait a sec.'
                    bot.topic(config('irc')['main_channel'], PREVIOUS_TOPIC)
                    version, is_snapshot, version_text = minecraft.update(args[1], snapshot=True, reply=reply)
                else:
                    warning('Usage: update [snapshot <snapshot_id> | <version>]')
            elif len(args) == 1:
                PREVIOUS_TOPIC = (config('irc')['topic'] + ' | ' if 'topic' in config('irc') and config('irc')['topic'] is not None else '') + 'The server is being updated, wait a sec.'
                bot.topic(config('irc')['main_channel'], PREVIOUS_TOPIC)
                version, is_snapshot, version_text = minecraft.update(args[0], snapshot=False, reply=reply)
            else:
                warning('Usage: update [snapshot <snapshot_id> | <version>]')
        else:
            PREVIOUS_TOPIC = (config('irc')['topic'] + ' | ' if 'topic' in config('irc') and config('irc')['topic'] is not None else '') + 'The server is being updated, wait a sec.'
            bot.topic(config('irc')['main_channel'], PREVIOUS_TOPIC)
            version, is_snapshot, version_text = minecraft.update(snapshot=True, reply=reply)
        try:
            twid = tweet('Server updated to ' + version_text + '! Wheee! See http://minecraft.gamepedia.com/Version_history' + ('/Development_versions#' if is_snapshot else '#') + version + ' for details.')
        except TwitterError as e:
            reply(('...' if context == 'minecraft' else '…') + 'done updating, but the announcement tweet failed.')
        else:
            reply(('...' if context == 'minecraft' else '…') + 'done [https://twitter.com/' + config('twitter').get('screen_name', 'wurstmineberg') + '/status/' + str(twid) + ']')
        update_topic()
    
    def _command_version(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        reply('I am wurstminebot version ' + str(__version__) + ', running on init-minecraft version ' + str(minecraft.__version__))
    
    def _command_whitelist(args=[], permission_level=0, reply=reply, sender=sender, sender_person=None):
        if len(args) in [2, 3]:
            try:
                if len(args) == 3 and args[2] is not None and len(args[2]):
                    screen_name = args[2][1:] if args[2].startswith('@') else args[2]
                else:
                    screen_name = None
                minecraft.whitelist_add(args[0], args[1])
            except ValueError:
                warning('id ' + str(args[0]) + ' already exists')
            else:
                reply(str(args[1]) + ' is now whitelisted')
                if len(args) == 3:
                    set_twitter(nicksub.Person(str(args[0])), str(args[2]))
                    reply('@' + config('twitter')['screen_name'] + ' is now following @' + str(args[2]))
        else:
            warning('Usage: whitelist <unique_id> <minecraft_name> [<twitter_username>]')
    
    commands = {
        'achievementtweet': {
            'description': 'toggle achievement message tweeting',
            'function': _command_achievementtweet,
            'permission_level': 3,
            'usage': '[on | off [<time>]]'
        },
        'alias': {
            'description': 'add, edit, or remove an alias (you can use aliases like regular commands)',
            'function': _command_alias,
            'permission_level': 2,
            'usage': '<alias_name> [<text>...]'
        },
        'command': {
            'description': 'perform Minecraft server command',
            'function': _command_command,
            'permission_level': 4,
            'usage': '<command> [<arguments>...]'
        },
        'deathtweet': {
            'description': 'toggle death message tweeting',
            'function': _command_deathtweet,
            'permission_level': 3,
            'usage': '[on | off [<time>]]'
        },
        'dg': {
            'description': 'record an assassination attempt in the Death Games log',
            'function': _command_dg,
            'permission_level': 3,
            'usage': '(win | fail) [<attacker>] <target>'
        },
        'fixstatus': {
            'description': 'update the server status on the website and in the channel topic',
            'function': update_all,
            'permission_level': 0,
            'usage': None
        },
        'join': {
            'description': 'make the bot join a channel',
            'function': _command_join,
            'permission_level': 4,
            'usage': '<channel>'
        },
        'lastseen': {
            'description': 'when was the player last seen logging in or out on Minecraft',
            'function': _command_lastseen,
            'permission_level': 0,
            'usage': '<player>'
        },
        'leak': {
            'description': 'tweet the last line_count (defaults to 1) chatlog lines',
            'function': _command_leak,
            'permission_level': 2,
            'usage': '[<line_count>]'
        },
        'mwiki': {
            'description': 'look something up in the Minecraft Wiki',
            'function': mwiki_lookup,
            'permission_level': 0,
            'usage': '(<url> | <article>...)'
        },
        'opt': {
            'description': 'change your options',
            'function': _command_opt,
            'permission_level': 1,
            'usage': '<option> [true|false]'
        },
        'pastemojira': {
            'description': 'print the title of a bug in Mojangs bug tracker',
            'function': _command_pastemojira,
            'permission_level': 0,
            'usage': '(<url> | [<project_key>] <issue_id>) [nolink]'
        },
        'pastetweet': {
            'description': 'print the contents of a tweet',
            'function': _command_pastetweet,
            'permission_level': 0,
            'usage': '(<url> | <status_id>) [nolink]'
        },
        'people': {
            'description': 'people.json management',
            'function': _command_people,
            'permission_level': 0,
            'usage': '[<person> [<attribute> [<value>]]]'
        },
        'ping': {
            'description': 'say pong',
            'function': _command_ping,
            'permission_level': 0,
            'usage': None
        },
        'quit': {
            'description': 'stop the bot with a custom quit message',
            'function': _command_quit,
            'permission_level': 4,
            'usage': '[<quit_message>...]'
        },
        'raw': {
            'description': 'send raw message to IRC',
            'function': _command_raw,
            'permission_level': 4,
            'usage': '<raw_message>...'
        },
        'restart': {
            'description': 'restart the Minecraft server or the bot',
            'function': _command_restart,
            'permission_level': 4,
            'usage': '[minecraft | bot]'
        },
        'status': {
            'description': 'print some server status',
            'function': _command_status,
            'permission_level': 0,
            'usage': None
        },
        'stop': {
            'description': 'stop the Minecraft server or the bot',
            'function': _command_stop,
            'permission_level': 4,
            'usage': '[minecraft | bot]'
        },
        'time': {
            'description': 'reply with the current time',
            'function': _command_time,
            'permission_level': 0,
            'usage': None
        },
        'topic': {
            'description': 'temporarily set the channel topic',
            'function': _command_topic,
            'permission_level': 4,
            'usage': '<topic>...'
        },
        'tweet': {
            'description': 'tweet message',
            'function': _command_tweet,
            'permission_level': 4,
            'usage': '<message>...'
        },
        'update': {
            'description': 'update Minecraft',
            'function': _command_update,
            'permission_level': 4,
            'usage': '[snapshot <snapshot_id> | <version>]'
        },
        'version': {
            'description': 'reply with the current version of wurstminebot and init-minecraft',
            'function': _command_version,
            'permission_level': 0,
            'usage': None
        },
        'whitelist': {
            'description': 'add person to whitelist',
            'function': _command_whitelist,
            'permission_level': 4,
            'usage': '<unique_id> <minecraft_name> [<twitter_username>]'
        }
    }
    
    if sender_person is None:
        try:
            sender_person = nicksub.Person(sender, context=context)
        except nicksub.PersonNotFoundError:
            sender_person = None
    elif sender is None:
        sender = sender_person.nick(context, default=sender_person.id)
    
    if cmd.lower() == 'help':
        if len(args) >= 2:
            help_text = 'Usage: help [aliases | commands | <command>]'
        elif len(args) == 0:
            help_text = 'Hello, I am wurstminebot. I sync messages between IRC and Minecraft, and respond to various commands.\nExecute “help commands” for a list of commands, or “help <command>” (replace <command> with a command name) for help on a specific command.\nTo execute a command, send it to me in private chat (here) or address me in ' + config('irc').get('main_channel', '#wurstmineberg') + ' (like this: “wurstminebot: <command>...”). You can also execute commands in a channel or in Minecraft like this: “!<command>...”.'
        elif args[0] == 'aliases':
            num_aliases = len(list(config('aliases').keys()))
            if num_aliases > 0:
                help_text = 'Currently defined aliases: ' + ', '.join(sorted(list(config('aliases').keys()))) + '. For more information, execute “help alias”.'
            else:
                help_text = 'No aliases are currently defined. For more information, execute “help alias”.'
        elif args[0] == 'commands':
            num_aliases = len(list(config('aliases').keys()))
            help_text = 'Available commands: ' + ', '.join(sorted(list(commands.keys()) + ['help'])) + (', and ' + str(num_aliases) + ' aliases.' if num_aliases > 0 else '.')
        elif args[0] == 'help':
            help_text = 'help: get help on a command\nUsage: help [aliases | commands | <command>]'
        elif args[0].lower() in commands:
            help_cmd = args[0].lower()
            help_text = help_cmd + ': ' + commands[help_cmd]['description'] + (' (' + permission_levels[commands[help_cmd]['permission_level']] + ')' if commands[help_cmd].get('permission_level', 0) > 0 else '') + '\nUsage: ' + help_cmd + ('' if commands[help_cmd].get('usage') is None else (' ' + commands[help_cmd]['usage']))
        elif args[0] in config('aliases'):
            help_text = args[0] + ' is an alias. For more information, execute “help alias”.'
        else:
            help_text = errors.unknown(args[0])
        if context == 'irc':
            for line in help_text.splitlines():
                bot.say(sender, line)
        else:
            reply(help_text)
    elif cmd.lower() in commands:
        if nicksub.sub(sender, context, 'irc', strict=False) in [None] + config('irc')['op_nicks']:
            sender_permission_level = 4
        elif sender_person is not None:
            sender_permission_level = 1
            if sender_person.id in config('ops'):
                sender_permission_level = 4
            elif sender_person.whitelisted():
                sender_permission_level = 3
            elif sender_person.invited():
                sender_permission_level = 2
        else:
            sender_permission_level = 0
        if sender_permission_level >= commands[cmd].get('permission_level', 0):
            return commands[cmd]['function'](args=args, permission_level=sender_permission_level, reply=reply, sender=sender, sender_person=sender_person)
        else:
            warning(errors.permission(commands[cmd].get('permission_level', 0)))
    elif cmd in config('aliases'):
        if context == 'irc' and chan == config('irc').get('main_channel', '#wurstmineberg'):
            minecraft.tellraw([
                {
                    'text': '<' + nicksub.sub(sender, 'irc', 'minecraft') + '>',
                    'color': 'aqua',
                    'hoverEvent': {
                        'action': 'show_text',
                        'value': sender + ' in ' + chan
                    },
                    'clickEvent': {
                        'action': 'suggest_command',
                        'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '
                    }
                },
                {
                    'text': ' '
                },
                {
                    'text': config('aliases')[cmd],
                    'color': 'aqua'
                }
            ])
        elif context == 'minecraft':
            minecraft.tellraw([
                {
                    'text': sender,
                    'color': 'gold'
                },
                {
                    'text': ': ',
                    'color': 'gold'
                },
                {
                    'text': config('aliases')[cmd],
                    'color': 'gold'
                }
            ])
        if context == 'irc' and chan is not None:
            bot.say(chan, sender + ': ' + config('aliases')[cmd])
        elif context == 'irc' and sender is not None:
            bot.say(sender, config('aliases')[cmd])
        elif context == 'minecraft':
            bot.say(config('irc').get('main_channel'), '<' + (sender if sender_person is None else sender_person.irc_nick()) + '> ' + config('aliases')[cmd])
    else:
        warning(errors.unknown(cmd))

def endMOTD(sender, headers, message):
    irc_config = config('irc')
    chans = set(irc_config.get('channels', []))
    if 'main_channel' in irc:
        chans.add(irc_config['main_channel'])
    if 'dev_channel' in irc:
        chans.add(irc_config['dev_channel'])
    if 'live_channel' in irc:
        chans.add(irc_config['live_channel'])
    for chan in chans:
        bot.joinchan(chan)
    bot.say(irc_config['main_channel'], "aaand I'm back.")
    minecraft.tellraw({'text': "aaand I'm back.", 'color': 'gold'})
    _debug_print("aaand I'm back.")
    update_all()
    threading.Timer(20, minecraft.update_status).start()
    InputLoop.start()

bot.bind('376', endMOTD)

def action(sender, headers, message):
    try:
        if sender == config('irc').get('nick', 'wurstminebot'):
            return
        if headers[0] == config('irc')['main_channel']:
            minecraft.tellraw({'text': '', 'extra': [{'text': '* ' + nicksub.sub(sender, 'irc', 'minecraft'), 'color': 'aqua', 'hoverEvent': {'action': 'show_text', 'value': sender + ' in ' + headers[0]}, 'clickEvent': {'action': 'suggest_command', 'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '}}, {'text': ' '}, {'text': nicksub.textsub(message, 'irc', 'minecraft'), 'color': 'aqua'}]})
    except SystemExit:
        _debug_print('Exit in ACTION')
        InputLoop.stop()
        TimeLoop.stop()
        raise
    except:
        _debug_print('Exception in ACTION:')
        if config('debug', False):
            traceback.print_exc()

bot.bind('ACTION', action)

def join(sender, headers, message):
    if len(headers):
        chan = headers[0]
    elif message is not None and len(message):
        chan = message
    else:
        return
    with open(config('paths')['people']) as people_json:
        people = json.load(people_json)
    for person in nicksub.everyone():
        if person.minecraft is not None and person.option('sync_join_part'):
            minecraft.tellraw([
                {
                    'text': sender,
                    'color': 'yellow',
                    'clickEvent': {
                        'action': 'suggest_command',
                        'value': sender + ': '
                    }
                },
                {
                    'text': ' joined ' + chan,
                    'color': 'yellow'
                }
            ], player=person.minecraft)

bot.bind('JOIN', join)

def nick(sender, headers, message):
    if message is None or len(message) == 0:
        return
    for person in nicksub.everyone():
        if person.minecraft is not None and person.option('sync_nick_changes'):
            minecraft.tellraw([
                {
                    'text': sender + ' is now known as ',
                    'color': 'yellow'
                },
                {
                    'text': message,
                    'color': 'yellow',
                    'clickEvent': {
                        'action': 'suggest_command',
                        'value': message + ': '
                    }
                }
            ], player=person.minecraft)

def part(sender, headers, message):
    chans = headers[0].split(',')
    if len(chans) == 0:
        return
    elif len(chans) == 1:
        chans = chans[0]
    elif len(chans) == 2:
        chans = chans[0] + ' and ' + chans[1]
    else:
        chans = ', '.join(chans[:-1]) + ', and ' + chans[-1]
    for person in nicksub.everyone():
        if person.minecraft is not None and person.option('sync_join_part'):
            minecraft.tellraw({
                'text': sender + ' left ' + chans,
                'color': 'yellow'
            }, player=person.minecraft)

bot.bind('PART', part)

def privmsg(sender, headers, message):
    irc_config = config('irc')
    def botsay(msg):
        for line in msg.splitlines():
            bot.say(irc_config['main_channel'], line)
    
    try:
        _debug_print('[irc] <' + sender + '> ' + message)
        if sender == irc_config.get('nick', 'wurstminebot'):
            if headers[0] == irc_config.get('dev_channel') and irc_config.get('dev_channel') != irc_config.get('main_channel'):
                # sync commit messages from dev to main
                bot.say(irc_config.get('main_channel', '#wurstmineberg'), message)
            return
        if headers[0].startswith('#'):
            if message.startswith(irc_config.get('nick', 'wurstminebot') + ': ') or message.startswith(irc_config['nick'] + ', '):
                cmd = message[len(irc_config.get('nick', 'wurstminebot')) + 2:].split(' ')
                if len(cmd):
                    try:
                        command(cmd[0], args=cmd[1:], sender=sender, chan=headers[0], context='irc')
                    except SystemExit:
                        raise
                    except Exception as e:
                        bot.say(headers[0], sender + ': Error: ' + str(e))
                        _debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]) + ':')
                        if config('debug', False):
                            traceback.print_exc()
            elif message.startswith('!') and not re.match('!+$', message):
                cmd = message[1:].split(' ')
                if len(cmd):
                    try:
                        command(cmd[0], args=cmd[1:], sender=sender, chan=headers[0], context='irc')
                    except SystemExit:
                        raise
                    except Exception as e:
                        bot.say(headers[0], sender + ': Error: ' + str(e))
                        _debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to ' + str(headers[0]) + ':')
                        if config('debug', False):
                            traceback.print_exc()
            elif headers[0] == irc_config.get('main_channel'):
                if re.match('https?://mojang\\.atlassian\\.net/browse/[A-Z]+-[0-9]+', message):
                    minecraft.tellraw([
                        {
                            'text': '<' + nicksub.sub(sender, 'irc', 'minecraft') + '>',
                            'color': 'aqua',
                            'hoverEvent': {
                                'action': 'show_text',
                                'value': sender + ' in ' + headers[0]
                            },
                            'clickEvent': {
                                'action': 'suggest_command',
                                'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '
                            }
                        },
                        {
                            'text': ' '
                        },
                        {
                            'text': message,
                            'color': 'aqua',
                            'clickEvent': {
                                'action': 'open_url',
                                'value': message
                            }
                        }
                    ])
                    try:
                        command('pastemojira', args=[message, 'nolink'], reply_format='tellraw')
                        command('pastemojira', args=[message, 'nolink'], context='irc', sender=sender, chan=headers[0], reply=botsay)
                    except SystemExit:
                        raise
                    except Exception as e:
                        bot.say(headers[0], 'Error pasting mojira ticket: ' + str(e))
                        _debug_print('Exception while pasting mojira ticket:')
                        if config('debug', False):
                            traceback.print_exc()
                elif re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/[0-9]+$', message):
                    minecraft.tellraw([
                        {
                            'text': '<' + nicksub.sub(sender, 'irc', 'minecraft') + '>',
                            'color': 'aqua',
                            'hoverEvent': {
                                'action': 'show_text',
                                'value': sender + ' in ' + headers[0]
                            },
                            'clickEvent': {
                                'action': 'suggest_command',
                                'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '
                            }
                        },
                        {
                            'text': ' '
                        },
                        {
                            'text': message,
                            'color': 'aqua',
                            'clickEvent': {
                                'action': 'open_url',
                                'value': message
                            }
                        }
                    ])
                    try:
                        twid = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)$', message).group(1)
                        minecraft.tellraw(pastetweet(twid, link=False, tellraw=True))
                        botsay(pastetweet(twid, link=False, tellraw=False))
                    except SystemExit:
                        raise
                    except Exception as e:
                        bot.say(headers[0], 'Error while pasting tweet: ' + str(e))
                        _debug_print('Exception while pasting tweet:')
                        if config('debug', False):
                            traceback.print_exc()
                else:
                    match = re.match('([a-z0-9]+:[^ ]+)(.*)$', message)
                    if match:
                        url, remaining_message = match.group(1, 2)
                        minecraft.tellraw([
                            {
                                'text': '<' + nicksub.sub(sender, 'irc', 'minecraft') + '>',
                                'color': 'aqua',
                                'hoverEvent': {
                                    'action': 'show_text',
                                    'value': sender + ' in ' + headers[0]
                                },
                                'clickEvent': {
                                    'action': 'suggest_command',
                                    'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '
                                }
                            },
                            {
                                'text': ' '
                            },
                            {
                                'text': url,
                                'color': 'aqua',
                                'clickEvent': {
                                    'action': 'open_url',
                                    'value': url
                                }
                            },
                            {
                                'text': remaining_message,
                                'color': 'aqua'
                            }
                        ])
                    else:
                        minecraft.tellraw({
                            'text': '',
                            'extra': [
                                {
                                    'text': '<' + nicksub.sub(sender, 'irc', 'minecraft') + '>',
                                    'color': 'aqua',
                                    'hoverEvent': {
                                        'action': 'show_text',
                                        'value': sender + ' in ' + headers[0]
                                    },
                                    'clickEvent': {
                                        'action': 'suggest_command',
                                        'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '
                                    }
                                },
                                {
                                    'text': ' '
                                },
                                {
                                    'text': nicksub.textsub(message, 'irc', 'minecraft'),
                                    'color': 'aqua'
                                }
                            ]
                        })
        else:
            cmd = message.split(' ')
            if len(cmd):
                try:
                    command(cmd[0], args=cmd[1:], sender=sender, context='irc')
                except SystemExit:
                    raise
                except Exception as e:
                    bot.say(sender, 'Error: ' + str(e))
                    _debug_print('Exception in ' + str(cmd[0]) + ' command from ' + str(sender) + ' to query:')
                    if config('debug', False):
                        traceback.print_exc()
    except SystemExit:
        _debug_print('Exit in PRIVMSG')
        InputLoop.stop()
        TimeLoop.stop()
        raise
    except:
        _debug_print('Exception in PRIVMSG:')
        if config('debug', False):
            traceback.print_exc()

bot.bind('PRIVMSG', privmsg)

def run():
    bot.debugging(config('debug'))
    TimeLoop.start()
    try:
        bot.run()
    except Exception:
        InputLoop.stop()
        TimeLoop.stop()
        _debug_print('Exception in bot.run:')
        if config('debug', False):
            traceback.print_exc()
        sys.exit(1)
    InputLoop.stop()
    TimeLoop.stop()

def newDaemonContext(pidfilename):
    if not os.geteuid() == 0:
        sys.exit("\nOnly root can start/stop the daemon!\n")
    
    pidfile = daemon.pidlockfile.PIDLockFile(pidfilename)
    logfile = open("/opt/wurstmineberg/log/wurstminebot.log", "a")
    daemoncontext = daemon.DaemonContext(working_directory = '/opt/wurstmineberg/',
                                         pidfile = pidfile,
                                         uid = 1000, gid = 1000,
                                         stdout = logfile, stderr = logfile)
    
    daemoncontext.files_preserve = [logfile]
    daemoncontext.signal_map = {
        signal.SIGTERM: bot.stop,
        signal.SIGHUP: bot.stop,
    }
    return daemoncontext

def start(context):
    print("Starting wurstminebot version", __version__)

    if status(context.pidfile):
        print("Already running!")
        return
    else:
        # Removes the PID file
        stop(context)
    
    print("Daemonizing...")
    with context:
        print("Daemonized.")
        run()
        print("Terminating...")

def status(pidfile):
    if pidfile.is_locked():
        return os.path.exists("/proc/" + str(pidfile.read_pid()))
    return False

def stop(context):
    InputLoop.stop()
    TimeLoop.stop()
    if status(context.pidfile):
        print("Stopping the service...")
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
        print("Service did not shutdown correctly. Cleaning up...")
        context.pidfile.break_lock()

if __name__ == '__main__':
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
        print('wurstminebot ' + ('is' if status(pidfile) else 'is not') + ' running.')
    else:
        run()
