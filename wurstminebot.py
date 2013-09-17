#!/usr/bin/env python3
"""Minecraft IRC bot.

Usage:
  wurstminebot [options]
  wurstminebot -h | --help
  wurstminebot --version

Options:
  --config=<config>  Path to the config file [default: /opt/wurstmineberg/config/wurstminebot.json].
  -h, --help         Print this message and exit.
  --version          Print version info and exit.
"""

from TwitterAPI import TwitterAPI
from datetime import datetime
import deaths
from docopt import docopt
from ircbotframe import ircBot
import json
import minecraft
import nicksub
import random
import re
import select
import subprocess
import sys
import threading
import time
from datetime import timedelta

CONFIG_FILE = '/opt/wurstmineberg/config/wurstminebot.json'
if __name__ == '__main__':
    arguments = docopt(__doc__, version='wurstminebot 1.0.2')
    CONFIG_FILE = arguments['--config']

def config(key=None, default_value=None):
    with open(CONFIG_FILE) as config_file:
        j = json.load(config_file)
    if key is None:
        return j
    return j.get(key, default_value)

ASSETS = '/var/www/wurstmineberg.de/assets/serverstatus'
DEATHTWEET = True
DST = bool(time.localtime().tm_isdst)
LASTDEATH = ''
LOGDIR = '/opt/wurstmineberg/log'
SCRIPTS = '/opt/wurstmineberg/bin'

bot = ircBot(config('irc')['server'], config('irc')['port'], config('irc')['nick'], config('irc')['nick'], password=config('irc')['password'], ssl=config('irc')['ssl'])
botops = [None] + config('irc')['op_nicks']

twitter = TwitterAPI(config('twitter')['consumer_key'], config('twitter')['consumer_secret'], config('twitter')['access_token_key'], config('twitter')['access_token_secret'])

def _timed_input(timeout=1): #FROM http://stackoverflow.com/a/2904057
    i, o, e = select.select([sys.stdin], [], [], timeout)
    if i:
        return sys.stdin.readline().strip()

def _delayed_update():
    time.sleep(20)
    minecraft.update_status()

class errors:
    botop = 'you must be a bot op to do this'
    unknown = 'unknown command'
    
    @staticmethod
    def argc(expected, given, atleast=False):
        return ('not enough' if given < expected else 'too many') + ' arguments, expected ' + ('at least ' if atleast else '') + str(expected)

class InputLoop(threading.Thread):
    def run(self):
        global LASTDEATH
        while bot.keepGoing:
            if sys.stdin.isatty():
                prompt = 'wurstminebot> ' if sys.stdout.isatty() else ''
                try:
                    print(prompt, end='')
                    cmd = _timed_input()
                    if cmd is None:
                        continue
                    cmd = cmd.split(' ')
                except EOFError as e:
                    command(None, None, 'quit', ['EOFError'], context='console')
                    break
                except KeyboardInterrupt as e:
                    command(None, None, 'quit', ['KeyboardInterrupt'], context='console')
                    break
                if len(cmd):
                    command(None, None, cmd[0], cmd[1:], context='console')
            else:
                # server log output processing
                cmd = []
                try:
                    logLine = input()
                except EOFError as e:
                    continue
                except KeyboardInterrupt as e:
                    command(None, None, 'quit', ['KeyboardInterrupt'], context='console')
                    break
                else:
                    match = re.match(minecraft.regexes.timestamp + ' \\[INFO\\] \\* (' + minecraft.regexes.player + ') (.*)', logLine)
                    if match:
                        # action
                        player, message = match.group(1, 2)
                        bot.say(config('irc')['main_channel'], '* ' + nicksub.sub(player, 'minecraft', 'irc') + ' ' + nicksub.textsub(message, 'minecraft', 'irc'))
                    else:
                        match = re.match(minecraft.regexes.timestamp + ' \\[INFO\\] <(' + minecraft.regexes.player + ')> (.*)', logLine)
                        if match:
                            player, message = match.group(1, 2)
                            if message.startswith('!') and len(message) > 1:
                                # command
                                cmd = message[1:].split(' ')
                                command(sender=player, chan=None, cmd=cmd[0], args=cmd[1:], context='minecraft')
                            else:
                                # chat message
                                bot.say(config('irc')['main_channel'], '<' + nicksub.sub(player, 'minecraft', 'irc') + '> ' + nicksub.textsub(message, 'minecraft', 'irc'))
                        else:
                            match = re.match('(' + minecraft.regexes.timestamp + ') \\[INFO\\] (' + minecraft.regexes.player + ') (left|joined) the game', logLine)
                            if match:
                                # join/leave
                                timestamp, player = match.group(1, 2)
                                joined = bool(match.group(3) == 'joined')
                                with open(LOGDIR + '/logins.log', 'a') as loginslog:
                                    print(timestamp + ' ' + player + ' ' + ('joined' if joined else 'left') + ' the game', file=loginslog)
                                if joined:
                                    welcomeMessages = ['I warmed your pickaxe for you.', "Please don't make a mess again.", "Nice to see you haven't given up. Yet.", 'Check out the new biomes!']
                                    if player in ['BenemitC', 'Farthen08', 'naturalismus']:
                                        welcomeMessages += ['Big Brother is watching you.']
                                    minecraft.tellraw({'text': 'Hello ' + player + '. ' + random.choice(welcomeMessages), 'color': 'gray'}, player)
                                bot.say(config('irc')['main_channel'], nicksub.sub(player, 'minecraft', 'irc') + ' ' + ('joined' if joined else 'left') + ' the game')
                                minecraft.update_status()
                                threading.Thread(target=_delayed_update).start()
                            else:
                                for deathid, death in enumerate(deaths.regexes):
                                    match = re.match('(' + minecraft.regexes.timestamp + ') \\[INFO\\] (' + minecraft.regexes.player + ') ' + death + '$', logLine)
                                    if not match:
                                        continue
                                    # death
                                    timestamp, player = match.group(1, 2)
                                    groups = match.groups()[2:]
                                    message = deaths.partial_message(deathid, groups)
                                    with open(LOGDIR + '/deaths.log', 'a') as deathslog:
                                        print(timestamp + ' ' + player + ' ' + message, file=deathslog)
                                    if DEATHTWEET:
                                        if message == LASTDEATH:
                                            comment = ' … Again.' # This prevents botspam if the same player dies lots of times (more than twice) for the same reason.
                                        else:
                                            comment = ' … ' + random.choice(["It's funny because it's true.", 'INSERT CHEECKY RESPONSE.', 'Like a bauhu5.', 'Like a champ.', "I've never been so proud."])
                                        LASTDEATH = message
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
                                        twid = 'deathtweets are diabled'
                                    bot.say(config('irc')['main_channel'], nicksub.sub(player, 'minecraft', 'irc') + ' ' + nicksub.textsub(message, 'minecraft', 'irc', strict=True) + ' [' + twid + ']')

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

def command(sender, chan, cmd, args, context='irc', reply=None):
    global DEATHTWEET
    if reply is None:
        def reply(msg):
            if context == 'irc':
                if not sender:
                    print(msg)
                elif chan:
                    bot.say(chan, sender + ': ' + msg)
                else:
                    bot.say(sender, msg)
            elif context == 'minecraft':
                minecraft.tellraw({'text': msg, 'color': 'gold'}, sender)
            elif context == 'console':
                print(msg)
    
    isbotop = nicksub.sub(sender, context, 'irc', strict=False) in botops
    if cmd == 'command':
        # perform Minecraft server command
        if isbotop:
            if args[0]:
                cmdResult = minecraft.command(args[0], args[1:])
                for line in cmdResult.splitlines():
                    reply(line)
            else:
                reply(errors.argc(1, len(args), atleast=True))
        else:
            reply(errors.botop)
    elif cmd == 'deathtweet':
        # toggle death message tweeting
        if not len(args):
            reply('Deathtweeting is currently ' + ('enabled' if DEATHTWEET else 'disabled'))
        elif args[0] == 'on':
            DEATHTWEET = True
            reply('Deathtweeting is now enabled')
        elif args[0] == 'off':
            DEATHTWEET = False
            reply('Deathtweeting is now disabled')
        else:
            reply('first argument needs to be “on” or “off”')
    elif cmd == 'exitreader':
        # logpipereader quit function, now deprecated
        reply('This is not logpipereader, this is wurstminebot. Quit using the quit command.')
    elif cmd == 'fixstatus':
        # update the server status on the website
        minecraft.update_status()
        threading.Thread(target=_delayed_update).start()
    elif cmd == 'lastseen':
        # when was the player last seen logging in or out on Minecraft
        if len(args):
            player = args[0]
            mcplayer = nicksub.sub(player, context, 'minecraft', strict=False)
            if mcplayer in minecraft.online_players():
                reply(player + ' is currently on the server.')
            else:
                lastseen = minecraft.last_seen(mcplayer)
                if lastseen is None:
                    reply('I have not seen ' + player + ' on the server yet.')
                else:
                    if lastseen.date() == datetime.utcnow().date():
                        datestr = 'today at ' + lastseen.strftime('%H:%M UTC')
                    elif lastseen.date() == datetime.utcnow().date() - timedelta(days=1):
                        datestr = 'yesterday at ' + lastseen.strftime('%H:%M UTC')
                    else:
                        datestr = lastseen.strftime('on %Y-%m-%d at %H:%M UTC')
                    reply(player + ' was last seen ' + datestr + '.')
        else:
            reply(errors.argc(1, len(args)))
    elif cmd == 'pastetweet':
        # print the contents of a tweet
        link = True
        if len(args) == 2 and args[1] == 'nolink':
            link = False
            args = [args[0]]
        if len(args) == 1:
            match = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)', args[0])
            twid = match.group(1) if match else args[0]
            request = twitter.request('statuses/show', {'id': twid})
            if 'id' in request.json():
                if 'retweeted_status' in request.json():
                    retweeted_request = twitter.request('statuses/show', {'id': request.json()['retweeted_status']['id']})
                    tweet_author = '<@' + request.json()['user']['screen_name'] + ' RT @' + retweeted_request.json()['user']['screen_name'] + '> '
                    text = retweeted_request.json()['text']
                else:
                    tweet_author = '<@' + request.json()['user']['screen_name'] + '> '
                    text = request.json()['text']
                reply(tweet_author + text + ((' [https://twitter.com/' + request.json()['user']['screen_name'] + '/status/' + request.json()['id_str'] + ']') if link else ''))
            else:
                reply('Error ' + str(request.status_code))
        else:
            reply(errors.argc(1, len(args)))
    elif cmd == 'ping':
        # say pong
        reply('pong')
    elif cmd == 'quit':
        # quit the IRC bot
        if isbotop:
            quitMsg = ' '.join(args) if len(args) else None
            if context != 'minecraft':
                minecraft.tellraw({'text': ('Restarting the bot: ' + quitMsg) if quitMsg else 'Restarting the bot...', 'color': 'red'})
            if (context != 'irc') or (chan is None):
                bot.say(config('irc')['main_channel'], ('brb, ' + quitMsg) if quitMsg else random.choice(['Please wait while I reinstall the universe.', 'brb', 'Please hang tight, I seem to have exploded.']))
            bot.disconnect(quitMsg if quitMsg else 'brb')
            bot.stop()
            sys.exit()
        else:
            reply(errors.botop)
    elif cmd == 'raw':
        # send raw message to IRC
        if isbotop:
            if len(args):
                bot.send(' '.join(args))
            else:
                reply(errors.argc(1, len(args), atleast=True))
        else:
            reply(errors.botop)
    elif cmd == 'restart':
        # restart the Minecraft server
        if isbotop:
            minecraft.stop()
            minecraft.start()
        else:
            reply(errors.botop)
    elif cmd == 'status':
        # print some server status
        if minecraft.status():
            if context != 'minecraft':
                players = minecraft.online_players()
                if len(players):
                    reply('Online players: ' + ', '.join(map(lambda nick: nicksub.sub(nick, 'minecraft', context), players)))
                else:
                    reply('The server is currently empty.')
            reply('Minecraft version ' + minecraft.version())
        else:
            reply('The server is currently offline.')
    elif cmd == 'stop':
        # stop the Minecraft server
        if isbotop:
            minecraft.stop()
        else:
            reply(errors.botop)
    elif cmd == 'time':
        # reply with the current time
        telltime(func=reply)
    elif cmd == 'tweet':
        # tweet message
        if isbotop:
            if len(args):
                tweet = nicksub.textsub(' '.join(args), context, 'twitter')
                if len(tweet) > 140:
                    reply('too long')
                else:
                    r = twitter.request('statuses/update', {'status': tweet})
                    if 'id' in r.json():
                        reply('https://twitter.com/wurstmineberg/status/' + str(r.json()['id']))
                    else:
                        reply('Error ' + str(r.status_code))
            else:
                reply(errors.argc(1, len(args), atleast=True))
        else:
            reply(errors.botop)
    elif cmd == 'update':
        # update Minecraft
        if isbotop:
            if len(args):
                if args[0] == 'snapshot':
                    if len(args) == 2:
                        minecraft.update(args[1], snapshot=True)
                    else:
                        reply(errors.argc(2, len(args)))
                elif len(args) == 1:
                    minecraft.update(args[0], snapshot=False)
                else:
                    reply(errors.argc(1, len(args)))
            else:
                reply(errors.argc(1, len(args), atleast=True))
        else:
            reply(errors.botop)
    elif not chan:
        reply(errors.unknown)

def endMOTD(sender, headers, message):
    for chan in config('irc')['channels']:
        print('joining ' + chan) #DEBUG
        bot.joinchan(chan)
    bot.say(config('irc')['main_channel'], "aaand I'm back.")
    minecraft.tellraw({'text': "aaand I'm back.", 'color': 'gold'})
    print("aaand I'm back.") #DEBUG
    InputLoop().start()

bot.bind('376', endMOTD)

def action(sender, headers, message):
    if sender == config('irc')['nick']:
        return
    if headers[0] == config('irc')['main_channel']:
        minecraft.tellraw({'text': '', 'extra': [{'text': '* ' + nicksub.sub(sender, 'irc', 'minecraft'), 'color': 'aqua', 'hoverEvent': {'action': 'show_text', 'value': sender + ' in ' + headers[0]}, 'clickEvent': {'action': 'suggest_command', 'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '}}, {'text': ' '}, {'text': nicksub.textsub(message, 'irc', 'minecraft'), 'color': 'aqua'}]})

bot.bind('ACTION', action)

def privmsg(sender, headers, message):
    def tweetpaste(msg):
        for line in msg.splitlines():
            bot.say(config('irc')['main_channel'], line)
            minecraft.tellraw({'text': line, 'color': 'gold'})
    
    if sender == config('irc')['nick']:
        return
    if headers[0].startswith('#'):
        if message.startswith(config('irc')['nick'] + ': ') or message.startswith(config('irc')['nick'] + ', '):
            cmd = message[len(config('irc')['nick']) + 2:].split(' ')
            if len(cmd):
                command(sender, headers[0], cmd[0], cmd[1:], context='irc')
        elif message.startswith('!'):
            cmd = message[1:].split(' ')
            if len(cmd):
                command(sender, headers[0], cmd[0], cmd[1:], context='irc')
        elif headers[0] == config('irc')['main_channel']:
            if re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/[0-9]+$', message):
                minecraft.tellraw({'text': '', 'extra': [{'text': '<' + nicksub.sub(sender, 'irc', 'minecraft') + '>', 'color': 'aqua', 'hoverEvent': {'action': 'show_text', 'value': sender + ' in ' + headers[0]}, 'clickEvent': {'action': 'suggest_command', 'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '}}, {'text': ' '}, {'text': message, 'color': 'aqua', 'clickEvent': {'action': 'open_url', 'value': message}}]})
                command(sender, headers[0], 'pastetweet', [message, 'nolink'], reply=tweetpaste)
            else:
                minecraft.tellraw({'text': '', 'extra': [{'text': '<' + nicksub.sub(sender, 'irc', 'minecraft') + '>', 'color': 'aqua', 'hoverEvent': {'action': 'show_text', 'value': sender + ' in ' + headers[0]}, 'clickEvent': {'action': 'suggest_command', 'value': nicksub.sub(sender, 'irc', 'minecraft') + ': '}}, {'text': ' '}, {'text': nicksub.textsub(message, 'irc', 'minecraft'), 'color': 'aqua'}]})
    else:
        cmd = message.split(' ')
        if len(cmd):
            command(sender, None, cmd[0], cmd[1:], context='irc')

bot.bind('PRIVMSG', privmsg)

if __name__ == '__main__':
    bot.start()
    TimeLoop().start()
