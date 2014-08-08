import sys

from wurstminebot import core
from datetime import datetime
import inspect
import json
import minecraft
from wurstminebot import nicksub
import os.path
import random
import re
import requests
import subprocess
import threading
from datetime import timedelta
from datetime import timezone
import traceback
import urllib.parse

class BaseCommand(threading.Thread):
    """base class for other commands, not a real command"""
    
    usage = None
    
    def __init__(self, args, sender, context, channel=None, addressing=None):
        super().__init__(name='wurstminebot command ' + self.__class__.__name__)
        self.addressing = addressing
        self.arguments = [str(arg) for arg in args]
        if isinstance(sender, str):
            self.sender = nicksub.Dummy(sender, context=context)
        else:
            self.sender = sender
        self.context = context
        self.channel = channel
        self.name = self.__class__.__name__

    def parse_args(self):
        """Returns a bool representing whether or not the arguments passed are well-formed."""
        return True

    def permission_level(self):
        return 0

    def reply(self, irc_reply, tellraw_reply=None):
        if self.context == 'minecraft':
            if tellraw_reply is None:
                tellraw_reply = {
                    'text': irc_reply,
                    'color': 'gold'
                }
            if isinstance(tellraw_reply, str):
                tellraw_reply = {
                    'text': tellraw_reply,
                    'color': 'gold'
                }
            if self.sender.minecraft is None:
                minecraft.tellraw([{
                    'text': self.sender.display_name() + ': ',
                    'color': 'gold'
                }] + ([tellraw_reply] if isinstance(tellraw_reply, dict) else tellraw_reply), (self.sender.minecraft if self.addressing is None else self.addressing.minecraft))
            else:
                minecraft.tellraw(tellraw_reply, self.sender.minecraft)
        elif self.channel is None:
            if self.addressing is None:
                for line in irc_reply.splitlines():
                    core.state['bot'].say(self.sender.irc_nick(respect_highlight_option=False), line)
            else:
                for line in ('(from ' + self.sender.irc_nick(respect_highlight_option=False) + ') ' + irc_reply).splitlines():
                    core.state['bot'].say(self.addressing.irc_nick(respect_highlight_option=False), line)
        else:
            for line in irc_reply.splitlines():
                core.state['bot'].say(self.channel, (self.sender.irc_nick(respect_highlight_option=False) if self.addressing is None else self.addressing.irc_nick(respect_highlight_option=False)) + ': ' + line)

    def run(self):
        raise NotImplementedError('Implement run method of Command subclass')

    def warning(self, warning_reply):
        self.reply(warning_reply, {
            'text': warning_reply,
            'color': 'red'
        })

class AliasCommand(BaseCommand):
    """base class for alias commands defined in config, not the Alias command itself"""
    
    def __init__(self, name, alias_dict, args, sender, context, channel=None, addressing=None):
        super().__init__(args, sender, context, channel=channel, addressing=addressing)
        self.alias_dict = alias_dict
        self.name = name
    
    def parse_args(self):
        alias_type = self.alias_dict.get('type', 'say')
        if alias_type == 'command':
            for command_class in classes:
                if command_class.__name__.lower() == self.alias_dict['command_name'].lower():
                    aliased_command = command_class(args=self.arguments, sender=self.sender, context=self.context, channel=self.channel, addressing=self.addressing)
                    self.usage = aliased_command.usage
                    return aliased_command.parse_args()
            else:
                raise ValueError('No such command')
        elif alias_type == 'disable':
            return True
        elif alias_type == 'reply':
            if len(self.arguments) > 0:
                return False
            return True
        elif alias_type == 'say':
            if len(self.arguments) > 0:
                return False
            return True
        else:
            raise ValueError('No such alias type')
    
    def run(self):
        alias_type = self.alias_dict.get('type', 'say')
        if alias_type == 'command':
            for command_class in classes:
                if command_class.__name__.lower() == self.alias_dict['command_name'].lower():
                    return command_class(args=self.arguments, sender=self.sender, context=self.context, channel=self.channel, addressing=self.addressing).run()
            else:
                raise ValueError('No such command') 
        elif alias_type == 'disable':
            self.warning('This command is disabled.')
        elif alias_type == 'reply':
            self.reply(self.alias_dict['text'], self.alias_dict.get('tellraw_text'))
        elif alias_type == 'say':
            if self.context == 'irc' and self.channel == core.config('irc').get('main_channel'):
                tellraw_text = self.alias_dict['text']
                if 'tellraw_text' in self.alias_dict:
                    tellraw_text = self.alias_dict['tellraw_text']
                if isinstance(tellraw_text, str):
                    tellraw_text = [
                        {
                            'color': 'aqua',
                            'text': tellraw_text
                        }
                    ]
                if isinstance(tellraw_text, dict):
                    tellraw_text = [tellraw_text]
                minecraft.tellraw([
                    {
                        'clickEvent': {
                            'action': 'suggest_command',
                            'value': self.sender.nick('minecraft') + ': '
                        },
                        'color': 'aqua',
                        'text': '<' + self.sender.nick('minecraft') + '>'
                    }
                ] + ([] if self.addressing is None else [
                    {
                        'text': ' '
                    },
                    {
                        'clickEvent': {
                            'action': 'suggest_command',
                            'value': self.addressing.nick('minecraft') + ': '
                        },
                        'color': 'gold',
                        'text': self.addressing.nick('minecraft')
                    },
                    {
                        'color': 'gold',
                        'text': ':'
                    }
                ]) + [
                    {
                        'text': ' '
                    }
                ] + tellraw_text)
            elif self.context == 'minecraft':
                tellraw_text = self.alias_dict['text']
                if 'tellraw_text' in self.alias_dict:
                    tellraw_text = self.alias_dict['tellraw_text']
                if isinstance(tellraw_text, str):
                    tellraw_text = [
                        {
                            'color': 'gold',
                            'text': tellraw_text
                        }
                    ]
                if isinstance(tellraw_text, dict):
                    tellraw_text = [tellraw_text]
                minecraft.tellraw([
                    {
                        'color': 'gold',
                        'text': '<'
                    },
                    {
                        'clickEvent': {
                            'action': 'suggest_command',
                            'value': self.sender.nick('minecraft') + ': '
                        },
                        'color': 'gold',
                        'text': self.sender.nick('minecraft')
                    },
                    {
                        'color': 'gold',
                        'text': '> '
                    }
                ] + ([] if self.addressing is None else [
                    {
                        'clickEvent': {
                            'action': 'suggest_command',
                            'value': self.addressing.nick('minecraft') + ': '
                        },
                        'color': 'gold',
                        'text': self.addressing.nick('minecraft')
                    },
                    {
                        'color': 'gold',
                        'text': ':'
                    }
                ]) + tellraw_text)
            if self.context == 'irc' and self.channel is not None:
                core.state['bot'].say(self.channel, '<' + self.sender.irc_nick(respect_highlight_option=False) + '> ' + ('' if self.addressing is None else self.addressing.irc_nick(respect_highlight_option=False) + ': ') + self.alias_dict['text'])
            elif self.context == 'irc' and self.sender.irc_nick(fallback=None) is not None:
                core.state['bot'].say(self.sender.irc_nick(respect_highlight_option=False), self.alias_dict['text'])
            elif self.context == 'minecraft' and 'main_channel' in core.config('irc'):
                core.state['bot'].say(core.config('irc')['main_channel'], '<' + self.sender.irc_nick() + '> ' + ('' if self.addressing is None else self.addressing.irc_nick(respect_highlight_option=False) + ': ') + self.alias_dict['text'])
        else:
            raise ValueError('No such alias type')

class AchievementTweet(BaseCommand):
    """toggle achievement message tweeting"""
    
    usage = '[on | off [<time>]]'
    
    def parse_args(self):
        if len(self.arguments) > 2:
            return False
        elif len(self.arguments) >= 1:
            if self.arguments[0] not in ('on', 'off'):
                return False
            if len(self.arguments) == 2:
                if self.arguments[0] == 'on':
                    return False
                try:
                    core.parse_timedelta(self.arguments[1])
                except:
                    return '<time> must be a time interval, like 2h16m30s'
        return True
    
    def permission_level(self):
        if len(self.arguments) == 2 and parse_timedelta(self.arguments[1]) > timedelta(days=1):
            return 4
        if len(self.arguments) == 1 and self.arguments[0] == 'off':
            return 4
        return 3
    
    def reenable_achievement_tweets(self):
        core.state['achievement_tweets'] = True
        self.reply('Achievement tweets are back on')
    
    def run(self):
        if len(self.arguments) == 0:
            self.reply('Achievement tweeting is currently ' + ('enabled' if core.state['achievement_tweets'] else 'disabled'))
        elif self.arguments[0] == 'on':
            core.state['achievement_tweets'] = True
            self.reply('Achievement tweeting is now enabled')
        else:
            if len(self.arguments) == 2:
                number = parse_timedelta(self.arguments[1])
                threading.Timer(number, self.reenable_achievement_tweets).start()
            core.state['achievement_tweets'] = False
            self.reply('Achievement tweeting is now disabled')

class Alias(BaseCommand):
    """add, edit, or remove an alias (you can use aliases like regular commands)"""
    
    usage = '<alias_name> [<text>...]'
    
    def parse_args(self):
        if len(self.arguments) == 0:
            return False
        if not re.match('[A-Za-z]+$', self.arguments[0]):
            return '<alias_name> may only consist of Latin letters'
        return True
    
    def permission_level(self):
        if len(self.arguments) == 1:
            return 4
        if self.arguments[0].lower() in core.config('aliases'):
            return 4
        if self.arguments[0].lower() in [c.__name__.lower() for c in classes]:
            return 4
        return 0
    
    def run(self):
        aliases = core.config('aliases')
        alias = self.arguments[0].lower()
        if len(self.arguments) == 1:
            if alias in aliases:
                deleted_alias = aliases[alias]
                if deleted_alias['type'] in ['reply', 'say']:
                    deleted_alias = '“' + deleted_alias['text'] + '”'
                elif deleted_alias['type'] == 'command':
                    deleted_alias = 'an alias for ' + deleted_alias['command_name']
                else:
                    deleted_alias = str(deleted_alias)
                del aliases[alias]
                core.update_config(['aliases'], aliases)
                self.reply('Alias deleted. (Was ' + deleted_alias + ')', 'Alias deleted. (Was ' + deleted_alias + ')')
            else:
                self.warning('The alias you' + (' just ' if random.randrange(0, 2) else ' ') + 'tried to delete ' + ("didn't" if random.randrange(0, 2) else 'did not') + (' even ' if random.randrange(0, 2) else ' ') + 'exist' + (' in the first place!' if random.randrange(0, 2) else '!') + (" So I guess everything's fine then?" if random.randrange(0, 2) else '')) # fun with randomized replies
        else:
            alias_existed = alias in aliases
            aliases[alias] = {
                'text': ' '.join(self.arguments[1:]),
                'type': 'say'
            }
            core.update_config(['aliases'], aliases)
            if alias_existed:
                self.reply('Alias edited.')
            else:
                self.reply('Alias added.')

class Backup(BaseCommand):
    """perform a backup of the world directory"""
    
    def parse_args(self):
        if len(self.arguments):
            return False
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        minecraft.backup(reply=self.reply, announce=True)

class Cloud(BaseCommand):
    """search for an item in the Cloud, our public item storage"""
    
    usage = '<item_id> [<damage>]'
    
    def parse_args(self):
        if len(self.arguments) not in range(1, 3):
            return False
        if len(self.arguments) >= 2:
            try:
                int(self.arguments[1])
            except ValueError:
                core.debug_print('Exception in Cloud command <damage> argument parsing:')
                if core.config('debug', False) or core.state.get('is_daemon', False):
                    traceback.print_exc(file=sys.stdout)
                return '<damage> must be a number'
        return True
    
    def run(self):
        import api
        import bottle
        try:
            if len(self.arguments) < 2:
                item = api.api_item_by_id(self.arguments[0])
            else:
                item = api.api_item_by_damage(self.arguments[0], int(self.arguments[1]))
        except bottle.HTTPError as e:
            self.reply(str(e.body))
            return
        item_name = str(item['name'] if 'name' in item else self.arguments[0])
        if 'cloud' not in item:
            self.reply("I don't know where, if at all, " + item_name + ' is in the Cloud')
            return
        if item['cloud'] is None:
            self.reply(item_name + ' is not available in the Cloud')
            return
        ordinals = {
            1: 'st',
            2: 'nd',
            3: 'rd'
        }
        x = item['cloud']['x']
        y = item['cloud']['y']
        if x == 0:
            corridor = 'central corridor'
        elif x == 1:
            corridor = 'left corridor'
        elif x == -1 and y != 1:
            corridor = 'right corridor'
        else:
            if x < 0:
                direction = 'right'
                x *= -1
            else:
                direction = 'left'
            corridor = str(x) + ordinals.get(x, 'th') + ' corridor to the ' + direction
        self.reply(str(y) + ordinals.get(y, 'th') + ' floor, ' + corridor)

class Command(BaseCommand):
    """perform a Minecraft server command"""
    
    usage = '<command> [<arguments>...]'
    
    def parse_args(self):
        if len(self.arguments) == 0:
            return False
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        for line in minecraft.command(self.arguments[0], self.arguments[1:]).splitlines():
            self.reply(line)

class DeathGames(BaseCommand):
    """record an assassination attempt in the Death Games log"""
    
    usage = '(win | fail) [<attacker>] <target>'
    
    def parse_args(self):
        if len(self.arguments) not in range(2, 4):
            return False
        if self.arguments[0].lower() not in ('win', 'fail'):
            return False
        try:
            nicksub.Person(self.arguments[1])
        except nicksub.PersonNotFoundError:
            try:
                nicksub.Person(self.arguments[1], context=self.context)
            except:
                return '<attacker> must be a person'
        if len(self.arguments) == 3:
            try:
                nicksub.Person(self.arguments[2])
            except nicksub.PersonNotFoundError:
                try:
                    nicksub.Person(self.arguments[2], context=self.context)
                except:
                    return '<target> must be a person'
        return True
    
    def permission_level(self):
        return 3
    
    def run(self):
        success = self.arguments[0].lower() == 'win'
        if len(self.arguments) == 3:
            try:
                attacker = nicksub.Person(self.arguments[1])
            except nicksub.PersonNotFoundError:
                attacker = nicksub.Person(self.arguments[1], context=self.context)
            try:
                target = nicksub.Person(self.arguments[2])
            except nicksub.PersonNotFoundError:
                target = nicksub.Person(self.arguments[2], context=self.context)
        else:
            attacker = self.sender
            try:
                target = nicksub.Person(self.arguments[1])
            except nicksub.PersonNotFoundError:
                target = nicksub.Person(self.arguments[1], context=self.context)
        core.death_games_log(attacker, target, success)

class DeathTweet(BaseCommand):
    """toggle death message tweeting"""
    
    usage = '[on | off [<time>]]'
    
    def parse_args(self):
        if len(self.arguments) > 2:
            return False
        elif len(self.arguments) >= 1:
            if self.arguments[0] not in ('on', 'off'):
                return False
            if len(self.arguments) == 2:
                if self.arguments[0] == 'on':
                    return False
                try:
                    core.parse_timedelta(self.arguments[1])
                except:
                    return '<time> must be a time interval, like 2h16m30s'
        return True
    
    def permission_level(self):
        if len(self.arguments) == 2 and parse_timedelta(self.arguments[1]) > timedelta(days=1):
            return 4
        return 3
    
    def reenable_death_tweets():
        core.state['death_tweets'] = True
        self.reply('Death tweets are back on')
    
    def run(self):
        if len(self.arguments) == 0:
            self.reply('Deathtweeting is currently ' + ('enabled' if core.state['death_tweets'] else 'disabled'))
        elif self.arguments[0] == 'on':
            core.state['death_tweets'] = True
            self.reply('Deathtweeting is now enabled')
        else:
            if len(self.arguments) == 2:
                number = core.parse_timedelta(self.arguments[1])
                threading.Timer(number, self.reenable_death_tweets).start()
            core.state['death_tweets'] = False
            self.reply('Deathtweeting is now disabled')

class FixStatus(BaseCommand):
    """update the server status on the website and in the channel topic"""
    
    def parse_args(self):
        if len(self.arguments):
            return False
        return True
    
    def run(self):
        core.update_all(force=True)

class Help(BaseCommand):
    """get help on a command"""
    
    usage = '[aliases | commands | <alias> | <command>]'
    
    def parse_args(self):
        if len(self.arguments) > 2:
            return False
        return True
    
    def reply(self, irc_reply, tellraw_reply=None):
        if self.context == 'irc':
            if self.addressing is None:
                core.state['bot'].say(self.sender.irc_nick(respect_highlight_option=False), irc_reply)
            else:
                core.state['bot'].say(self.addressing.irc_nick(respect_highlight_option=False), '(from ' + self.sender.irc_nick(respect_highlight_option=False) + ') ' + irc_reply)
        else:
            return super().reply(irc_reply, tellraw_reply)
    
    def run(self):
        if len(self.arguments) == 0:
            self.reply('Hello, I am ' + ('wurstminebot' if core.config('irc').get('nick', 'wurstminebot') == 'wurstminebot' else core.config('irc')['nick'] + ', a wurstminebot') + '. I sync messages between IRC and Minecraft, and respond to various commands.')
            self.reply('Execute “Help commands” for a list of commands, or “Help <command>” (replace <command> with a command name) for help on a specific command.', 'Execute "Help commands" for a list of commands, or "Help <command>" (replace <command> with a command name) for help on a specific command.')
            help_text = 'To execute a command, send it to me in private chat (here) or address me in a channel (like this: “' + core.config('irc').get('nick', 'wurstminebot') + ': <command>...”). You can also execute commands in a channel or in Minecraft like this: “!<command>...”.'
            help_text_tellraw = 'You can execute a command by typing "!<command>..." in the in-game chat or an IRC channel. You can also send the command to me in a private IRC query (without the "!") or address me in a channel (like this: "' + core.config('irc').get('nick', 'wurstminebot') + ': <command>...").'
            self.reply(help_text, help_text_tellraw)
        elif self.arguments[0].lower() == 'aliases':
            num_aliases = len(list(core.config('aliases').keys()))
            if num_aliases > 0:
                help_text = 'Currently defined aliases: ' + ', '.join(sorted(list(core.config('aliases').keys()))) + '. For more information, execute'
            else:
                help_text = 'No aliases are currently defined. For more information, execute'
            self.reply(help_text + ' “Help alias”.', help_text + ' "Help alias".')
        elif self.arguments[0].lower() == 'commands':
            num_aliases = len(list(core.config('aliases').keys()))
            self.reply('Available commands: ' + ', '.join(sorted([command_class.__name__ for command_class in classes])) + (', and ' + str(num_aliases) + ' aliases.' if num_aliases > 0 else '.'))
        elif self.arguments[0].lower() in core.config('aliases'):
            alias_dict = core.config('aliases')[self.arguments[0].lower()]
            if alias_dict.get('type') == 'command':
                self.reply(self.arguments[0].lower() + ' is ' + ('an alias of ' + alias_dict['command_name'] if 'command_name' in alias_dict else 'a broken alias') + '.')
            elif alias_dict.get('type') == 'disable':
                self.reply(self.arguments[0].lower() + ' is disabled.')
            elif alias_dict.get('type') == 'reply':
                self.reply(self.arguments[0].lower() + ' is an echo alias. Execute it to see what the reply is.')
            elif alias_dict.get('type') == 'say':
                self.reply(self.arguments[0].lower() + ' is an alias. Execute it to see what it stands for.')
            else:
                self.reply(self.arguments[0] + ' is a broken alias.')
        else:
            for command_class in classes:
                if command_class.__name__.lower() == self.arguments[0].lower():
                    self.reply(command_class.__name__ + ': ' + command_class.__doc__)
                    self.reply('Usage: ' + command_class.__name__ + ('' if command_class.usage is None else (' ' + command_class.usage)))
                    self.reply('More info: http://wiki.wurstmineberg.de/Commands#' + command_class.__name__, {'text': 'More info', 'clickEvent': {'action': 'open_url', 'value': 'http://wiki.wurstmineberg.de/Commands#' + command_class.__name__}})
                    break
            else:
                self.reply(core.ErrorMessage.unknown(self.arguments[0]))

class Invite(BaseCommand):
    """invite a new player"""
    
    usage = '<unique_id> <minecraft_name> [<twitter_username>]'
    
    def parse_args(self):
        if len(self.arguments) not in range(2, 4):
            return False
        if not re.match('[a-z][0-9a-z]{1,15}$', self.arguments[0].lower()):
            return '<unique_id> must be a valid Wurstmineberg ID: alphanumeric, 2 to 15 characters, and start with a letter'
        try:
            nicksub.Person(self.arguments[0], strict=False)
        except:
            pass # person with this ID does not exist
        else:
            return 'a person with this Wurstmineberg ID already exists'
        if not re.match(minecraft.regexes.player, self.arguments[1]):
            return '<minecraft_name> is not a valid Minecraft nickname'
        if len(self.arguments) > 2 and not re.match('@?[A-Za-z0-9_]{1,15}$', self.arguments[2]):
            return '<twitter_username> is invalid, see https://support.twitter.com/articles/101299'
        return True
    
    def permission_level(self):
        response = requests.get('https://s3.amazonaws.com/MinecraftSkins/' + self.arguments[1] + '.png')
        if response.status_code != 200:
            return 4
        return 3
    
    def run(self):
        if len(self.arguments) == 3 and self.arguments[2] is not None and len(self.arguments[2]):
            screen_name = self.arguments[2][1:] if self.arguments[2].startswith('@') else self.arguments[2]
        else:
            screen_name = None
        minecraft.whitelist_add(self.arguments[0].lower(), minecraft_nick=self.arguments[1], people_file=core.config('paths').get('people'), person_status='invited', invited_by=self.sender)
        self.reply('A new person with id ' + self.arguments[0].lower() + ' is now invited. The !Whitelist command must be run by a bot op.')
        if screen_name is not None:
            core.set_twitter(nicksub.Person(self.arguments[0]), screen_name)
            self.reply('@' + core.config('twitter')['screen_name'] + ' is now following @' + screen_name)

class Join(BaseCommand):
    """make the bot join a channel"""
    
    usage = '<channel>'
    
    def parse_args(self):
        if len(self.arguments) != 1:
            return False
        if not self.arguments[0].startswith('#'):
            return '<channel> is not a valid IRC channel name'
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        chans = sorted(core.config('irc').get('channels', []))
        if str(self.arguments[0]) in chans:
            self.warning('I am already in ' + self.arguments[0])
        else:
            chans.append(self.arguments[0])
            chans = sorted(chans)
            core.update_config(['irc', 'channels'], chans)
        core.state['bot'].joinchan(self.arguments[0])

class LastSeen(BaseCommand):
    """when was the player last seen logging in or out on Minecraft"""
    
    usage = '<player>'
    
    def parse_args(self):
        if len(self.arguments) != 1:
            return False
        if nicksub.exists(self.arguments[0]):
            return True
        try:
            person = nicksub.Person(self.arguments[0], context=self.context)
        except nicksub.PersonNotFoundError:
            try:
                person = nicksub.Person(self.arguments[0], context='minecraft')
            except nicksub.PersonNotFoundError:
                return '<player> must be a person'
        if person.minecraft is None:
            return '<player> does not have a Minecraft nickname'
        return True
    
    def run(self):
        player = self.arguments[0]
        try:
            person = nicksub.Person(player)
        except nicksub.PersonNotFoundError:
            try:
                person = nicksub.Person(player, context=self.context)
            except nicksub.PersonNotFoundError:
                person = nicksub.Person(player, context='minecraft')
        if person.minecraft in minecraft.online_players():
            self.reply(player + ' is currently on the server.', [
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
            with core.state['log_lock']:
                lastseen = None
                if 'logs' in core.config('paths') and os.path.exists(os.path.join(core.config('paths')['logs'], 'logins.log')):
                    lastseen = minecraft.last_seen(person, logins_log=os.path.join(core.config('paths')['logs'], 'logins.log'))
                if lastseen is None:
                    self.reply('let me check the logs…', 'checking the logs...')
                    lastseen = minecraft.last_seen(person.minecraft)
                if lastseen is None:
                    self.reply('I have not seen ' + player + ' on the server yet.')
                else:
                    lastseen = lastseen.astimezone(timezone.utc)
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
                    self.reply(player + ' was last seen ' + datestr + '.', [
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

class Leak(BaseCommand):
    """tweet the last line_count (defaults to 1) chatlog lines"""
    
    usage = '[<line_count>]'
    
    def parse_args(self):
        if len(self.arguments) not in range(0, 2):
            return False
        if len(self.arguments) > 0:
            try:
                if int(self.arguments[0]) < 1:
                    return '<line_count> must be at least 1'
            except ValueError:
                return '<line_count> must be a positive integer'
        return True
    
    def permission_level(self):
        return 2
    
    def run(self):
        irc_config = core.config('irc')
        if 'main_channel' not in irc_config:
            self.warning('No channel to leak from!')
            return
        messages = [(msg_type, msg_sender, msg_text) for msg_type, msg_sender, msg_headers, msg_text in core.state['bot'].channel_data[irc_config['main_channel']]['log'] if msg_type == 'ACTION' or (msg_type == 'PRIVMSG' and (not msg_text.startswith('!')) and (not msg_text.startswith(irc_config['nick'] + ': ')) and (not msg_text.startswith(irc_config['nick'] + ', ')))]
        if len(self.arguments) == 0:
            if len(messages):
                messages = [messages[-1]]
            else:
                self.warning(core.ErrorMessage.log)
                return
        else:
            if re.match('[0-9]+$', self.arguments[0]) and len(messages) >= int(self.arguments[0]):
                messages = messages[-int(self.arguments[0]):]
            else:
                self.warning(core.ErrorMessage.log)
                return
        status = '\n'.join(((('* ' + nicksub.sub(msg_sender, 'irc', 'twitter') + ' ') if msg_type == 'ACTION' else ('<' + nicksub.sub(msg_sender, 'irc', 'twitter') + '> ')) + nicksub.textsub(message, 'irc', 'twitter')) for msg_type, msg_sender, message in messages)
        if len(status + ' #ircleaks') <= 140:
            if '\n' in status:
                status += '\n#ircleaks'
            else:
                status += ' #ircleaks'
        try:
            twid = core.tweet(status)
        except core.TwitterError as e:
            self.warning('Error ' + str(e.status_code) + ': ' + str(e))
            return
        except AttributeError:
            self.warning('Twitter is not configured.')
        else:
            tweet_url = 'https://twitter.com/' + core.config('twitter').get('screen_name', 'wurstmineberg') + '/status/' + str(twid)
            minecraft.tellraw({
                'text': 'leaked',
                'clickEvent': {
                    'action': 'open_url',
                    'value': tweet_url
                },
                'color': 'gold'
            })
            core.state['bot'].say(irc_config['main_channel'], 'leaked ' + tweet_url)

class MinecraftWiki(BaseCommand):
    """look something up in the Minecraft Wiki"""
    
    usage = '(<url> | <article>...)'
    
    def parse_args(self):
        if len(self.arguments) == 0:
            return False
        return True
    
    def run(self):
        core.minecraft_wiki_lookup(article='_'.join(self.arguments), reply=self.reply)

class Option(BaseCommand):
    """change your options"""
    
    usage = '<option> [(on | off | reset | show) [<person>]]'
    
    def parse_args(self):
        if len(self.arguments) not in range(1, 4):
            return False
        if not re.match('[a-z_]+$', self.arguments[0].lower()):
            return 'option names only contain letters and underscores'
        if len(self.arguments) >= 2 and self.arguments[1].lower() not in ('\\delete', '\\reset', 'true', 'false', 'yes', 'no', 'on', 'off', 'reset', 'delete', 'show'):
            return False
        if len(self.arguments) >= 3 and not nicksub.exists(self.arguments[2]):
            return '<person> must be an existing Wurstmineberg ID'
        return True
    
    def permission_level(self):
        if len(self.arguments) >= 3 and self.arguments[1].lower() != 'show' and nicksub.Person(self.arguments[2]) != self.sender:
            return 4
        return 1
    
    def run(self):
        target_person = nicksub.Person(self.arguments[2]) if len(self.arguments) >= 3 else self.sender
        target_nick = 'you' if target_person == (self.addressing or self.sender) else target_person.nick(self.context)
        if len(self.arguments) == 1 or self.arguments[1].lower() == 'show':
            flag = target_person.option(self.arguments[0])
            is_default = target_person.option_is_default(self.arguments[0])
            self.reply('option ' + self.arguments[0].lower() + ' is ' + ('on' if flag else 'off') + ' for ' + target_nick + (' by default' if is_default else ''))
        elif self.arguments[1].lower() in ('on', 'true', 'yes'):
            previous_value = target_person.option(self.arguments[0])
            previous_value_is_default = target_person.option_is_default(self.arguments[0])
            target_person.set_option(self.arguments[0], True)
            self.reply('option ' + self.arguments[0].lower() + ' is now on for ' + target_nick + ' (was ' + ('on' if previous_value else 'off') + (' by default' if previous_value_is_default else '') + ')')
        elif self.arguments[1].lower() in ('false', 'no', 'off'):
            previous_value = target_person.option(self.arguments[0])
            previous_value_is_default = target_person.option_is_default(self.arguments[0])
            target_person.set_option(self.arguments[0], False)
            self.reply('option ' + self.arguments[0].lower() + ' is now off for ' + target_nick + ' (was ' + ('on' if previous_value else 'off') + (' by default' if previous_value_is_default else '') + ')')
        else:
            previous_value = target_person.option(self.arguments[0])
            previous_value_is_default = target_person.option_is_default(self.arguments[0])
            target_person.del_option(self.arguments[0])
            self.reply('option ' + self.arguments[0].lower() + ' is now ' + ('on' if target_person.option(self.arguments[0]) else 'off') + ' for ' + target_nick + ' by default (was ' + ('on' if previous_value else 'off') + (' by default' if previous_value_is_default else '') + ')')

class PasteMojira(BaseCommand):
    """print the title of a bug in Mojang's bug tracker"""
    
    usage = '(<url> | [<project_key>] <issue_id>) [nolink]'
    
    def parse_args(self):
        if len(self.arguments) > 1 and self.arguments[-1].lower() == 'nolink':
            arguments = self.arguments[:-1]
        else:
            arguments = self.arguments
        if len(arguments) > 2:
            return False
        if len(arguments) == 1:
            if not re.match('(https?://(mojang\\.atlassian\\.net|bugs\\.mojang\\.com)/browse/)?[A-Z]+-[0-9]+', arguments[0]):
                try:
                    int(arguments[0])
                except ValueError:
                    return 'no valid <url> or <issue_id> specified'
        if len(arguments) == 2:
            try:
                int(arguments[1])
            except ValueError:
                return '<issue_id> must be a positive integer'
        return True
    
    def run(self):
        link = True
        if len(self.arguments) > 1 and self.arguments[-1].lower() == 'nolink':
            link = False
            arguments = self.arguments[:-1]
        else:
            arguments = self.arguments[:]
        if len(arguments) == 2:
            project_key = arguments[0]
            issue_id = int(arguments[1])
        elif len(arguments) == 1:
            match = re.match('(https?://(mojang\\.atlassian\\.net|bugs\\.mojang\\.com)/browse/)?([A-Z]+)-([0-9]+)', arguments[0])
            if match:
                project_key = str(match.group(3))
                issue_id = int(match.group(4))
            else:
                project_key = 'MC'
                issue_id = int(arguments[0])
        else:
            self.reply('http://mojang.atlassian.net/browse/MC')
            return
        self.reply(core.paste_mojira(project_key, issue_id, link=link), core.paste_mojira(project_key, issue_id, link=link, tellraw=True))

class PasteTweet(BaseCommand):
    """print the contents of a tweet"""
    
    usage = '(<url> | <status_id>) [nolink]'
    
    def parse_args(self):
        if self.arguments[-1].lower() == 'nolink':
            arguments = self.arguments[:-1]
        else:
            arguments = self.arguments
        if len(arguments) != 1:
            return False
        if not re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/[0-9]+', arguments[0]):
            try:
                int(arguments[0])
            except ValueError:
                return 'no valid <url> or <status_id> specified'
        return True
    
    def run(self):
        link = self.arguments[-1].lower() != 'nolink'
        match = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)', self.arguments[0])
        twid = int(match.group(1) if match else self.arguments[0])
        try:
            self.reply(core.paste_tweet(twid, link=link), core.paste_tweet(twid, link=link, tellraw=True))
        except core.TwitterError as e:
            self.warning('Error ' + str(e.status_code) + ': ' + str(e))
        except AttributeError:
            self.warning('Twitter is not configured')

class People(BaseCommand):
    """people.json management"""
    
    usage = '[<person> [<attribute> [<value>...]]]'
    
    def parse_args(self):
        if len(self.arguments) >= 1:
            try:
                nicksub.Person(self.arguments[0])
            except nicksub.PersonNotFoundError:
                return '<person> must be an existing Wurstmineberg ID'
            if len(self.arguments) >= 2:
                if self.arguments[1].lower() == 'favcolor':
                    if len(self.arguments) == 2:
                        return True
                    if len(self.arguments) == 3:
                        if re.match('#?([0-9A-Fa-f]{3}){1,2}$', self.arguments[2]):
                            return True
                        return '<value> must be a color in hex format: #RRGGBB or #RGB'
                    if len(self.arguments) == 5:
                        try:
                            r = int(self.arguments[2])
                        except:
                            return 'red part of color must be a number'
                        try:
                            g = int(self.arguments[3])
                        except:
                            return 'green part of color must be a number'
                        try:
                            b = int(self.arguments[4])
                        except:
                            return 'blue part of color must be a number'
                        if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                            return True
                        return 'all color components must be between 0 and 255'
                    return '<value> must be a color in hex format: #RRGGBB or #RGB; or in decimal format: <red> <green> <blue>'
                if self.arguments[1].lower() == 'gravatar':
                    if len(self.arguments) == 2:
                        return True
                    if len(self.arguments) > 3:
                        return '<value> must be an e-mail address, no spaces allowed'
                    if self.arguments[2].lower() in ['delete', 'reset']:
                        return True
                    if '@' not in self.arguments[2]:
                        return '<value> must be an e-mail address'
                    return True
                if self.arguments[1].lower() in ['description', 'name', 'wiki']:
                    return True
                if self.arguments[1].lower() in ['reddit', 'twitter', 'website']:
                    if len(self.arguments) > 3:
                        return 'no spaces allowed in <value>'
                    return True
                return '<attribute> must be description, favcolor, gravatar, name, reddit, twitter, website, or wiki'
        return True
    
    def permission_level(self):
        if len(self.arguments) == 3:
            if self.sender != nicksub.Person(self.arguments[0]):
                return 4
        return 0
    
    def run(self):
        if len(self.arguments):
            person = nicksub.Person(self.arguments[0])
            if len(self.arguments) >= 2:
                if self.arguments[1].lower() == 'description':
                    if len(self.arguments) == 2:
                        if person.description:
                            self.reply(person.description)
                        else:
                            self.reply('no description')
                    else:
                        old_description = person.description
                        person.description = ' '.join(self.arguments[2:])
                        self.reply('description ' + ('updated, was “' + old_description + '”' if old_description else 'added'))
                elif self.arguments[1].lower() == 'favcolor':
                    if len(self.arguments) == 2:
                        if person.fav_color:
                            self.reply('#%02x%02x%02x' % person.fav_color)
                        else:
                            self.reply(person.display_name() + ' has no favorite color')
                    else:
                        if len(self.arguments) == 3:
                            match = re.match('#?([0-9A-Fa-f]{3})$', self.arguments[2])
                            if match:
                                r = int(match.group(1)[0], 16) * 0x11
                                g = int(match.group(1)[1], 16) * 0x11
                                b = int(match.group(1)[2], 16) * 0x11
                            else:
                                match = re.match('#?([0-9A-Fa-f]{6})$', self.arguments[2])
                                r = int(match.group(1)[:2], 16)
                                g = int(match.group(1)[2:4], 16)
                                b = int(match.group(1)[4:], 16)
                        else:
                            r = int(self.arguments[2])
                            g = int(self.arguments[3])
                            b = int(self.arguments[4])
                        old_color = person.fav_color
                        person.fav_color = r, g, b
                        self.reply('favorite color ' + ('changed, was #%02x%02x%02x' % old_color if old_color else 'added'))
                elif self.arguments[1].lower() == 'gravatar':
                    if len(self.arguments) == 2:
                        if person.gravatar_email:
                            self.reply(person.gravatar_email)
                        else:
                            self.reply('no Gravatar address')
                    else:
                        old_gravatar = person.gravatar_email
                        if self.arguments[2].lower() in ['delete', 'reset']:
                            del person.gravatar_email
                            self.reply('Gravatar address deleted, was ' + old_gravatar if old_gravatar else 'no Gravatar address to delete' + (' :V' if random.randrange(0, 2) else ''))
                            return
                        person.gravatar_email = self.arguments[2]
                        self.reply('Gravatar address ' + ('changed, was ' + old_gravatar if old_gravatar else 'added'))
                elif self.arguments[1].lower() == 'name':
                    if len(self.arguments) == 2:
                        if person.name:
                            self.reply(person.name)
                        else:
                            self.reply('no name, using id: ' + person.id)
                    else:
                        old_name = person.name
                        person.name = ' '.join(self.arguments[2:])
                        self.reply('name ' + ('changed, was “' + old_name + '”' if old_name else 'added'))
                elif self.arguments[1].lower() == 'reddit':
                    if len(self.arguments) == 2:
                        if person.reddit:
                            self.reply('/u/' + person.reddit)
                        else:
                            self.reply('no reddit nick')
                    else:
                        old_reddit_nick = person.reddit
                        reddit_nick = self.arguments[2][3:] if self.arguments[2].startswith('/u/') else self.arguments[2]
                        person.reddit = reddit_nick
                        self.reply('reddit nick ' + ('changed, was /u/' + old_reddit_nick if old_reddit_nick else 'added'))
                elif self.arguments[1].lower() == 'twitter':
                    if len(self.arguments) == 2:
                        if person.twitter:
                            self.reply('@' + person.twitter)
                        else:
                            self.reply('no twitter nick')
                    else:
                        screen_name = self.arguments[2][1:] if self.arguments[2].startswith('@') else self.arguments[2]
                        core.set_twitter(person, screen_name)
                        self.reply('@' + core.config('twitter')['screen_name'] + ' is now following @' + screen_name)
                elif self.arguments[1].lower() == 'website':
                    if len(self.arguments) == 2:
                        if person.website:
                            self.reply(person.website)
                        else:
                            self.reply('no website')
                    else:
                        old_website = person.website
                        person.website = self.arguments[2]
                        self.reply('website ' + ('changed, was ' + old_website if old_website else 'added'))
                elif self.arguments[1].lower() == 'wiki':
                    if len(self.arguments) == 2:
                        if person.wiki:
                            self.reply(person.wiki)
                        else:
                            self.reply('no wiki account')
                    else:
                        old_wiki = person.wiki
                        new_wiki = self.arguments[2]
                        if new_wiki.startswith('User:') or new_wiki.startswith('user:'):
                            new_wiki = new_wiki[5:]
                        new_wiki = new_wiki[0].upper() + new_wiki[1:]
                        person.wiki = new_wiki
                        self.reply('wiki account ' + ('changed, was “' + old_wiki + '”' if old_wiki else 'added'))
            else:
                self.reply('person with id ' + person.id + ' and ' + ('no name (id will be used as name)' if person.name is None else 'name ' + person.name) + ' http://wurstmineberg.de/people/' + person.id, {
                    'clickEvent': {
                        'action': 'open_url',
                        'value': 'http://wurstmineberg.de/people/' + person.id
                    },
                    'color': 'gold',
                    'text': 'person with id ' + person.id + ' and ' + ('no name (id will be used as name)' if person.name is None else 'name ' + person.name)
                })
        else:
            self.reply('http://wurstmineberg.de/people', {
                'text': 'http://wurstmineberg.de/people',
                'color': 'gold',
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'http://wurstmineberg.de/people'
                }
            })
    
class Quit(BaseCommand):
    """stop the bot with a custom quit message"""
    
    usage = '[<quit_message>...]'
    
    def permission_level(self):
        return 4
    
    def run(self):
        quitMsg = ' '.join(self.arguments) if len(self.arguments) else None
        minecraft.tellraw({
            'text': ('Shutting down the bot: ' + quitMsg) if quitMsg else 'Shutting down the bot...',
            'color': 'red'
        })
        irc_config = core.config('irc')
        if 'main_channel' in irc_config:
            core.state['bot'].say(irc_config['main_channel'], ('bye, ' + quitMsg) if quitMsg else random.choice(irc_config.get('quit_messages', ['bye'])))
        core.state['bot'].disconnect(quitMsg if quitMsg else 'bye')
        core.cleanup()
        sys.exit()

class Raw(BaseCommand):
    """send raw message to IRC"""
    
    usage = '<raw_message>...'
    
    def parse_args(self):
        if len(self.arguments) == 0:
            return False
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        core.state['bot'].send(' '.join(self.arguments))

class Restart(BaseCommand):
    """restart the Minecraft server or the bot"""
    
    usage = '[minecraft | bot]'
    
    def parse_args(self):
        if len(self.arguments) == 0:
            return True
        if len(self.arguments) == 1 and self.arguments[0].lower() in ['bot', 'minecraft', 'server']:
            return True
        return False
    
    def permission_level(self):
        return 4
    
    def run(self):
        if len(self.arguments) == 0 or (len(self.arguments) == 1 and self.arguments[0].lower() == 'bot'):
            # restart the bot
            minecraft.tellraw({
                'text': 'Restarting the bot...',
                'color': 'red'
            })
            irc_config = core.config('irc')
            if 'main_channel' in irc_config:
                core.state['bot'].say(irc_config['main_channel'], random.choice(irc_config.get('quit_messages', ['brb'])))
            core.state['bot'].disconnect('brb')
            core.cleanup()
            subprocess.Popen(['service', 'wurstminebot', 'restart'])
        else:
            # restart the Minecraft server
            if not core.status['server_control_lock'].acquire():
                self.warning('Server access is locked. Not restarting server.')
                return
            core.update_topic(special_status='The server is restarting…')
            if minecraft.restart(reply=self.reply, log_path=os.path.join(core.config('paths')['logs'], 'logins.log')):
                self.reply('Server restarted.')
            else:
                self.reply('Could not restart the server!')
            core.update_topic()
            core.status['server_control_lock'].release()

class Retweet(BaseCommand):
    """retweet a tweet with the bot's twitter account"""
    
    usage = '(<url> | <status_id>) [nopaste]'
    
    def parse_args(self):
        if len(self.arguments) != 1:
            if len(self.arguments) != 2:
                return False
            if self.arguments[1].lower() != 'nopaste':
                return False
        if not re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/[0-9]+', self.arguments[0]):
            try:
                int(self.arguments[0])
            except ValueError:
                return 'no valid <url> or <status_id> specified'
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        import TwitterAPI
        if len(self.arguments) > 1:
            paste = self.arguments[1].lower() != 'nopaste'
        else:
            paste = True
        match = re.match('https?://twitter\\.com/[0-9A-Z_a-z]+/status/([0-9]+)', self.arguments[0])
        twid = int(match.group(1) if match else self.arguments[0])
        r = core.twitter.request('statuses/retweet/:' + str(twid))
        if isinstance(r, TwitterAPI.TwitterResponse):
            j = r.response.json()
        else:
            j = r.json()
        if r.status_code == 200:
            twid = j['id']
        else:
            first_error = j.get('errors', [])
            if isinstance(first_error, list):
                first_error = first_error[0] if len(first_error) else {}
            if isinstance(first_error, str):
                first_error = {'message': first_error}
            raise core.TwitterError(first_error.get('code', 0), message=first_error.get('message'), status_code=r.status_code, errors=j.get('errors', []))
        url = 'https://twitter.com/' + core.config('twitter')['screen_name'] + '/status/' + str(twid)
        if paste:
            if self.context == 'minecraft':
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
                minecraft.tellraw(core.paste_tweet(twid, tellraw=True, link=True))
            if self.channel is not None:
                core.state['bot'].say(self.channel, url)
            irc_config = core.config('irc')
            if 'main_channel' in irc_config and self.channel != irc_config['main_channel']:
                for line in core.paste_tweet(twid, link=True).splitlines():
                    core.state['bot'].say(irc_config['main_channel'], line)
        else:
            self.reply(url)

class Status(BaseCommand):
    """print some server status"""
    
    def parse_args(self):
        if len(self.arguments):
            return False
        return True
    
    def run(self):
        import requests
        if minecraft.status():
            if self.context != 'minecraft':
                players = nicksub.sorted_people(nicksub.person_or_dummy(minecraft_nick, context='minecraft') for minecraft_nick in minecraft.online_players())
                if len(players):
                    self.reply('Online players: ' + ', '.join(person.nick(self.context) for person in players))
                else:
                    self.reply('The server is currently empty.')
            version = minecraft.version()
            if version is None:
                self.reply('unknown Minecraft version')
            else:
                version_url = minecraft.wiki_version_link(version)
                self.reply('Minecraft version ' + version + ' [' + version_url + ']', [
                    {
                        'color': 'gold',
                        'text': 'Minecraft version '
                    },
                    {
                        'clickEvent': {
                            'action': 'open_url',
                            'value': version_url
                        },
                        'color': 'gold',
                        'text': version
                    }
                ])
        else:
            self.reply('The server is currently offline.')
        response = requests.get('http://status.mojang.com/check')
        for item in response.json():
            for key, value in item.items():
                if value != 'green':
                    self.reply('Mojang service ' + key + ' has status ' + json.dumps(value), [
                        {
                            'clickEvent': {
                                'action': 'open_url',
                                'value': 'http://status.mojang.com/check'
                            },
                            'color': 'gold',
                            'text': 'Mojang service'
                        },
                        {
                            'text': ' '
                        },
                        {
                            'clickEvent': {
                                'action': 'open_url',
                                'value': key
                            },
                            'color': 'gold',
                            'text': key
                        },
                        {
                            'color': 'gold',
                            'text': ' has status '
                        },
                        {
                            'color': value if value in ('yellow', 'red') else 'gold',
                            'text': json.dumps(value)
                        }
                    ])

class Stop(BaseCommand):
    """stop the Minecraft server or the bot"""
    
    usage = '[minecraft | bot]'
    
    def parse_args(self):
        if len(self.arguments) == 0:
            return True
        if len(self.arguments) == 1:
            if self.arguments[0].lower() in ['bot', 'minecraft']:
                return True
        return False
    
    def permission_level(self):
        return 4
    
    def run(self):
        if len(self.arguments) == 0 or (len(self.arguments) == 1 and self.arguments[0] == 'bot'):
            # stop the bot
            return Quit(args=self.arguments, sender=self.sender, context=self.context, channel=self.channel, addressing=self.addressing).run()
        # stop the Minecraft server
        if not core.status['server_control_lock'].acquire():
            self.warning('Server access is locked. Not stopping server.')
            return
        core.update_topic(special_status='The server is down for now. Blame ' + self.sender.irc_nick(respect_highlight_option=False) + '.')
        if minecraft.stop(reply=self.reply, log_path=os.path.join(core.config('paths')['logs'], 'logins.log')):
            self.reply('Server stopped.')
        else:
            self.warning('The server could not be stopped! D:')
        core.status['server_control_lock'].release()

class Time(BaseCommand):
    """reply with the current time"""
    
    def parse_args(self):
        if len(self.arguments):
            return False
        return True
    
    def run(self):
        from wurstminebot import loops
        loops.tell_time(func=self.reply)

class Topic(BaseCommand):
    """change the main channel's topic"""
    
    usage = '[<topic>...]'
    
    def permission_level(self):
        return 4
    
    def run(self):
        topic = None if len(self.arguments) == 0 else ' '.join(self.arguments)
        core.update_config(['irc', 'topic'], topic)
        core.update_topic()

class Tweet(BaseCommand):
    """write a tweet as the bot's Twitter account"""
    
    usage = '<message>...'
    
    def parse_args(self):
        if len(self.arguments) == 0:
            return False
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        status = nicksub.textsub(' '.join(self.arguments), self.context, 'twitter')
        try:
            twid = core.tweet(status)
        except AttributeError:
            self.warning('Twitter is not configured.')
            return
        url = 'https://twitter.com/' + core.config('twitter')['screen_name'] + '/status/' + str(twid)
        if self.context == 'minecraft':
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
            minecraft.tellraw(core.paste_tweet(twid, tellraw=True, link=True))
        if self.channel is not None:
            core.state['bot'].say(self.channel, url)
        irc_config = core.config('irc')
        if 'main_channel' in irc_config and self.channel != irc_config['main_channel']:
            for line in core.paste_tweet(twid, link=True).splitlines():
                core.state['bot'].say(irc_config['main_channel'], line)

class Update(BaseCommand):
    """update Minecraft"""
    
    usage = '[release | snapshot [<snapshot_id>] | <version>]'
    muted_backup_messages = {
        'Minecraft is running... suspending saves',
        'Minecraft is running... re-enabling saves',
        'Symlinking to httpdocs...',
        'Done.'
    }
    
    def backup_reply(self, message):
        if message not in self.muted_backup_messages:
            self.reply(message)
    
    def parse_args(self):
        if len(self.arguments) > 0:
            if self.arguments[0].lower() == 'snapshot':
                if len(self.arguments) > 2:
                    return False
                if len(self.arguments) == 2:
                    if not re.match('[a-z]', self.arguments[1].lower()):
                        return '<snapshot_id> must be a single Latin letter'
            elif len(self.arguments) != 1:
                return False
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        if not core.status['server_control_lock'].acquire():
            self.warning('Server access is locked. Not stopping server.')
            return
        core.update_topic(special_status='The server is being updated, wait a sec.')
        backup_thread = None
        version = minecraft.version()
        if version is not None and 'backup' in minecraft.config('paths'):
            path = os.path.join(minecraft.config('paths')['backup'], 'pre-update', minecraft.config('world') + '_' + re.sub('\\.', '_', version))
            backup_thread = threading.Thread(target=minecraft.backup, kwargs={'reply': self.backup_reply, 'announce': True, 'path': path})
            backup_thread.start()
        if (len(self.arguments) == 1 and self.arguments[0].lower() != 'snapshot') or len(self.arguments) == 2:
            if self.arguments[0].lower() == 'snapshot': # !update snapshot <snapshot_id>
                update_iterator = minecraft.iter_update(version=(self.arguments[1].lower() if len(self.arguments) == 2 else 'a'), snapshot=True, reply=self.reply, log_path=os.path.join(core.config('paths')['logs'], 'logins.log'))
            elif self.arguments[0] == 'release': # !update release
                update_iterator = minecraft.iter_update(snapshot=False, reply=self.reply, log_path=os.path.join(core.config('paths')['logs'], 'logins.log'))
            else: # !update <version>
                update_iterator = minecraft.iter_update(version=self.arguments[0], snapshot=False, reply=self.reply, log_path=os.path.join(core.config('paths')['logs'], 'logins.log'))
        else: # !update [snapshot]
            update_iterator = minecraft.iter_update(snapshot=True, reply=self.reply, log_path=os.path.join(core.config('paths')['logs'], 'logins.log'))
        version_dict = next(update_iterator)
        version = version_dict['version']
        snapshot = version_dict['is_snapshot']
        version_text = version_dict['version_text']
        self.reply('Downloading ' + version_text)
        assert next(update_iterator) == 'Download finished. Stopping server...'
        if backup_thread is None:
            self.reply('Download finished. Stopping server...')
        else:
            backup_thread.join()
            self.reply('Backup and download finished. Stopping server...')
        for message in update_iterator:
            self.reply(message)
        try:
            twid = core.tweet('Server updated to ' + version_text + '! Wheee! See ' + minecraft.wiki_version_link(version) + ' for details.')
        except (core.TwitterError, AttributeError):
            self.reply('…done updating, but the announcement tweet failed.', '...done updating, but the announcement tweet failed.')
        else:
            status_url = core.config('twitter').get('screen_name', 'wurstmineberg') + '/status/' + str(twid)
            self.reply('…done [https://twitter.com/' + status_url + ']', {
                'text': '...done',
                'clickEvent': {
                    'action': 'open_url',
                    'value': 'https://twitter.com/' + status_url
                },
                'color': 'gold'
            })
        core.update_topic()
        core.state['server_control_lock'].release()

class Version(BaseCommand):
    """reply with the current version of wurstminebot and init-minecraft"""
    
    def parse_args(self):
        if len(self.arguments):
            return False
        return True
    
    def run(self):
        self.reply('I am wurstminebot version ' + core.__version__ + ', running on init-minecraft version ' + minecraft.__version__)

class Whitelist(BaseCommand):
    """add someone to the whitelist"""
    
    usage = '<unique_id> [<minecraft_name> [<twitter_username>]]'
    
    def parse_args(self):
        if len(self.arguments) not in range(1, 4):
            return False
        if not re.match('[a-z][0-9a-z]{1,15}$', self.arguments[0].lower()):
            return '<unique_id> must be a valid Wurstmineberg ID: alphanumeric, 2 to 15 characters, and start with a letter'
        if len(self.arguments) < 2:
            if (not nicksub.exists(self.arguments[0])) or nicksub.Person(self.arguments[0]).minecraft == None:
                return '<minecraft_name> is required because no Minecraft UUID is known for this person yet'
        elif not re.match(minecraft.regexes.player, self.arguments[1]):
            return '<minecraft_name> is not a valid Minecraft nickname'
        if len(self.arguments) > 2 and not re.match('@?[A-Za-z0-9_]{1,15}$', self.arguments[2]):
            return '<twitter_username> is invalid, see https://support.twitter.com/articles/101299'
        return True
    
    def permission_level(self):
        return 4
    
    def run(self):
        minecraft_nick = self.arguments[1] if len(self.arguments) > 1 else nicksub.Person(self.arguments[0]).minecraft
        try:
            if len(self.arguments) == 3 and self.arguments[2] is not None and len(self.arguments[2]):
                screen_name = self.arguments[2][1:] if self.arguments[2].startswith('@') else self.arguments[2]
            else:
                screen_name = None
            minecraft.whitelist_add(self.arguments[0], minecraft_nick, people_file=core.config('paths').get('people'))
        except ValueError:
            self.warning('id ' + self.arguments[0] + ' already exists')
        else:
            self.reply(minecraft_nick + ' is now whitelisted')
            if screen_name is not None:
                core.set_twitter(nicksub.Person(self.arguments[0]), screen_name)
                self.reply('@' + core.config('twitter')['screen_name'] + ' is now following @' + screen_name)

def parse(command, sender, context, channel=None):
    # parameter parsing
    if isinstance(command, str):
        command = command.split(' ')
    args = command[1:]
    command = command[0]
    addressing = None
    match = re.match('([A-Za-z]+)@([^ ]+)$', command)
    if match:
        command = match.group(1)
        addressing = nicksub.person_or_dummy(match.group(2), context=context)
    command = command.lower()
    # check the aliases first
    aliases = core.config('aliases')
    if command in aliases:
        return AliasCommand(name=command, alias_dict=aliases[command], args=args, sender=sender, context=context, channel=channel, addressing=addressing)
    # no alias found, check commands
    for command_class in classes:
        if command_class.__name__.lower() == command:
            return command_class(args=args, sender=sender, context=context, channel=channel, addressing=addressing)
    else:
        raise ValueError('No such command')

def run(command_name, sender, context, channel=None, wait=False):
    """Runs a command.
    
    Required arguments:
    command_name -- either a string containing the command name and arguments, or an array where the first item is the command name and the rest are arguments
    sender -- a nicksub.Person or string representing the sender of the command. If it's a string, it will be converted into a nicksub.Dummy
    context -- a string, 'minecraft' or 'irc', depending on where the command was sent from
    
    Optional arguments:
    channel -- if sent from IRC, the channel to which the command was sent, or None (the default) if it was sent to query
    wait -- whether or not the function call should block until the command has finished executing. Defaults to False
    """
    try:
        command = parse(command=command_name, sender=sender, context=context, channel=channel)
    except ValueError:
        if isinstance(command_name, str):
            command_name = command_name.split(' ')
        command_name = command_name[0]
        BaseCommand(args=[], sender=sender, context=context, channel=channel).warning(core.ErrorMessage.unknown(command_name))
        return False
    core.debug_print('[command] ' + command.name + ' ' + ' '.join(command.arguments))
    parse_result = command.parse_args()
    if parse_result is False:
        command.warning('Usage: ' + command.name + ('' if command.usage is None else ' ' + command.usage))
        return False
    elif parse_result is not True:
        command.warning(str(parse_result))
        return False
    sender_permission_level = 0
    if isinstance(sender, nicksub.Person):
        sender_permission_level = 1
        if sender.id in core.config('ops'):
            sender_permission_level = 4
        elif sender.whitelisted():
            sender_permission_level = 3
        elif sender.invited():
            sender_permission_level = 2
    command_permission_level = command.permission_level()
    if sender_permission_level < command_permission_level:
        command.warning(core.ErrorMessage.permission(level=command_permission_level))
        return False
    if wait:
        command.run()
    else:
        command.start()
    return True

classes = [command_class for name, command_class in inspect.getmembers(sys.modules[__name__], inspect.isclass) if issubclass(command_class, BaseCommand) and name != 'AliasCommand']
