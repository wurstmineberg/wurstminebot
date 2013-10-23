#!/usr/bin/env python3
"""Minecraft IRC bot.

Usage:
  wurstminebot [options] [start | stop | restart | status]
  wurstminebot -h | --help
  wurstminebot --version

Options:
  --config=<config>  Path to the config file [default: /opt/wurstmineberg/config/wurstminebot.json].
  -h, --help         Print this message and exit.
  --version          Print version info and exit.
"""

__version__ = '1.4.9'

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
import subprocess
import threading
import time
from datetime import timedelta
import xml.sax.saxutils

CONFIG_FILE = '/opt/wurstmineberg/config/wurstminebot.json'
if __name__ == '__main__':
    arguments = docopt(__doc__, version='wurstminebot ' + __version__)
    CONFIG_FILE = arguments['--config']

def _debug_print(msg):
    if config('debug'):
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
        'advanced_comment_lines': {
            'death': [],
            'server_join': []
        },
        'comment_lines': {
            'death': ['Well done.'],
            'server_join': []
        },
        'debug': False,
        'irc': {
            'channels': [],
            'op_nicks': [],
            'password': '',
            'port': 6667,
            'ssl': False,
            'topic': None
        },
        'paths': {
            'assets': '/var/www/wurstmineberg.de/assets/serverstatus',
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

ACHIEVEMENTTWEET = True
DEATHTWEET = True
DST = bool(time.localtime().tm_isdst)
LASTDEATH = ''
TOPIC = config('irc')['topic']

bot = ircBot(config('irc')['server'], config('irc')['port'], config('irc')['nick'], config('irc')['nick'], password=config('irc')['password'], ssl=config('irc')['ssl'])
bot.log_own_messages = False

twitter = TwitterAPI(config('twitter')['consumer_key'], config('twitter')['consumer_secret'], config('twitter')['access_token_key'], config('twitter')['access_token_secret'])

def _timed_input(timeout=1): #FROM http://stackoverflow.com/a/2904057
    i, o, e = select.select([sys.stdin], [], [], timeout)
    if i:
        return sys.stdin.readline().strip()

class errors:
    botop = 'you must be a bot op to do this'
    log = "I can't find that in my chatlog"
    unknown = 'unknown command'
    
    @staticmethod
    def argc(expected, given, atleast=False):
        return ('not enough' if given < expected else 'too many') + ' arguments, expected ' + ('at least ' if atleast else '') + str(expected)

def update_all(*args, **kwargs):
    minecraft.update_status()
    minecraft.update_whitelist()
    update_topic()
    threading.Timer(20, minecraft.update_status).start()

class InputLoop(threading.Thread):
    def run(self):
        global LASTDEATH
        for logLine in _logtail():
            # server log output processing
            _debug_print('[logpipe] ' + logLine)
            match = re.match(minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: \\* (' + minecraft.regexes.player + ') (.*)', logLine)
            if match:
                # action
                player, message = match.group(1, 2)
                chan = config('irc')['main_channel']
                sender = nicksub.sub(player, 'minecraft', 'irc')
                subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                bot.log(chan, 'ACTION', sender, [chan], subbed_message)
                bot.say(chan, '* ' + sender + ' ' + subbed_message)
            else:
                match = re.match(minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: <(' + minecraft.regexes.player + ')> (.*)', logLine)
                if match:
                    player, message = match.group(1, 2)
                    if message.startswith('!') and len(message) > 1:
                        # command
                        cmd = message[1:].split(' ')
                        command(sender=player, chan=None, cmd=cmd[0], args=cmd[1:], context='minecraft')
                    else:
                        # chat message
                        chan = config('irc')['main_channel']
                        sender = nicksub.sub(player, 'minecraft', 'irc')
                        subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                        bot.log(chan, 'PRIVMSG', sender, [chan], subbed_message)
                        bot.say(chan, '<' + sender + '> ' + subbed_message)
                else:
                    match = re.match('(' + minecraft.regexes.timestamp + ') \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') (left|joined) the game', logLine)
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
                                welcome_message = 'Welcome to the server!'
                            else:
                                welcome_messages = dict(((1, index), 1.0) for index in range(len(config('comment_lines').get('server_join', []))))
                                with open(config('paths')['people']) as people_json:
                                    people = json.load(people_json)
                                for person in people:
                                    if person['minecraft'] == player:
                                        if 'description' not in person:
                                            welcome_messages[0, 1] = 1.0
                                        break
                                else:
                                    welcome_messages[0, 2] = 16.0
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
                                        'text': '. Write one today and send it to ',
                                        'color': 'gray'
                                    },
                                    {
                                        'text': 'Jemus42',
                                        'clickEvent': {
                                            'action': 'suggest_command',
                                            'value': 'Jemus42: '
                                        },
                                        'color': 'gray'
                                    },
                                    {
                                        'text': ' or ',
                                        'color': 'gray'
                                    },
                                    {
                                        'text': 'Fenhl',
                                        'clickEvent': {
                                            'action': 'suggest_command',
                                            'value': 'Fenhl: '
                                        },
                                        'color': 'gray'
                                    },
                                    {
                                        'text': '!',
                                        'color': 'gray'
                                    }
                                ])
                            elif welcome_message[0] == 1:
                                minecraft.tellraw({'text': 'Hello ' + player + '. ' + config('comment_lines')['server_join'][welcome_message[1]], 'color': 'gray'}, player)
                            elif welcome_message[0] == 2:
                                message_list = config('advanced_comment_lines')['server_join'][welcome_message[1]]
                                if isinstance(message_list, str):
                                    message_list = [{'text': message_list, 'color': 'gray'}]
                                elif isinstance(message_list, dict):
                                    message_list = [message_list]
                                minecraft.tellraw([
                                    {
                                        'text': 'Hello ' + player + '. ',
                                        'color': 'gray'
                                    }
                                ] + message_list)
                            else:
                                minecraft.tellraw({'text': 'Hello ' + player + '. How did you do that?', 'color': 'gray'}, player)
                        #bot.say(config('irc')['main_channel'], nicksub.sub(player, 'minecraft', 'irc') + ' ' + ('joined' if joined else 'left') + ' the game')
                        update_all()
                    else:
                        match = re.match(minecraft.regexes.timestamp + ' \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') has just earned the achievement \\[(.+)\\]$', logLine)
                        if match:
                            # achievement
                            player, achievement = match.group(1, 2)
                            if ACHIEVEMENTTWEET:
                                tweet = '[Achievement Get] ' + nicksub.sub(player, 'minecraft', 'twitter') + ' got ' + achievement
                                if len(tweet) <= 140:
                                    tweet_request = twitter.request('statuses/update', {'status': tweet})
                                    if 'id' in tweet_request.json():
                                        twid = 'https://twitter.com/wurstmineberg/status/' + str(tweet_request.json()['id'])
                                    else:
                                        twid = 'error ' + str(tweet_request.status_code)
                                else:
                                    twid = 'too long for twitter'
                            else:
                                twid = 'achievement tweets are disabled'
                            bot.say(config('irc')['main_channel'], 'Achievement Get: ' + nicksub.sub(player, 'minecraft', 'irc') + ' got ' + achievement + ' [' + twid + ']')
                        else:
                            for deathid, death in enumerate(deaths.regexes):
                                match = re.match('(' + minecraft.regexes.timestamp + ') \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') ' + death + '$', logLine)
                                if not match:
                                    continue
                                # death
                                timestamp, player = match.group(1, 2)
                                groups = match.groups()[2:]
                                message = deaths.partial_message(deathid, groups)
                                with open(os.path.join(config('paths')['logs'], 'deaths.log'), 'a') as deathslog:
                                    print(timestamp + ' ' + player + ' ' + message, file=deathslog)
                                if DEATHTWEET:
                                    if player + ' ' + message == LASTDEATH:
                                        comment = ' … Again.' # This prevents botspam if the same player dies lots of times (more than twice) for the same reason.
                                    else:
                                        death_comments = config('comment_lines').get('death', ['Well done.'])
                                        if deathid == 7: # was blown up by Creeper
                                            death_comments.append('Creepers gonna creep.')
                                        if deathid == 28: # was slain by Zombie
                                            death_comments.append('Zombies gonna zomb.')
                                        comment = ' … ' + random.choice(death_comments)
                                    LASTDEATH = player + ' ' + message
                                    tweet = '[DEATH] ' + nicksub.sub(player, 'minecraft', 'twitter') + ' ' + nicksub.textsub(message, 'minecraft', 'twitter', strict=True)
                                    if len(tweet + comment) <= 140:
                                        tweet += comment
                                    if len(tweet) <= 140:
                                        tweet_request = twitter.request('statuses/update', {'status': tweet})
                                        if 'id' in tweet_request.json():
                                            twid = 'https://twitter.com/wurstmineberg/status/' + str(tweet_request.json()['id'])
                                            minecraft.tellraw({'text': 'Your fail has been reported. Congratulations.', 'color': 'gold', 'clickEvent': {'action': 'open_url', 'value': twid}})
                                        else:
                                            twid = 'error ' + str(tweet_request.status_code)
                                            minecraft.tellraw({'text': 'Your fail has ', 'color': 'gold', 'extra': [{'text': 'not', 'color': 'red'}, {'text': ' been reported because of '}, {'text': 'reasons', 'hoverEvent': {'action': 'show_text', 'value': str(tweet_request.status_code)}}, {'text': '.'}]})
                                    else:
                                        twid = 'too long for twitter'
                                        minecraft.tellraw({'text': 'Your fail has ', 'color': 'gold', 'extra': [{'text': 'not', 'color': 'red'}, {'text': ' been reported because it was too long.'}]})
                                else:
                                    twid = 'deathtweets are disabled'
                                bot.say(config('irc')['main_channel'], nicksub.sub(player, 'minecraft', 'irc') + ' ' + nicksub.textsub(message, 'minecraft', 'irc', strict=True) + ' [' + twid + ']')
                                break
            if not bot.keepGoing:
                break

class TimeLoop(threading.Thread):
    def run(self):
        #FROM http://stackoverflow.com/questions/9918972/running-a-line-in-1-hour-intervals-in-python
        # modified to work with leap seconds
        while True:
            # sleep for the remaining seconds until the next hour
            time.sleep(3601 - time.time() % 3600)
            telltime(comment=True)

def telltime(func=None, comment=False, restart=False):
    if func is None:
        def func(msg):
            for line in msg.splitlines():
                minecraft.tellraw({'text': line, 'color': 'gold'})
        
        custom_func = False
    else:
        custom_func = True
    def warning(msg):
        if custom_func:
            func(msg)
        else:
            for line in msg.splitlines():
                minecraft.tellraw({'text': line, 'color': 'red'})
    
    global DST
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
            populated = bool(len(minecraft.online_players()))
            if populated:
                warning('The server is going to restart in 5 minutes.')
                time.sleep(240)
                warning('The server is going to restart in 60 seconds.')
                time.sleep(50)
            minecraft.stop()
            time.sleep(30)
            if minecraft.start():
                if populated:
                    bot.say('The server has restarted.')
            else:
                bot.say('Please help! Something went wrong with the server restart!')
    DST = dst

def update_topic():
    players = minecraft.online_players()
    player_list = ('Currently online: ' + ', '.join(players)) if len(players) else ''
    if TOPIC is None:
        bot.topic(config('irc')['main_channel'], player_list)
    elif len(players):
        bot.topic(config('irc')['main_channel'], TOPIC + ' | ' + player_list)
    else:
        bot.topic(config('irc')['main_channel'], TOPIC)

def command(sender, chan, cmd, args, context='irc', reply=None, reply_format=None):
    if reply is None:
        if reply_format == 'tellraw' or context == 'minecraft':
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
                elif context == 'console':
                    print(msg)
    
    def warning(msg):
        if reply_format == 'tellraw':
            reply({'text': msg, 'color': 'red'})
        else:
            reply(msg)
    
    def _command_achievementtweet(args=[], botop=False):
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
            
            if len(args) >= 2:
                match = re.match('([0-9]+)([dhms])', args[1])
                if match:
                    number, unit = match.group(1, 2)
                    number *= {'d': 86400, 'h': 3600, 'm': 60, 's': 1}[unit]
                elif re.match('[0-9]+', args[1]):
                    number = int(args[1])
                else:
                    warning(args[1] + ' is not a time value')
                    return
                threading.Timer(number, _reenable_death_tweets).start()
            elif not botop:
                warning(errors.botop)
                return
            ACHIEVEMENTTWEET = False
            reply('Achievement tweeting is now disabled')
        else:
            warning('first argument needs to be “on” or “off”')
    
    def _command_command(args=[], botop=False):
        if args[0]:
            reply(minecraft.command(args[0], args[1:]))
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_deathtweet(args=[], botop=False):
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
            
            if len(args) >= 2:
                match = re.match('([0-9]+)([dhms])', args[1])
                if match:
                    number, unit = match.group(1, 2)
                    number *= {'d': 86400, 'h': 3600, 'm': 60, 's': 1}[unit]
                elif re.match('[0-9]+', args[1]):
                    number = int(args[1])
                else:
                    warning(args[1] + ' is not a time value')
                    return
                threading.Timer(number, _reenable_death_tweets).start()
            elif not botop:
                warning(errors.botop)
                return
            DEATHTWEET = False
            reply('Deathtweeting is now disabled')
        else:
            warning('first argument needs to be “on” or “off”')
    
    def _command_lastseen(args=[], botop=False):
        if len(args):
            player = args[0]
            mcplayer = nicksub.sub(player, context, 'minecraft', strict=False)
            if mcplayer in minecraft.online_players():
                if reply_format == 'tellraw':
                    reply([
                        {
                            'text': player,
                            'hoverEvent': {
                                'action': 'show_text',
                                'value': mcplayer + ' in Minecraft'
                            },
                            'clickEvent': {
                                'action': 'suggest_command',
                                'value': mcplayer + ': '
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
                lastseen = minecraft.last_seen(mcplayer)
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
                                    'value': mcplayer + ' in Minecraft'
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
    
    def _command_leak(args=[], botop=False):
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
        tweet = '\n'.join(((('* ' + nicksub.sub(msg_sender, 'irc', 'twitter') + ' ') if msg_type == 'ACTION' else ('<' + nicksub.sub(msg_sender, 'irc', 'twitter') + '> ')) + nicksub.textsub(message, 'irc', 'twitter')) for msg_type, msg_sender, message in messages)
        if len(tweet + ' #ircleaks') <= 140:
            if '\n' in tweet:
                tweet += '\n#ircleaks'
            else:
                tweet += ' #ircleaks'
        command(None, chan, 'tweet', [tweet], context='twitter', reply=reply, reply_format=reply_format)
    
    def _command_pastemojira(args=[], botop=False):
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
    
    def _command_pastetweet(args=[], botop=False):
        link = True
        if len(args) == 2 and args[1] == 'nolink':
            link = False
            args = [args[0]]
        if len(args) == 1:
            match = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)', str(args[0]))
            twid = match.group(1) if match else args[0]
            request = twitter.request('statuses/show', {'id': twid})
            if 'id' in request.json():
                if 'retweeted_status' in request.json():
                    retweeted_request = twitter.request('statuses/show', {'id': request.json()['retweeted_status']['id']})
                    tweet_author = '<@' + request.json()['user']['screen_name'] + ' RT @' + retweeted_request.json()['user']['screen_name'] + '> '
                    tweet_author_tellraw = [
                        {
                            'text': '@' + request.json()['user']['screen_name'],
                            'clickEvent': {
                                'action': 'open_url',
                                'value': 'https://twitter.com/' + request.json()['user']['screen_name']
                            },
                            'color': 'gold'
                        },
                        {
                            'text': ' RT ',
                            'color': 'gold'
                        },
                        {
                            'text': '@' + retweeted_request.json()['user']['screen_name'],
                            'clickEvent': {
                                'action': 'open_url',
                                'value': 'https://twitter.com/' + retweeted_request.json()['user']['screen_name']
                            },
                            'color': 'gold'
                        }
                    ]
                    text = xml.sax.saxutils.unescape(retweeted_request.json()['text'])
                else:
                    tweet_author = '<@' + request.json()['user']['screen_name'] + '> '
                    tweet_author_tellraw = [
                        {
                            'text': '@' + request.json()['user']['screen_name'],
                            'clickEvent': {
                                'action': 'open_url',
                                'value': 'https://twitter.com/' + request.json()['user']['screen_name']
                            },
                            'color': 'gold'
                        }
                    ]
                    text = xml.sax.saxutils.unescape(request.json()['text'])
                tweet_url = 'https://twitter.com/' + request.json()['user']['screen_name'] + '/status/' + request.json()['id_str']
                if reply_format == 'tellraw':
                    reply({
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
                    })
                else:
                    reply(tweet_author + text + ((' [' + tweet_url + ']') if link else ''))
            else:
                warning('Error ' + str(request.status_code))
        else:
            warning(errors.argc(1, len(args)))
    
    def _command_people(args=[], botop=False):
        if len(args):
            with open(config('paths')['people']) as people_json:
                people = json.load(people_json)
            for person in people:
                if person['id'] == args[0]:
                    break
            else:
                warning('no person with id ' + str(args[0]) + ' in people.json')
                return
            can_edit = isbotop or (context == 'minecraft' and 'minecraft' in person and person['minecraft'] == sender) or (context == 'irc' and 'irc' in person and 'nicks' in person['irc'] and sender in person['irc']['nicks'])
            if len(args) >= 2:
                if args[1] == 'description':
                    if len(args) == 2:
                        reply(person.get('description', 'no description'))
                        return
                    elif can_edit:
                        person['description'] = ' '.join(args[2:])
                        with open(config('paths')['people'], 'w') as people_json:
                            json.dump(people, people_json, indent=4, separators=(',', ': '), sort_keys=True)
                        reply('description updated')
                    else:
                        warning(errors.botop)
                        return
                elif args[1] == 'name':
                    if len(args) == 2:
                        reply(person.get('name', 'no name, using id: ' + person['id']))
                    elif can_edit:
                        had_name = 'name' in person
                        person['name'] = ' '.join(args[2:])
                        with open(config('paths')['people'], 'w') as people_json:
                            json.dump(people, people_json, indent=4, separators=(',', ': '), sort_keys=True)
                        reply('name ' + ('changed' if had_name else 'added'))
                    else:
                        warning(errors.botop)
                        return
                elif args[1] == 'reddit':
                    if len(args) == 2:
                        reply(('/u/' + person['reddit']) if 'reddit' in person else 'no reddit nick')
                    elif can_edit:
                        had_reddit_nick = 'reddit' in person
                        reddit_nick = args[2][3:] if args[2].startswith('/u/') else args[2]
                        person['reddit'] = reddit_nick
                        with open(config('paths')['people'], 'w') as people_json:
                            json.dump(people, people_json, indent=4, separators=(',', ': '), sort_keys=True)
                        reply('reddit nick ' + ('changed' if had_reddit_nick else 'added'))
                    else:
                        warning(errors.botop)
                        return
                elif args[1] == 'twitter':
                    if len(args) == 2:
                        reply(('@' + person['twitter']) if 'twitter' in person else 'no twitter nick')
                        return
                    elif can_edit:
                        screen_name = args[2][1:] if args[2].startswith('@') else args[2]
                        person['twitter'] = screen_name
                        with open(config('paths')['people'], 'w') as people_json:
                            json.dump(people, people_json, indent=4, separators=(',', ': '), sort_keys=True)
                        twitter.request('lists/members/create', {'list_id': 94629160, 'screen_name': screen_name})
                        twitter.request('friendships/add', {'screen_name': screen_name})
                        reply('@' + config('twitter')['screen_name'] + ' is now following @' + screen_name)
                    else:
                        warning(errors.botop)
                        return
                elif args[1] == 'website':
                    if len(args) == 2:
                        reply(person['website'] if 'website' in person else 'no website')
                    elif can_edit:
                        had_website = 'website' in person
                        person['website'] = str(args[2])
                        with open(config('paths')['people'], 'w') as people_json:
                            json.dump(people, people_json, indent=4, separators=(',', ': '), sort_keys=True)
                        reply('website ' + ('changed' if had_website else 'added'))
                    else:
                        warning(errors.botop)
                        return
                else:
                    warning('no such people attribute: ' + str(args[1]))
                    return
            else:
                if 'name' in person:
                    reply('person with id ' + str(args[0]) + ' and name ' + person['name'])
                else:
                    reply('person with id ' + str(args[0]) + ' and no name')
        else:
            reply('http://wurstmineberg.de/people')
    
    def _command_ping(args=[], botop=False):
        if random.randrange(1024) == 0:
            reply('BWO' + 'R' * random.randint(3, 20) + 'N' * random.randing(1, 5) + 'G') # PINGCEPTION
        else:
            reply('pong')
    
    def _command_quit(args=[], botop=False):
        quitMsg = ' '.join(args) if len(args) else None
        if context != 'minecraft':
            minecraft.tellraw({'text': ('Restarting the bot: ' + quitMsg) if quitMsg else 'Restarting the bot...', 'color': 'red'})
        if (context != 'irc') or (chan is None):
            bot.say(config('irc')['main_channel'], ('brb, ' + quitMsg) if quitMsg else random.choice(['Please wait while I reinstall the universe.', 'brb', 'Please hang tight, I seem to have exploded.']))
        bot.disconnect(quitMsg if quitMsg else 'brb')
        bot.stop()
        sys.exit()
    
    def _command_raw(args=[], botop=False):
        if len(args):
            bot.send(' '.join(args))
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_status(args=[], botop=False):
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
    
    def _command_time(args=[], botop=False):
        telltime(func=reply)
    
    def _command_topic(args=[], botop=False):
        if len(args):
            TOPIC = ' '.join(args)
            update_topic()
            reply('Topic changed temporarily. To change permanently, edit /opt/wurstmineberg/config/wurstminebot.json')
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_tweet(args=[], botop=False):
        if len(args):
            tweet = nicksub.textsub(' '.join(args), context, 'twitter')
            if len(tweet) > 140:
                warning('too long')
            else:
                r = twitter.request('statuses/update', {'status': tweet})
                if 'id' in r.json():
                    url = 'https://twitter.com/wurstmineberg/status/' + str(r.json()['id'])
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
                        command(None, None, 'pastetweet', [r.json()['id']], reply_format='tellraw')
                    if context == 'irc' and chan == config('irc')['main_channel']:
                        bot.say(chan, url)
                    else:
                        command(None, None, 'pastetweet', [r.json()['id']], reply=lambda msg: bot.say(config('irc')['main_channel'] if chan is None else chan, msg))
                else:
                    warning('Error ' + str(r.status_code))
        else:
            warning(errors.argc(1, len(args), atleast=True))
    
    def _command_update(args=[], botop=False):
        if len(args):
            if args[0] == 'snapshot':
                if len(args) == 2:
                    minecraft.update(args[1], snapshot=True)
                else:
                    warning('Usage: update (snapshot <snapshot_id> | <version>)')
            elif len(args) == 1:
                minecraft.update(args[0], snapshot=False)
            else:
                warning('Usage: update (snapshot <snapshot_id> | <version>)')
        else:
            warning('Usage: update (snapshot <snapshot_id> | <version>)')
    
    def _command_whitelist(args=[], botop=False):
        if len(args) == 2:
            try:
                minecraft.whitelist_add(args[0], args[1])
            except ValueError:
                warning('id ' + str(args[0]) + ' already exists')
            else:
                reply(str(args[1]) + ' is now whitelisted')
        else:
            warning('Usage: whitelist <unique_id> <minecraft_name>')
    
    commands = {
        'achievementtweet': {
            'description': 'toggle achievement message tweeting',
            'function': _command_achievementtweet,
            'usage': '[on | off [<time>]]'
        },
        'command': {
            'botop_only': True,
            'description': 'perform Minecraft server command',
            'function': _command_command,
            'usage': '<command> [<arguments>...]',
        },
        'deathtweet': {
            'description': 'toggle death message tweeting',
            'function': _command_deathtweet,
            'usage': '[on | off [<time>]]'
        },
        'fixstatus': {
            'description': 'update the server status on the website and in the channel topic',
            'function': update_all,
            'usage': None
        },
        'lastseen': {
            'description': 'when was the player last seen logging in or out on Minecraft',
            'function': _command_lastseen,
            'usage': '<player>'
        },
        'leak': {
            'description': 'tweet the last line_count (defaults to 1) chatlog lines',
            'function': _command_leak,
            'usage': '[<line_count>]'
        },
        'pastemojira': {
            'description': 'print the title of a bug in Mojangs bug tracker',
            'function': _command_pastemojira,
            'usage': '(<url> | [<project_key>] <issue_id>) [nolink]'
        },
        'pastetweet': {
            'description': 'print the contents of a tweet',
            'function': _command_pastetweet,
            'usage': '(<url> | <status_id>) [nolink]'
        },
        'people': {
            'description': 'people.json management',
            'function': _command_people,
            'usage': '[<person> [<attribute> [<value>]]]'
        },
        'ping': {
            'description': 'say pong',
            'function': _command_ping,
            'usage': None
        },
        'quit': {
            'botop_only': True,
            'description': 'quit the IRC bot',
            'function': _command_quit,
            'usage': '[<quit_message>...]'
        },
        'raw': {
            'botop_only': True,
            'description': 'send raw message to IRC',
            'function': _command_raw,
            'usage': '<raw_message>...'
        },
        'restart': {
            'botop_only': True,
            'description': 'restart the Minecraft server',
            'function': minecraft.restart,
            'usage': None
        },
        'status': {
            'description': 'print some server status',
            'function': _command_status,
            'usage': None
        },
        'stop': {
            'botop_only': True,
            'description': 'stop the Minecraft server',
            'function': minecraft.stop,
            'usage': None
        },
        'time': {
            'description': 'reply with the current time',
            'function': _command_time,
            'usage': None
        },
        'topic': {
            'botop_only': True,
            'description': 'temporarily set the channel topic',
            'function': _command_topic,
            'usage': '<topic>...'
        },
        'tweet': {
            'botop_only': True,
            'description': 'tweet message',
            'function': _command_tweet,
            'usage': '<message>...'
        },
        'update': {
            'botop_only': True,
            'description': 'update Minecraft',
            'function': _command_update,
            'usage': '(snapshot <snapshot_id> | <version>)'
        },
        'whitelist': {
            'botop_only': True,
            'description': 'add person to whitelist',
            'function': _command_whitelist,
            'usage': 'whitelist <unique_id> <minecraft_name>'
        }
    }
    
    if cmd == 'help':
        if len(args) >= 2:
            help_text = 'Usage: help [commands | <command>]'
        elif len(args) == 0:
            help_text = 'Hello, I am wurstminebot. I sync messages between IRC and Minecraft, and respond to various commands.\nExecute “help commands” for a list of commands, or “help <command>” (replace <command> with a command name) for help on a specific command.\nTo execute a command, send it to me in private chat (here) or address me in ' + config('irc').get('main_channel', '#wurstmineberg') + ' (like this: “wurstminebot: <command>...”). You can also execute commands in a channel or in Minecraft like this: “!<command>...”.'
        elif args[0] == 'commands':
            help_text = 'Available commands: ' + ', '.join(sorted(list(commands.keys()) + ['help']))
        elif args[0] == 'help':
            help_text = 'help: get help on a command\nUsage: help [commands | <command>]'
        elif args[0].lower() in commands:
            help_cmd = args[0].lower()
            help_text = help_cmd + ': ' + commands[help_cmd]['description'] + (' (requires bot op)' if commands[help_cmd].get('botop_only', False) else '') + '\nUsage: ' + help_cmd + ('' if commands[help_cmd].get('usage') is None else (' ' + commands[help_cmd]['usage']))
        else:
            help_text = '“' + str(args[0]) + '” is not a command. Type “help commands” for a list of commands.'
        if context == 'irc':
            for line in help_text.splitlines():
                bot.say(sender, line)
        else:
            reply(sender, help_text)
    elif cmd in commands:
        isbotop = nicksub.sub(sender, context, 'irc', strict=False) in [None] + config('irc')['op_nicks']
        if isbotop or not cmd.get('botop_only', False):
            commands[cmd]['function'](args=args, botop=isbotop)
        else:
            warning(errors.botop)
    elif not chan:
        warning(errors.unknown)

def endMOTD(sender, headers, message):
    for chan in config('irc')['channels']:
        bot.joinchan(chan)
    bot.say(config('irc')['main_channel'], "aaand I'm back.")
    minecraft.tellraw({'text': "aaand I'm back.", 'color': 'gold'})
    _debug_print("aaand I'm back.")
    update_all()
    threading.Timer(20, minecraft.update_status).start()
    InputLoop().start()

bot.bind('376', endMOTD)

def action(sender, headers, message):
    if sender == config('irc').get('nick', 'wurstminebot'):
        return
    if headers[0] == config('irc')['main_channel']:
        minecraft.tellraw({'text': '', 'extra': [{'text': '* ' + nicksub.sub(sender, 'irc', 'minecraft'), 'color': 'aqua', 'hoverEvent': {'action': 'show_text', 'value': sender + ' in ' + headers[0]}, 'clickEvent': {'action': 'suggest_command', 'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '}}, {'text': ' '}, {'text': nicksub.textsub(message, 'irc', 'minecraft'), 'color': 'aqua'}]})

bot.bind('ACTION', action)

def privmsg(sender, headers, message):
    def botsay(msg):
        for line in msg.splitlines():
            bot.say(config('irc')['main_channel'], line)
    
    _debug_print('[irc] <' + sender + '> ' + message)
    if sender == config('irc').get('nick', 'wurstminebot'):
        return
    if headers[0].startswith('#'):
        if message.startswith(config('irc').get('nick', 'wurstminebot') + ': ') or message.startswith(config('irc')['nick'] + ', '):
            cmd = message[len(config('irc').get('nick', 'wurstminebot')) + 2:].split(' ')
            if len(cmd):
                command(sender, headers[0], cmd[0], cmd[1:], context='irc')
        elif message.startswith('!'):
            cmd = message[1:].split(' ')
            if len(cmd):
                command(sender, headers[0], cmd[0], cmd[1:], context='irc')
        elif headers[0] == config('irc')['main_channel']:
            if re.match('https?://mojang.atlassian.net/browse/[A-Z]+-[0-9]+', message):
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
                command(None, None, 'pastemojira', [message, 'nolink'], reply_format='tellraw')
                command(sender, headers[0], 'pastemojira', [message, 'nolink'], reply=botsay)
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
                command(None, None, 'pastetweet', [message, 'nolink'], reply_format='tellraw')
                command(sender, headers[0], 'pastetweet', [message, 'nolink'], reply=botsay)
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
            command(sender, None, cmd[0], cmd[1:], context='irc')

bot.bind('PRIVMSG', privmsg)

def run():
    bot.debugging(config('debug'))
    TimeLoop().start()
    bot.run()

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
