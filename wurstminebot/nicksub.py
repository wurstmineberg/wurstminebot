import sys

import json
import re

CONFIG_FILE = '/opt/wurstmineberg/config/people.json'

def config(person_id=None):
    try:
        with open(CONFIG_FILE) as config_file:
            j = json.load(config_file)
    except:
        j = []
    if isinstance(j, dict):
        j = j['people']
    if person_id is None:
        return j
    for person in j:
        if person.get('id') == person_id:
            return person
    else:
        raise PersonNotFoundError('person with id ' + str(person_id) + ' not found')

def set_config(config_dict):
    if not isinstance(config_dict, dict):
        config_dict = {'people': config_dict}
    with open(CONFIG_FILE, 'w') as config_file:
        json.dump(config_dict, config_file, sort_keys=True, indent=4, separators=(',', ': '))

def update_config(person_id, path, value=None, delete=False):
    config_dict = config()
    if isinstance(config_dict, dict):
        full_config_dict = config_dict
    else:
        full_config_dict = {'people': config_dict}
    for person_dict in full_config_dict['people']:
        if person_dict['id'] == person_id:
            break
    else:
        raise KeyError('person with id ' + str(person_id) + ' not found')
    person_index = index(person_id)
    if len(path) > 1:
        for key in path[:-1]:
            if not isinstance(person_dict, dict):
                raise KeyError('Trying to update a non-dict config key')
            if key not in person_dict:
                person_dict[key] = {}
            person_dict = person_dict[key]
    if len(path) > 0:
        if delete:
            del person_dict[path[-1]]
        else:
            person_dict[path[-1]] = value
    else:
        if delete:
            del full_config_dict['people'][person_index]
        else:
            full_config_dict['people'][person_index] = value
    set_config(full_config_dict)

class PersonNotFoundError(Exception):
    pass # raised when a Person object is created or reloaded with data not in the config

def ircNicks(mode='all', include_ids=False):
    for person in config():
        if 'irc' in person and 'nicks' in person['irc'] and len(person['irc']['nicks']):
            if mode == 'all':
                for nick in person['irc']['nicks']:
                    yield (person['id'], nick) if include_ids else nick
            elif mode == 'lists':
                yield (person['id'], person['irc']['nicks']) if include_ids else person['irc']['nicks']
            elif mode == 'main':
                yield (person['id'], person['irc']['nicks'][0]) if include_ids else person['irc']['nicks'][0]
            else:
                raise ValueError('unknown mode: ' + str(mode))

def minecraftNicks(include_ids=False):
    for person in config():
        if 'minecraft' in person:
            yield (person['id'], person['minecraft']) if include_ids else person['minecraft']

def otherNicks(mode='all', include_ids=False):
    for person in config():
        if 'nicks' in person and len(person['nicks']):
            if mode == 'all':
                for nick in person['nicks']:
                    yield (person['id'], nick) if include_ids else nick
            elif mode == 'lists':
                yield (person['id'], person['nicks']) if include_ids else person['nicks']
            else:
                raise ValueError('unknown mode: ' + str(mode))

def redditNicks(include_ids=False, format='plain'):
    def _formatRedditNick(nick):
        if format == 'plain':
            return nick
        elif format == 'prefix':
            return '/u/' + nick
        elif format == 'url_long':
            return 'https://www.reddit.com/user/' + nick
        elif format == 'url_short':
            return 'https://reddit.com/u/' + nick
        else:
            raise ValueError('unknown format: ' + str(format))
    
    for person in config():
        if 'reddit' in person:
            yield (person['id'], _formatRedditNick(person['reddit'])) if include_ids else _formatRedditNick(person['reddit'])

def twitterNicks(include_ids=False, twitter_at_prefix=False):
    for person in config():
        if 'twitter' in person:
            formatted_nick = ('@' + person['twitter']) if twitter_at_prefix else person['twitter']
            yield (person['id'], formatted_nick) if include_ids else formatted_nick

class BasePerson:
    def __eq__(self, other):
        try:
            return self.id == other.id
        except AttributeError:
            return False
    
    def display_name(self):
        return self.id if self.name is None else self.name
    
    def invited(self):
        return self.whitelisted() or self.status == 'invited'
    
    def irc_nick(self, respect_highlight_option=True, channel_members=[], fallback=True):
        """Returns the best IRC nick for the person. “Best” in this case means the first in the list.
        
        respect_highlight_option: if this is True and the person has the chatsync_highlight option on, a zero-width non-joiner will be inserted after the first character of the nick.
        channel_members: if this is not empty, nicks in this list will be preferred.
        fallback: this defines how an empty list of IRC nicks is handled. If it is True, the display name will be used. If it is False, an AttributeError will be raised. For other values, the fallback will be returned instead.
        """
        for nick in self.irc_nicks:
            if nick in channel_members:
                break
        else:
            if len(self.irc_nicks) > 0:
                nick = self.irc_nicks[0]
            elif fallback is True:
                return self.display_name()
            elif fallback is False:
                raise AttributeError('Person has no IRC nicks')
            else:
                return fallback
        if respect_highlight_option and not self.option('chatsync_highlight'):
            return nick[0] + '\u200c' + nick[1:]
        return nick
    
    def nick(self, context, default=True, twitter_at_prefix=False):
        if default is True:
            default = self.display_name()
        if context == 'irc':
            return self.irc_nicks[0] if self.irc_nicks is not None and len(self.irc_nicks) else default
        elif context == 'minecraft':
            return default if self.minecraft is None else self.minecraft
        elif context == 'reddit':
            return default if self.reddit is None else self.reddit
        elif context == 'twitter':
            return default if self.twitter is None else (('@' + self.twitter) if twitter_at_prefix else self.twitter)
        else:
            return default
    
    def option(self, option_name):
        default_true_options = ['chatsync_highlight'] # These options are on by default. All other options are off by default.
        if str(option_name) in self.options:
            return self.options[str(option_name)]
        else:
            return str(option_name) in default_true_options
    
    def option_is_default(self, option_name):
        return str(option_name) not in self.options
    
    def set_option(self, option_name, value):
        opts = self.options
        opts[option_name] = value
        self.options = opts
    
    def whitelisted(self):
        return self.status in ['founding', 'later', 'postfreeze']

class Person(BasePerson):
    def __init__(self, id_or_nick, context=None, strict=True):
        if id_or_nick is None:
            raise TypeError('id or nick may not be None')
        if context is None:
            self.id = id_or_nick
            config(self.id) # raises PersonNotFoundError if the id is invalid
        elif context == 'irc':
            for id, irc_nick in ircNicks(mode='all', include_ids=True):
                if irc_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError('person with IRC nick ' + str(id_or_nick) + ' not found')
        elif context == 'minecraft':
            for id, minecraft_nick in minecraftNicks(include_ids=True):
                if minecraft_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError()
        elif context == 'reddit':
            for id, reddit_nick in redditNicks(include_ids=True, format='plain'):
                if id_or_nick.startswith('/u/'):
                    id_or_nick = id_or_nick[len('/u/'):]
                if reddit_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError('person with reddit nick ' + str(id_or_nick) + ' not found')
        elif context == 'twitter':
            for id, twitter_nick in twitterNicks(include_ids=True, twitter_at_prefix=False):
                if id_or_nick.startswith('@'):
                    id_or_nick = id_or_nick[len('@'):]
                if twitter_nick.lower() == id_or_nick.lower():
                    self.id = id
                    break
            else:
                raise PersonNotFoundError('person with twitter nick ' + str(id_or_nick) + ' not found')
        else:
            raise ValueError('unknown context: ' + str(context))
    
    @property
    def description(self):
        return config(self.id).get('description')
    
    @description.setter
    def description(self, value):
        update_config(self.id, ['description'], value=value)
    
    @description.deleter
    def description(self):
        update_config(self.id, ['description'], delete=True)
    
    @property
    def irc_nicks(self):
        return config(self.id).get('irc', {}).get('nicks', [])
    
    @irc_nicks.setter
    def irc_nicks(self, value):
        update_config(self.id, ['irc', 'nicks'], value=value)
    
    @irc_nicks.deleter
    def irc_nicks(self):
        update_config(self.id, ['irc', 'nicks'], delete=True)
    
    @property
    def minecraft(self):
        return config(self.id).get('minecraft')
    
    @minecraft.setter
    def minecraft(self, value):
        update_config(self.id, ['minecraft'], value=value)
    
    @minecraft.deleter
    def minecraft(self):
        update_config(self.id, ['minecraft'], delete=True)
    
    @property
    def name(self):
        return config(self.id).get('name')
    
    @name.setter
    def name(self, value):
        update_config(self.id, ['name'], value=value)
    
    @name.deleter
    def name(self):
        update_config(self.id, ['name'], delete=True)
    
    @property
    def nicks(self):
        return config(self.id).get('nicks', [])
    
    @nicks.setter
    def nicks(self, value):
        update_config(self.id, ['nicks'], value=value)
    
    @nicks.deleter
    def nicks(self):
        update_config(self.id, ['nicks'], delete=True)
    
    @property
    def nickserv(self):
        return config(self.id).get('irc', {}).get('nickserv')
    
    @nickserv.setter
    def nickserv(self, value):
        update_config(self.id, ['irc', 'nickserv'], value=value)
    
    @nickserv.deleter
    def nickserv(self):
        update_config(self.id, ['irc', 'nickserv'], delete=True)
    
    @property
    def options(self):
        return config(self.id).get('options', {})
    
    @options.setter
    def options(self, value):
        update_config(self.id, ['options'], value=value)
    
    @options.deleter
    def options(self):
        update_config(self.id, ['options'], delete=True)
    
    @property
    def reddit(self):
        return config(self.id).get('reddit')
    
    @reddit.setter
    def reddit(self, value):
        update_config(self.id, ['reddit'], value=value)
    
    @reddit.deleter
    def reddit(self):
        update_config(self.id, ['reddit'], delete=True)
    
    @property
    def status(self):
        return config(self.id).get('status', 'later')
    
    @status.setter
    def status(self, value):
        if value == 'later':
            del self.status
        else:
            update_config(self.id, ['status'], value=value)
    
    @status.deleter
    def status(self):
        update_config(self.id, ['status'], delete=True)
    
    @property
    def twitter(self):
        return config(self.id).get('twitter')
    
    @twitter.setter
    def twitter(self, value):
        update_config(self.id, ['twitter'], value=value)
    
    @twitter.deleter
    def twitter(self):
        update_config(self.id, ['twitter'], delete=True)
    
    @property
    def website(self):
        return config(self.id).get('website')
    
    @website.setter
    def website(self, value):
        update_config(self.id, ['website'], value=value)
    
    @website.deleter
    def website(self):
        update_config(self.id, ['website'], delete=True)
    
    @property
    def wiki(self):
        return config(self.id).get('wiki')
    
    @wiki.setter
    def wiki(self, value):
        update_config(self.id, ['wiki'], value=value)
    
    @wiki.deleter
    def wiki(self):
        update_config(self.id, ['wiki'], delete=True)

class Dummy(BasePerson):
    def __init__(self, id_or_nick, context=None):
        if id_or_nick is None:
            raise TypeError('id or nick may not be None')
        self.id_or_nick = id_or_nick
        self.context = context
        self.description = None
        self.id_or_nick = id_or_nick
        self.irc_nicks = []
        self.minecraft = None
        self.name = None
        self.nicks = None
        self.nickserv = None
        self.options = {}
        self.reddit = None
        self.status = 'unknown'
        self.twitter = None
        self.website = None
        self.wiki = None
        if context == 'irc':
            self.irc_nicks = [id_or_nick]
        elif context == 'minecraft':
            self.minecraft = id_or_nick
        elif context == 'reddit':
            if id_or_nick.startswith('/u/'):
                id_or_nick = id_or_nick[len('/u/'):]
            self.reddit = id_or_nick
        elif context == 'twitter':
            if id_or_nick.startswith('@'):
                id_or_nick = id_or_nick[len('@'):]
            self.twitter = id_or_nick
    
    def display_name(self):
        return self.id_or_nick
    
    def nick(self, context, default=True, twitter_at_prefix=False):
        return super().nick(context, default=default, twitter_at_prefix=False)

def everyone():
    for person in config():
        if id in person:
            yield Person(person['id'])

def index(person, default=False):
    if isinstance(person, Person):
        person_id = person.id
    elif isinstance(person, str):
        person_id = person
    elif default is False:
        raise TypeError('cannot get index of non-person object')
    else:
        return default
    for i, person_dict in enumerate(config()):
        if person_dict.get('id') == person_id:
            return i
    raise PersonNotFoundError('person with id ' + str(person_id) + ' not found')

def person_or_dummy(id_or_nick, context=None):
    try:
        return Person(id_or_nick, context=context)
    except PersonNotFoundError:
        return Dummy(id_or_nick, context=context)

def sorted_people(*args, context=None):
    """Returns a list of Person and Dummy objects based on the Person/Dummy objects and ids or (if context is specified) nicknames provided.
    """
    people = []
    dummies = []
    if len(args) == 1 and not isinstance(args[0], str):
        try:
            (_ for _ in args[0])
        except:
            pass # argument is not iterable
        else:
            args = args[0]
    for person_or_id in args:
        if not isinstance(person_or_id, BasePerson):
            person_or_id = person_or_dummy(person_or_id, context=context)
        if isinstance(person_or_id, Person):
            people.append(person_or_id)
        else:
            dummies.append(person_or_id)
    return sorted(people, key=index) + sorted(dummies, key=(lambda d: d.id_or_nick))

def sub(nick, source, target, strict=True, exit_on_fail=False, twitter_at_prefix=True):
    if exit_on_fail:
        if nick is None:
            sys.exit(1)
        try:
            ret = Person(nick, source).nick(target, twitter_at_prefix=twitter_at_prefix)
            if ret is None:
                sys.exit(2)
            else:
                return ret
        except PersonNotFoundError:
            sys.exit(1)
    else:
        if nick is None:
            return None
        try:
            return Person(nick, source).nick(target, nick, twitter_at_prefix=twitter_at_prefix)
        except PersonNotFoundError:
            return nick

def textsub(text, source, target, strict=False):
    def _nicksForContext(context):
        if context == 'irc':
            mode = 'main' if strict else 'all'
            return reversed(list(ircNicks(include_ids=True, mode=mode)))
        elif context == 'minecraft':
            return minecraftNicks(include_ids=True)
        elif context == 'reddit':
            return redditNicks(include_ids=True)
        elif context == 'twitter':
            return twitterNicks(include_ids=True, twitter_at_prefix=True)
        else:
            return []
    
    text = text[:]
    for id, nick in _nicksForContext(source):
        if Person(id).nick(target):
            text = re.sub('(?<![0-9A-Za-z@])(' + re.sub('\\|', '\\|', nick) + ')(?![0-9A-Za-z])', Person(id).nick(target, twitter_at_prefix=True), text, flags=re.IGNORECASE)
    if not strict:
        for id, nick in otherNicks(include_ids=True, mode='all'):
            if Person(id).nick(target):
                text = re.sub('(?<![0-9A-Za-z@])(' + re.sub('\\|', '\\|', nick) + ')(?![0-9A-Za-z])', Person(id).nick(target, twitter_at_prefix=True), text, flags=re.IGNORECASE)
    return text
