#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# fdb.py
#
#
# Copyright (c) Nicholas J. Radcliffe 2009-2011 and other authors specified
#               in the AUTHOR
# Licence terms in LICENCE.
#
# Notes:
#
#       Credentials (username and password) are normally read from
#       a plain text credentials file, or can be passed in explicitly.
#       The code assumes ~/.fluidDBcredentials on unix and
#       fluidDBcredentials.ini in the user's home folder on Windows.
#       The format is plain text with the username on the first line
#       and the password on the second, no whitespace.
#       Any further lines are ignored.
#
# Conventions in this code:
#
# The full path to a tag might be
#
#       http://fluidDB.fluidinfo.com/tags/njr/var/rating
#
# We call
#
# http://fluidDB.fluidinfo.com/tags/njr/var/rating --- the tag URI
# /tags/njr/var/rating                             --- the full tag path
# /njr/var/rating                                  --- the absolute tag path
# /njr/var                                         --- the absolute namespace
# var/rating                                       --- the relative tag path
# rating                                           --- the short tag name
#

from testfdb import *

sys.stdout = UnicodeOut(sys.stdout)
sys.stderr = UnicodeOut(sys.stderr)

def go():
    action, args, options, parser = parse_args()

    if action.startswith('test'):
        cases = {
            'testcli': TestCLI,
            'testdb': TestFluidDB,
            'testutil': TestFDBUtilityFunctions,
        }
        try:
            cases = {action: cases[action]}
        except KeyError:
            pass
        suite = unittest.TestSuite()
        for c in cases.values():
            s = unittest.TestLoader().loadTestsFromTestCase(c)
            suite.addTest(s)
        v = 2 if options.hightestverbosity else 1
        unittest.TextTestRunner(verbosity=v).run(suite)
    else:
        execute_command_line(action, args, options, parser)

if __name__ == '__main__':
    go()
