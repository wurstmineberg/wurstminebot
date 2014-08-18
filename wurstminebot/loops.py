import sys

from wurstminebot import commands
from wurstminebot import core
from datetime import datetime
from wurstminebot import deaths
import json
import lazyjson
import minecraft
from wurstminebot import nicksub
import os.path
import random
import re
import socket
import threading
import time
from datetime import timedelta
from datetime import timezone
import traceback

class InputLoop(threading.Thread):
    def __init__(self):
        super().__init__(name='wurstminebot InputLoop')
        self.stopped = False
    
    def log_tail(self, timeout=0.5, error_timeout=10):
        logpath = os.path.join(core.config('paths')['minecraft_server'], 'logs', 'latest.log')
        try:
            with open(logpath) as log:
                lines_read = len(list(log.read().split('\n'))) - 1 # don't yield lines that already existed
        except (IOError, OSError):
            lines_read = 0
        while not self.stopped:
            time.sleep(timeout)
            try:
                with open(logpath) as log:
                    lines = log.read().split('\n')
                    if len(lines) <= lines_read: # log has restarted
                        lines_read = 0
                    for line in lines[lines_read:-1]:
                        lines_read += 1
                        yield line
            except (IOError, OSError):
                core.debug_print('Log does not exist, retrying in {} seconds'.format(error_timeout))
                time.sleep(error_timeout)
    
    @staticmethod
    def process_log_line(log_line):
        try:
            # server log output processing
            core.debug_print('[logpipe] ' + log_line)
            match_prefix = '(' + minecraft.regexes.timestamp + '|' + minecraft.regexes.full_timestamp + ') \\[Server thread/INFO\\]: '
            matches = {
                'achievement': '(' + minecraft.regexes.player + ') has just earned the achievement \\[(.+)\\]$',
                'action': '\\* (' + minecraft.regexes.player + ') (.*)',
                'chat_message': '<(' + minecraft.regexes.player + ')> (.*)',
                'join_leave': '(' + minecraft.regexes.player + ') (left|joined) the game'
            }
            for match_type, match_string in matches.items():
                match = re.match(match_prefix + match_string, log_line)
                if not match:
                    continue
                if match_type == 'achievement':
                    player, achievement = match.group(2, 3)
                    person = nicksub.person_or_dummy(player, context='minecraft')
                    if core.state['achievement_tweets']:
                        twitter_nick = person.nick('twitter', twitter_at_prefix=True)
                        status = '[Achievement Get] ' + twitter_nick + ' got ' + achievement
                        try:
                            twid = core.tweet(status)
                        except core.TwitterError as e:
                            twid = 'error ' + str(e.status_code) + ': ' + str(e)
                        except AttributeError:
                            twid = 'Twitter is not configured'
                        else:
                            twid = 'https://twitter.com/wurstmineberg/status/' + str(twid)
                    else:
                        twid = 'achievement tweets are disabled'
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config:
                        core.state['bot'].say(irc_config['main_channel'], 'Achievement Get: ' + person.irc_nick() + ' got ' + achievement + ' [' + twid + ']')
                elif match_type == 'action':
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config:
                        player, message = match.group(2, 3)
                        sender_person = nicksub.person_or_dummy(player, context='minecraft')
                        sender = sender_person.irc_nick()
                        subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                        core.state['bot'].log(irc_config['main_channel'], 'ACTION', sender, [irc_config['main_channel']], subbed_message)
                        core.state['bot'].say(irc_config['main_channel'], '* ' + sender + ' ' + subbed_message)
                elif match_type == 'chat_message':
                    player, message = match.group(2, 3)
                    sender_person = nicksub.person_or_dummy(player, context='minecraft')
                    if re.match('![A-Za-z]', message): # command
                        cmd = message[1:].split(' ')
                        if commands.run(cmd, sender=sender_person, context='minecraft', return_exits=True):
                            core.debug_print('Exit in ' + str(cmd[0]) + ' command from ' + str(player) + ' to in-game chat')
                            core.cleanup()
                            sys.exit()
                    elif re.match('https?://bugs\\.mojang\\.com/browse/[A-Z]+-[0-9]+', message): # Mojira ticket
                        irc_config = core.config('irc')
                        if 'main_channel' in irc_config:
                            sender = sender_person.irc_nick()
                            subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                            core.state['bot'].log(irc_config['main_channel'], 'PRIVMSG', sender, [irc_config['main_channel']], subbed_message)
                            core.state['bot'].say(irc_config['main_channel'], '<' + sender + '> ' + subbed_message)
                        try:
                            match = re.match('https?://(mojang\\.atlassian\\.net|bugs\\.mojang\\.com)/browse/([A-Z]+)-([0-9]+)', message)
                            project = match.group(2)
                            issue_id = int(match.group(3))
                            if 'main_channel' in irc_config:
                                core.state['bot'].say(irc_config['main_channel'], core.paste_mojira(project, issue_id))
                            minecraft.tellraw(core.paste_mojira(project, issue_id, tellraw=True))
                        except SystemExit:
                            core.debug_print('Exit while pasting mojira ticket')
                            core.cleanup()
                            raise
                        except Exception as e:
                            minecraft.tellraw({
                                'text': 'Error pasting mojira ticket: ' + str(e),
                                'color': 'red'
                            })
                            core.debug_print('Exception while pasting mojira ticket:')
                            if core.config('debug', False) or core.state.get('is_daemon', False):
                                traceback.print_exc(file=sys.stdout)
                    elif re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/[0-9]+$', message): # tweet
                        irc_config = core.config('irc')
                        if 'main_channel' in irc_config:
                            sender = sender_person.irc_nick()
                            subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                            core.state['bot'].log(irc_config['main_channel'], 'PRIVMSG', sender, [irc_config['main_channel']], subbed_message)
                            core.state['bot'].say(irc_config['main_channel'], '<' + sender + '> ' + subbed_message)
                        try:
                            twid = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)$', message).group(1)
                            minecraft.tellraw(core.paste_tweet(twid, link=False, tellraw=True))
                            if 'main_channel' in irc_config:
                                pasted_tweet_irc = core.paste_tweet(twid, link=False, tellraw=False)
                                for line in pasted_tweet_irc.splitlines():
                                    core.state['bot'].say(irc_config['main_channel'], line)
                        except SystemExit:
                            core.debug_print('Exit while pasting tweet')
                            core.cleanup()
                            raise
                        except core.TwitterError as e:
                            minecraft.tellraw({
                                'text': 'Error ' + str(e.status_code) + ' while pasting tweet: ' + str(e),
                                'color': 'red'
                            })
                            core.debug_print('TwitterError ' + str(e.status_code) + ' while pasting tweet:')
                            core.debug_print(json.dumps(e.errors, sort_keys=True, indent=4, separators=(',', ': ')))
                        except AttributeError:
                            core.debug_print('Tried to paste a tweet from in-game chat, but Twitter is not configured')
                        except Exception as e:
                            minecraft.tellraw({
                                'text': 'Error while pasting tweet: ' + str(e),
                                'color': 'red'
                            })
                            core.debug_print('Exception while pasting tweet:')
                            if core.config('debug', False) or core.state.get('is_daemon', False):
                                traceback.print_exc(file=sys.stdout)
                    else: # chat message
                        irc_config = core.config('irc')
                        if 'main_channel' in irc_config:
                            sender = sender_person.irc_nick()
                            subbed_message = nicksub.textsub(message, 'minecraft', 'irc')
                            core.state['bot'].log(irc_config['main_channel'], 'PRIVMSG', sender, [irc_config['main_channel']], subbed_message)
                            core.state['bot'].say(irc_config['main_channel'], '<' + sender + '> ' + subbed_message)
                elif match_type == 'join_leave':
                    player = match.group(2)
                    try:
                        person = nicksub.Person(player, context='minecraft')
                    except nicksub.PersonNotFoundError:
                        person = None
                    joined = bool(match.group(3) == 'joined')
                    if person is None:
                        unknown_player = True
                    else:
                        unknown_player = False
                        with open(os.path.join(core.config('paths')['logs'], 'logins.log')) as loginslog:
                            for line in loginslog:
                                if person.id in line:
                                    new_player = False
                                    break
                            else:
                                new_player = True
                    with open(os.path.join(core.config('paths')['logs'], 'logins.log'), 'a') as loginslog:
                        print(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), ('?' if person is None else person.id), ('joined' if joined else 'left'), player, file=loginslog) # logs in UTC
                    if joined:
                        if unknown_player:
                            welcome_message = (0, 3) # The “you're not in the database” message
                        elif new_player:
                            welcome_message = (0, 2) # The “welcome to the server” message
                        else:
                            welcome_messages = {}
                            if person.description is None:
                                welcome_messages[0, 1] = 1.0 # The “you still don't have a description” welcome message
                            for index, adv_welcome_msg in enumerate(core.config('commentLines').get('serverJoin', [])):
                                if 'text' not in adv_welcome_msg:
                                    continue
                                welcome_messages[2, index] = adv_welcome_msg.get('weight', 1.0) * adv_welcome_msg.get('personWeights', {}).get(person.id, adv_welcome_msg.get('personWeights', {}).get('@default', 1.0))
                            random_index = random.uniform(0.0, sum(welcome_messages.values()))
                            index = 0.0
                            for welcome_message, weight in welcome_messages.items():
                                if random_index - index < weight:
                                    break
                                else:
                                    index += weight
                            else:
                                welcome_message = (0, 0) # The “um… sup?” welcome message
                        if welcome_message == (0, 0):
                            minecraft.tellraw({
                                'text': 'Hello ' + player + '. Um... sup?',
                                'color': 'gray'
                            }, player)
                            welcome_message_stub = 'Um... sup?'
                        elif welcome_message == (0, 1):
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
                                        'value': '!People ' + person.id + ' description '
                                    },
                                    'color': 'gray'
                                },
                                {
                                    'text': '!',
                                    'color': 'gray'
                                }
                            ], player)
                            welcome_message_stub = "You still don't have a description […]"
                        elif welcome_message == (0, 2):
                            minecraft.tellraw({
                                'text': 'Hello ' + player + '. Welcome to the server!',
                                'color': 'gray'
                            }, player)
                            welcome_message_stub = 'Welcome to the server!'
                        elif welcome_message == (0, 3):
                            minecraft.tellraw({
                                'color': 'gray',
                                'text': 'Hello ' + player + '. Do I know you?'
                            }, player)
                            welcome_message_stub = 'Do I know you?'
                        elif welcome_message[0] == 2: # regular comment lines (formerly known as advanced comment lines)
                            message_dict = core.config('commentLines')['serverJoin'][welcome_message[1]]
                            message_list = message_dict['text']
                            if isinstance(message_list, str):
                                message_list = [{'text': message_list, 'color': message_dict.get('commentColor', message_dict.get('color', 'gray'))}]
                            elif isinstance(message_list, dict) or isinstance(message_list, lazyjson.Dict):
                                message_list = [message_list]
                            prefix_list = []
                            if 'prefix' in message_dict:
                                prefix_list = message_dict['prefix']
                                if isinstance(prefix_list, str):
                                    prefix_list = [{'text': prefix_list, 'color': message_dict.get('prefixColor', message_dict.get('color', 'gray'))}]
                                elif isinstance(prefix_list, dict) or isinstance(prefix_list, lazyjson.Dict):
                                    prefix_list = [prefix_list]
                            minecraft.tellraw(prefix_list + ([
                                {
                                    'text': 'Hello ' + player + '. ',
                                    'color': message_dict.get('helloColor', message_dict.get('color', 'gray'))
                                }
                            ] if message_dict.get('helloPrefix', True) else []) + message_list, player)
                            if len(message_list) and 'text' in message_list[0]:
                                welcome_message_stub = (message_list[0]['text'][:80] if len(message_list[0]['text']) > 80 else message_list[0]['text']) + (' […]' if len(message_list[0]['text']) > 80 or len(message_list) > 1 else '')
                            else:
                                welcome_message_stub = '[…]'
                        else:
                            minecraft.tellraw({
                                'text': 'Hello ' + player + '. How did you do that?',
                                'color': 'gray'
                            }, player)
                            welcome_message_stub = 'How did you do that?'
                        core.debug_print('[join] ' + ('@unknown' if person is None else person.id) + ' ' + repr(welcome_message) + ' ' + welcome_message_stub)
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config and irc_config.get('playerList', 'announce') == 'announce':
                        core.state['bot'].say(irc_config['main_channel'], (player if person is None else person.irc_nick()) + ' ' + ('joined' if joined else 'left') + ' the game')
                    core.update_all()
                break
            else:
                try:
                    death = deaths.Death(log_line, time=datetime.now(timezone.utc))
                except ValueError:
                    return # no death, continue parsing here or ignore this line
                with open(os.path.join(core.config('paths')['logs'], 'deaths.log'), 'a') as deathslog:
                    death.log(deathslog)
                if core.state['death_tweets']:
                    if death.message() == core.state['last_death']:
                        comment = 'Again.' # This prevents botspam if the same player dies lots of times (more than twice) for the same reason.
                    elif (death.id == 'slainPlayerUsing' and death.groups[1] == 'Sword of Justice') or (death.id == 'shotPlayerUsing' and death.groups[1] == 'Bow of Justice'): # Death Games success
                        comment = 'And loses a diamond http://wiki.wurstmineberg.de/Death_Games'
                        try:
                            attacker = nicksub.Person(death.groups[0], context='minecraft')
                        except nicksub.PersonNotFoundError:
                            pass # don't automatically log
                        else:
                            core.death_games_log(attacker, death.person, success=True)
                    else:
                        death_comments = {}
                        for index, adv_death_comment in enumerate(core.config('commentLines').get('death', [])):
                            if 'text' not in adv_death_comment:
                                continue
                            try:
                                death_comments[2, index] = adv_death_comment.get('weight', 1.0) * adv_death_comment.get('personWeights', {}).get(death.person.id, adv_death_comment.get('personWeights', {}).get('@default', 1.0)) * adv_death_comment.get('typeWeights', {}).get(death.id, adv_death_comment.get('typeWeights', {}).get('@default', 1.0))
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
                        elif comment_index[0] == 2:
                            comment = core.config('commentLines')['death'][comment_index[1]]['text']
                        else:
                            comment = "I don't even."
                    core.state['last_death'] = death.message()
                    status = death.tweet(comment=comment)
                    try:
                        twid = core.tweet(status)
                    except core.TwitterError as e:
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
                    except AttributeError:
                        twid = 'Twitter is not configured'
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
                                'text': " been reported because I don't even Twitter.",
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
                core.debug_print('[death] ' + death.irc_message(tweet_info=twid, respect_highlight_option=False))
                irc_config = core.config('irc')
                if 'main_channel' in irc_config and core.state.get('bot'):
                    core.state['bot'].say(irc_config['main_channel'], death.irc_message(tweet_info=twid))
        except SystemExit:
            core.debug_print('Exit in log input loop')
            core.cleanup()
            raise
        except:
            core.debug_print('Exception in log input loop:')
            if core.state.get('is_daemon', False) or core.config('debug', False):
                traceback.print_exc(file=sys.stdout)
    
    def run(self):
        for log_line in self.log_tail():
            if self.stopped or 'bot' not in core.state or not core.state['bot'].keepGoing:
                break
            InputLoop.process_log_line(log_line)
    
    def start(self):
        self.stopped = False
        super().start()
    
    def stop(self):
        self.stopped = True

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
            tell_time(comment=True, restart=core.config('dailyRestart', True))
    
    def start(self):
        self.stopped = False
        super().start()
    
    def stop(self):
        self.stopped = True

class TwitterStream(threading.Thread):
    def __init__(self, twitter_api):
        super().__init__(name='wurstminebot TwitterStream')
        self.stopped = False
        self.twitter_api = twitter_api
    
    def run(self):
        response = self.twitter_api.request('user')
        for tweet in response:
            if self.stopped:
                break
            if not ('id' in tweet and 'entities' in tweet and 'user_mentions' in tweet['entities']):
                continue
            if not any(entity.get('screen_name') == core.config('twitter').get('screen_name') for entity in tweet.get('entities', {}).get('user_mentions', [])):
                continue
            minecraft.tellraw(core.paste_tweet(tweet['id'], link=True, tellraw=True))
            irc_config = core.config('irc')
            if core.state.get('bot') and 'main_channel' in irc_config:
                core.state['bot'].say(irc_config['main_channel'], core.paste_tweet(tweet['id'], link=True, multi_line='truncate'))
    
    def start(self):
        self.stopped = False
        super().start()
    
    def stop(self):
        self.stopped = True

def tell_time(func=None, comment=False, restart=False):
    if func is None:
        def func(msg, color='gold'):
            for line in msg.splitlines():
                try:
                    minecraft.tellraw({
                        'text': line,
                        'color': color
                    })
                except socket.error:
                    core.debug_print('telltime is disconnected from Minecraft')
                    irc_config = core.config('irc')
                    if 'main_channel' in irc_config:
                        core.state['bot'].say(irc_config['main_channel'], 'Warning! Telltime is disconnected from Minecraft.')
                    break
    
        custom_func = False
    else:
        custom_func = True
    def warning(msg):
        if custom_func:
            func(msg)
        else:
            func(msg, color='red')
    
    localnow = datetime.now()
    utcnow = datetime.utcnow()
    dst = bool(time.localtime().tm_isdst)
    if dst != core.state['dst']:
        if dst:
            func('Daylight saving time is now in effect.')
        else:
            func('Daylight saving time is no longer in effect.')
    func('The time is ' + utcnow.strftime('%H:%M') + ' UTC' + ('' if abs(localnow - utcnow) < timedelta(minutes=1) else ' (' + localnow.strftime('%H:%M') + ' local time)'))
    if comment:
        if dst != core.state['dst']:
            pass
        elif localnow.hour == 0:
            func('Dark outside, better play some Minecraft.')
        elif localnow.hour == 1:
            func("You better don't stay up all night again.")
            if random.random() < 0.1:
                time.sleep(random.randrange(30))
                func('...lol, as if.')
        elif localnow.hour == 2:
            activities = ['mining', 'redstoning', 'building', 'exploring', 'idling', 'farming', 'pvp']
            random.shuffle(activities)
            func('Some late night ' + activities[0] + ' always cheers me up.')
            time.sleep(random.randrange(8, 15))
            func('...Or ' + activities[1] + '. Or ' + activities[2] + '. Whatever floats your boat.')
        elif localnow.hour == 3:
            func(random.choice([
                'Seems like you are having fun.',
                "Seems like you're having fun."
            ]))
            mob = random.choice([None, None, 'zombie', 'zombie', 'zombie pigman', 'Enderman', 'villager', 'Testificate'])
            if mob is not None:
                time.sleep(random.randrange(45, 120))
                func('I heard that ' + mob + " over there talk trash about you. Thought you'd wanna know...")
        elif localnow.hour == 4:
            func('Getting pretty late, huh?')
        elif localnow.hour == 5:
            warning('It is really getting late. You should go to sleep.')
        elif localnow.hour == 6:
            func(random.choice([
                'Are you still going, just starting or asking yourself the same thing?',
                'Are you still going, just starting, or asking yourself the same thing?',
                'So... good morning I guess?'
            ]))
        elif localnow.hour == 11 and restart:
            players = set(minecraft.online_players())
            if len(players):
                warning('The server is going to restart in 5 minutes.')
                time.sleep(240)
                players |= set(minecraft.online_players())
                warning('The server is going to restart in 60 seconds.')
                time.sleep(50)
                players |= set(minecraft.online_players())
            core.update_topic(special_status='The server is restarting…')
            irc_config = core.config('irc')
            if minecraft.restart(reply=func, log_path=os.path.join(core.config('paths')['logs'], 'logins.log'), notice=None):
                if len(players) and 'main_channel' in irc_config:
                    irc_players = nicksub.sorted_people(players, context='minecraft')
                    core.state['bot'].say(irc_config['main_channel'], ', '.join(player.irc_nick(respect_highlight_option=False) for player in irc_players) + ': The server has restarted.')
            else:
                core.debug_print('daily server restart failed')
                if 'main_channel' in irc_config:
                    core.state['bot'].say(irc_config['main_channel'], 'Please help! Something went wrong with the server restart!')
            core.update_topic(special_status=None)
            core.state['dst'] = dst
            return
    core.update_topic()
    core.state['dst'] = dst
