# http://www.minecraftwiki.net/wiki/Server#Death_messages

import minecraft
import re

regexes = [
    'was squashed by a falling anvil',
    'was pricked to death',
    'walked into a cactus whilst trying to escape (.+)', 
    'was shot by arrow',
    'drowned',
    'drowned whilst trying to escape (.+)',
    'blew up',
    'was blown up by Creeper',
    'was blown up by (.+)',
    'hit the ground too hard',
    'fell from a high place and fell out of the world',
    'fell from a high place',
    'fell off a ladder',
    'fell off some vines',
    'fell out of the water',
    'fell into a patch of fire',
    'fell into a patch of cacti',
    'was doomed to fall',
    'was doomed to fall by (' + minecraft.regexes.player + ') using \\[(.+)\\]',
    'was doomed to fall by (.+)',
    'was shot off some vines by (.+)',
    'was shot off a ladder by (.+)',
    'was blown from a high place by (.+)',
    'went up in flames',
    'burned to death',
    'was burnt to a crisp whilst fighting (.+)',
    'walked into a fire whilst fighting (.+)',
    'was slain by (' + minecraft.regexes.player + ') using \\[(.+)\\]',
    'was slain by (.+) using \\[(.+)\\]',
    'was slain by Zombie',
    'was slain by (.+)',
    'was shot by (' + minecraft.regexes.player + ') using \\[(.+)\\]',
    'was shot by (' + minecraft.regexes.player + ')',
    'was shot by (.+)',
    'was fireballed by (.+)',
    'tried to swim in lava while trying to escape (.+)',
    'tried to swim in lava',
    'died',
    'got finished off by (' + minecraft.regexes.player + ') using \\[(.+)\\]',
    'got finished off by (.+) using \\[(.+)\\]',
    'was killed by (' + minecraft.regexes.player + ') using magic',
    'was killed by (.+) using magic',
    'was killed by magic',
    'starved to death',
    'suffocated in a wall',
    'was killed while trying to hurt (.+)',
    'was pummeled by (.+)',
    'fell out of the world',
    'was knocked into the void by (.+)',
    'withered away'
]

def partial_message(id, groups=()):
    ret = regexes[id]
    for group in groups:
        ret = re.sub('\\(.+?\\)', group, ret, count=1)
    return ret
