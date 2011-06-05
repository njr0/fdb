# flags.py
#
# Copyright (c) Nicholas J. Radcliffe 2009.
# Licence terms in LICENCE.

import sys
class FlagError (Exception):                    pass

def Plural(n, s, pl=None, str=False, justTheWord=False):
    """Returns a string like '23 fields' or '1 field' where the
        number is n, the stem is s and the plural is either stem + 's'
        or stem + pl (if provided)."""
    smallints = ['zero', 'one', 'two', 'three', 'four', 'five',
                         'six', 'seven', 'eight', 'nine', 'ten']

    isUnicode = type(s) == unicode
    if isUnicode:
        s = s.encode('UTF-8')
    if pl == None:
        pl = 's'
    if str and n < 10 and n >= 0:
        strNum = smallints[n]
    else:
        strNum = int(n)
    if n == 1:
        if justTheWord:
            result = s
        else:
            result ='%s %s' % (strNum, s)
    else:
        if justTheWord:
            result = '%s%s' % (s, pl)
        else:
            result = '%s %s%s' % (strNum, s, pl)
    return result.decode('UTF-8') if isUnicode else result

class Flags:
    def __init__ (self, args, groupable=None, argless=None,
                        argful=None, argNames = None, plusMinus=None,
                        helpString=None, help=False):
        """General option and argument handling for unix-style command lines.
        Supports
            grouped options:   command -abc arg1 arg2
            single options:    command -one -two -3 arg1 arg2
            options with args: command -a argA -b argB -c argC arg1 arg2
            +/- boolean options command -a +b -c +d

        args is a list of args, with arg[0] being taken to be the command.
        (If there is no arg[0], self.command is None; otherwise, it is set
         to the command name.)

        groupable is a hash mapping single letters to keys { 'a' : 'apple' }

        argless   is a hash mapping single options to keys {'one' : 'one'} etc.

        argful    is a hash mapping options to keys: {'one', 'one'}

        plusMinus is a hash whose keys are flags that are set to True
                     by +key and to False by -key; hash values give defaults.

        argNames  is a list of parameter names.   If provided, class variables
                  flag.paramName etc. will be set to the values given and
                  an error will be raised if more non-flag parameters are given
                  than are named.

        helpString is the help string, which is assigned to self.help
                   if any of -h, -help, --help or -? is issued.
                   If helpString is blank, some crappy automatic help
                        is generated.
                   May change to support hash with help for each flag/arg.

        help    If set to anything that evaluates as False help is written
                to self.help but no action is taken.

                If set to True or 'exit', help is printed followed by
                sys.exit (0).

                If set to 'print', help is printed but no call to exit follows.

        On return:
           Any non-flag args are in self.args and their number is in self.nArgs
           If argNames was provided, class parameters are set too.
           Class variables are set for each flag given.
        """
        helpFlags = ['-h', '-help', '--help', '-?']
        if help:
            assert help in (True, 'exit', 'print')
        self.groupable = groupable or {}
        self.argless = argless or {}
        self.argful = argful or {}
        self.plusMinus = plusMinus or {}
        self.argNames = argNames or []
        self.nonArgVals = self.groupable.values () + self.argless.values ()
        self.nonArgKeys = self.groupable.keys () + self.argless.keys ()
        self.nonArgKeys.sort ()
        N = len (args)
        d = self.__dict__
        for flag in self.nonArgVals:
            d[flag] = False
        for flag in self.argful.values ():
            d[flag] = None
        for flag in self.plusMinus.keys ():
            assert self.plusMinus[flag] in (True, False, None)
            d[flag] = self.plusMinus[flag]
        for a in self.argNames:
            d[a] = None
        self.args = []
        self.help = False
        self.command = None
        if args == []:
            return
        self.command = args[0]
        nfi = 0     # index for (non-flag) args

        self.badFlags = []
        self.extras = []
        self.arglessArgful = None
        allFlagsSoFar = True
        i = 1
        while i < len (args):
            a = args[i]
            if a in helpFlags:
                if helpString:
                    self.help = helpString
                else:
                    self.help = self.GenerateHelp ()
                if help:
                    print self.help
                    sys.exit (0)
            elif allFlagsSoFar:
                if a.startswith ('-') or self.plusMinus and a.startswith ('+'):
                    flagName = a[1:]
                    isArgless = [c in self.groupable for c in flagName]
                    if sum (isArgless) == len (a) - 1:  # all single letters
                        for flag in flagName:
                            d[self.groupable[flag]] = True
                    elif flagName in self.argless.keys ():
                        d[argless[flagName]] = True
                    elif flagName in self.argful.keys ():
                        if i+1 < N:
                            i += 1
                            d[argful[flagName]] = args[i]
                        else:
                            self.arglessArgful = a
                    elif flagName in self.plusMinus.keys ():
                        d[flagName] = (a[0] == '+')
                    else:
                        self.badFlags.append (a)
                else:
                    allFlagsSoFar = False
                    self.firstNonFlag = i

            if not allFlagsSoFar:
                self.args.append (a)
                if self.argNames:
                    if len (self.argNames) > nfi:
                        d[self.argNames[nfi]] = a
                        nfi += 1
                    else:
                        self.extras.append (a)
            i += 1
        self.nArgs = len (self.args)

        if self.badFlags:
            raise FlagError, ('I didn\'t recognize the %s %s.'
                        % (Plural (len (self.badFlags), 'flag', 's', 
                           justTheWord=True), ', '.join (self.badFlags)))
        if self.arglessArgful:
            raise FlagError, ('Flag %s requires argument' % self.arglessArgful)
        if self.extras:
            raise FlagError, ('Extra %s on line: %s'
                   % (Plural (len (self.extras), 'parameter'),
                      ', '.join (self.extras)))

    def GetArg (self, key, default=None, complainIfMissing=False):
        v = self.__dict__[key]
        if v == None:
            if complainIfMissing:
                raise FlagError, ('Flag %s is required and must be followed by'
                        ' an integer' % key)
            else:
                return default
        return v

    def GetIntArg (self, key, default=None, complainIfMissing=False):
        s = self.GetArg (key, None, complainIfMissing)
        if s == None:
            v = default
        else:
            try:
                v = int (s)
            except:
                raise FlagError, ('Flag %s must be followed by an integer, not'
                        ' %s' % (key, s))
        return v

    def GenerateHelp (self):
        s = ['Command %s' % self.command, '    Flags supported are:']
        for flag in self.nonArgKeys:
            s.append ('        -%s' % flag)
        argKeys = self.argful.keys ()
        argKeys.sort ()
        for flag in self.argful.keys ():
            s.append ('        -%s value' % flag)
        for flag in self.plusMinus.keys ():
            s.append ('        +%s or -%s' % (flag, flag))

        return '\n'.join (s)

    def __str__ (self):
        keys = self.__dict__.keys ()
        ignore = ('groupable', 'argful', 'help', 'badFlags',
                  'argless', 'plusMinus', 'argNames', 'arglessArgful',
                  'nonArgKeys', 'nonArgVals')
        keys.sort ()
        return '\n'.join (['    %-20s: %s' % (str (k), str (self.__dict__[k]))
                                for k in keys if not k in ignore])




