import datetime
import minecraft
from wurstminebot import nicksub
import re

messages = [
    {
        'id': 'anvil',
        'regex': 'was squashed by a falling anvil'
    },
    {
        'id': 'cactus',
        'regex': 'was pricked to death'
    },
    {
        'id': 'cactus-escape',
        'regex': 'walked into a cactus whilst trying to escape (.+)'
    },
    {
        'id': 'arrow',
        'regex': 'was shot by arrow'
    },
    {
        'id': 'drowned',
        'regex': 'drowned'
    },
    {
        'id': 'drowned-escape',
        'regex': 'drowned whilst trying to escape (.+)'
    },
    {
        'id': 'explosion',
        'regex': 'blew up'
    },
    {
        'id': 'explosion-creeper',
        'regex': 'was blown up by Creeper'
    },
    {
        'id': 'explosion-by',
        'regex': 'was blown up by (.+)'
    },
    {
        'id': 'hitground',
        'regex': 'hit the ground too hard'
    },
    {
        'id': 'high-void',
        'regex': 'fell from a high place and fell out of the world'
    },
    {
        'id': 'high-finished-player',
        'regex': 'fell from a high place and got finished off by (' + minecraft.regexes.player + ')'
    },
    {
        'id': 'high',
        'regex': 'fell from a high place'
    },
    {
        'id': 'high-ladder',
        'regex': 'fell off a ladder'
    },
    {
        'id': 'high-vines',
        'regex': 'fell off some vines'
    },
    {
        'id': 'high-water',
        'regex': 'fell out of the water'
    },
    {
        'id': 'hitground-fire',
        'regex': 'fell into a patch of fire'
    },
    {
        'id': 'hitground-cactus',
        'regex': 'fell into a patch of cacti'
    },
    {
        'id': 'doomedtofall',
        'regex': 'was doomed to fall'
    },
    {
        'id': 'doomedtofall-player-using',
        'regex': 'was doomed to fall by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'doomedtofall-by',
        'regex': 'was doomed to fall by (.+)'
    },
    {
        'id': 'arrow-high-vines',
        'regex': 'was shot off some vines by (.+)'
    },
    {
        'id': 'arrow-high-ladder',
        'regex': 'was shot off a ladder by (.+)'
    },
    {
        'id': 'explosion-high',
        'regex': 'was blown from a high place by (.+)'
    },
    {
        'id': 'fire',
        'regex': 'went up in flames'
    },
    {
        'id': 'burn',
        'regex': 'burned to death'
    },
    {
        'id': 'burn-by',
        'regex': 'was burnt to a crisp whilst fighting (.+)'
    },
    {
        'id': 'fire-by',
        'regex': 'walked into a fire whilst fighting (.+)'
    },
    {
        'id': 'slain-player-using',
        'regex': 'was slain by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'slain-using',
        'regex': 'was slain by (.+) using \\[(.+)\\]'
    },
    {
        'id': 'slain-silverfish',
        'regex': 'was slain by Silverfish'
    },
    {
        'id': 'slain-zombie',
        'regex': 'was slain by Zombie'
    },
    {
        'id': 'slain',
        'regex': 'was slain by (.+)'
    },
    {
        'id': 'shot-player-using',
        'regex': 'was shot by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'shot-player',
        'regex': 'was shot by (' + minecraft.regexes.player + ')'
    },
    {
        'id': 'shot',
        'regex': 'was shot by (.+)'
    },
    {
        'id': 'fireball',
        'regex': 'was fireballed by (.+)'
    },
    {
        'id': 'lava-by',
        'regex': 'tried to swim in lava while trying to escape (.+)'
    },
    {
        'id': 'lava',
        'regex': 'tried to swim in lava'
    },
    {
        'id': 'generic',
        'regex': 'died'
    },
    {
        'id': 'finished-player-using',
        'regex': 'got finished off by (' + minecraft.regexes.player + ') using \\[(.+)\\]'
    },
    {
        'id': 'finished-using',
        'regex': 'got finished off by (.+) using \\[(.+)\\]'
    },
    {
        'id': 'magic-player',
        'regex': 'was killed by (' + minecraft.regexes.player + ') using magic'
    },
    {
        'id': 'magic-by',
        'regex': 'was killed by (.+) using magic'
    },
    {
        'id': 'magic',
        'regex': 'was killed by magic'
    },
    {
        'id': 'starved',
        'regex': 'starved to death'
    },
    {
        'id': 'wall',
        'regex': 'suffocated in a wall'
    },
    {
        'id': 'generic-by',
        'regex': 'was killed while trying to hurt (.+)'
    },
    {
        'id': 'pummeled-by',
        'regex': 'was pummeled by (.+)'
    },
    {
        'id': 'void',
        'regex': 'fell out of the world'
    },
    {
        'id': 'void-by',
        'regex': 'was knocked into the void by (.+)'
    },
    {
        'id': 'wither',
        'regex': 'withered away'
    }
] # http://minecraft.gamepedia.com/Server#Death_messages

class Death:
    def __init__(self, log_line):
        for death in messages:
            match = re.match('(' + minecraft.regexes.timestamp + ') \\[Server thread/INFO\\]: (' + minecraft.regexes.player + ') ' + death['regex'] + '$', log_line)
            if not match:
                continue
            # death
            self.id = death['id']
            self.timestamp = minecraft.regexes.strptime(datetime.date.today(), match.group(1))
            self.person = nicksub.person_or_dummy(match.group(2), context='minecraft')
            self.partial_message = log_line[len('[00:00:00] [Server thread/INFO]: ' + self.person.nick('minecraft') + ' '):]
            self.groups = match.groups()[2:]
            break
        else:
            raise ValueError('Log line is not a death')
    
    def irc_message(self, tweet_info=None):
        victim_irc = self.person.irc_nick()
        return victim_irc + ' ' + nicksub.textsub(self.partial_message, 'minecraft', 'irc', strict=True) + ('' if tweet_info is None else ' [' + str(tweet_info) + ']')
    
    def message(self):
        return (self.person.nick('minecraft')) + ' ' + self.partial_message
    
    def tweet(self, comment=None):
        victim_twitter = self.person.nick('twitter', twitter_at_prefix=True)
        status = '[DEATH] ' + victim_twitter + ' ' + nicksub.textsub(self.partial_message, 'minecraft', 'twitter', strict=True)
        if comment is not None and len(status + ' … ' + comment) <= 140:
            status += ' … ' + comment
        return status
