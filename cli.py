# -*- coding: utf-8 -*-
#
# cli.py
#
# Copyright (c) Nicholas J. Radcliffe 2009-2011 and other authors specified
#               in the AUTHOR
# Licence terms in LICENCE.

import shutil
import sys
import types
from optparse import OptionParser, OptionGroup
from itertools import chain, imap
from fdblib import (
    FluidDB,
    O,
    Credentials,
    get_credentials_file,
    get_typed_tag_value,
    path_style,
    toStr,
    uprint,
    version,
    DEFAULT_ENCODING,
    STATUS,
    DADGAD_ID,
    HTTP_TIMEOUT,
    SANDBOX_PATH,
    FLUIDDB_PATH,
)
import ls
import flags


HTTP_METHODS = ['GET', 'PUT', 'POST', 'DELETE', 'HEAD']

ARGLESS_COMMANDS = ['COUNT', 'TAGS', 'LS', 'PWD', 'PWN', 'WHOAMI']

USAGE = u"""

 Tag objects:
   fdb tag -a 'DADGAD' tuning rating=10
   fdb tag -i %s /njr/tuning /njr/rating=10
   fdb tag -q 'about = "DADGAD"' tuning rating=10

 Untag objects:
   fdb untag -a 'DADGAD' /njr/tuning rating
   fdb untag -i %s
   fdb untag -q 'about = "DADGAD"' tuning rating

 Fetch objects and show tags
   fdb show -a 'DADGAD' /njr/tuning /njr/rating
   fdb show -i %s tuning rating
   fdb show -q 'about = "DADGAD"' tuning rating

 Count objects matching query:
   fdb count -q 'has fluiddb/users/username'

 Get tags on objects and their values:
   fdb tags -a 'DADGAD'
   fdb tags -i %s

 Miscellaneous:
   fdb whoami              prints username for authenticated user
   fdb pwd / fdb pwn       prints root namespace of authenticated user
   fdb su fdbuser          set fdb to use user credentials for fdbuser

 Run Tests:
   fdb test                runs all tests
   fdb testcli             tests command line interface only
   fdb testdb              tests core FluidDB interface only
   fdb testutil            runs tests not requiring FluidDB access

 Raw HTTP GET:
   fdb get /tags/njr/google
   fdb get /permissions/tags/njr/rating action=delete
   (use POST/PUT/DELETE/HEAD at your peril; currently untested.)

""" % (DADGAD_ID, DADGAD_ID, DADGAD_ID, DADGAD_ID)


USAGE_FI = u"""

 Tag objects:
   fdb tag -a 'DADGAD' njr/tuning njr/rating=10
   fdb tag -i %s njr/tuning njr/rating=10
   fdb tag -q 'about = "DADGAD"' tuning njr/rating=10

 Untag objects:
   fdb untag -a 'DADGAD' njr/tuning njr/rating
   fdb untag -i %s
   fdb untag -q 'about = "DADGAD"' njr/tuning njr/rating

 Fetch objects and show tags
   fdb show -a 'DADGAD' njr/tuning njr/rating
   fdb show -i %s njr/tuning njr/rating
   fdb show -q 'about = "DADGAD"' njr/tuning njr/rating

 Count objects matching query:
   fdb count -q 'has fluiddb/users/username'

 Get tags on objects and their values:
   fdb tags -a 'DADGAD'
   fdb tags -i %s

 Miscellaneous:
   fdb whoami              prints username for authenticated user
   fdb pwd / fdb pwn       prints root namespace of authenticated user
   fdb su fdbuser          set fdb to use user credentials for fdbuser

 Run Tests:
   fdb test            (runs all tests)
   fdb testcli         (tests command line interface only)
   fdb testdb          (tests core FluidDB interface only)
   fdb testutil        (runs tests not requiring FluidDB access)

 Raw HTTP GET:
   fdb get /tags/njr/google
   fdb get /permissions/tags/njr/rating action=delete
   (use POST/PUT/DELETE/HEAD at your peril; currently untested.)

""" % (DADGAD_ID, DADGAD_ID, DADGAD_ID, DADGAD_ID)


class ModeError(Exception):
    pass


class TooFewArgsForHTTPError(Exception):
    pass


class UnrecognizedHTTPMethodError(Exception):
    pass


class TagValue:
    def __init__(self, name, value=None):
        self.name = name
        self.value = value

    def __unicode__(self):
        return (u'Tag "%s", value "%s" of type %s'
                     % (self.name, toStr(self.value), toStr(type(self.value))))


def error_code(n):
    code = STATUS.__dict__
    for key in code:
        if n == code[key]:
            return unicode('%d (%s)' % (n, key.replace('_', ' ')))
    return unicode(n)


def execute_tag_command(objs, db, tags, options):
    tags = form_tag_value_pairs(tags)
    actions = {
        u'id': db.tag_object_by_id,
        u'about': db.tag_object_by_about,
    }
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        for tag in tags:
            o = actions[obj.mode](obj.specifier, tag.name, tag.value,
                                  inPref=True)
            if o == 0:
                if options.verbose:
                    print(u'Tagged object %s with %s'
                            % (description,
                               formatted_tag_value(tag.name, tag.value)))
            else:
                warning(u'Failed to tag object %s with %s'
                        % (description, tag.name))
                warning(u'Error code %s' % error_code(o))


def execute_untag_command(objs, db, tags, options):
    actions = {
        'id': db.untag_object_by_id,
        'about': db.untag_object_by_about,
    }
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        for tag in tags:
            o = actions[obj.mode](obj.specifier, tag, inPref=True)
            if o == 0:
                if options.verbose:
                    print('Removed tag %s from object %s\n'
                          % (tag, description))
            else:
                warning(u'Failed to remove tag %s from object %s'
                        % (tag, description))
                warning(u'Error code %s' % error_code(o))


def execute_show_command(objs, db, tags, options):
    actions = {
        u'id': db.get_tag_value_by_id,
        u'about': db.get_tag_value_by_about,
    }
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        print u'Object %s:' % description

        for tag in tags:
            fulltag = db.abs_tag_path(tag, inPref=True)
            outtag = db.abs_tag_path(tag, inPref=True, outPref=True)
            if tag == u'/id':
                if obj.mode == u'about':
                    o = db.query(u'fluiddb/about = "%s"' % obj.specifier)
                    if type(o) == types.IntType:  # error
                        status, v = o, None
                    else:
                        status, v = STATUS.OK, o[0]
                else:
                    status, v = STATUS.OK, obj.specifier
            else:
                status, v = actions[obj.mode](obj.specifier, tag, inPref=True)

            if status == STATUS.OK:
                print u'  %s' % formatted_tag_value(outtag, v)
            elif status == STATUS.NOT_FOUND:
                print u'  %s' % cli_bracket(u'tag %s not present' % outtag)
            else:
                print cli_bracket(u'error code %s getting tag %s'
                                  % (error_code(status), outtag))


def execute_tags_command(objs, db, options):
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        print u'Object %s:' % description
        id = (db.create_object(obj.specifier).id if obj.mode == u'about'
              else obj.specifier)
        for tag in db.get_object_tags_by_id(id):
            fulltag = u'/%s' % tag
            outtag = u'/%s' % tag if db.unixStyle else tag
            status, v = db.get_tag_value_by_id(id, fulltag)

            if status == STATUS.OK:
                print u'  %s' % formatted_tag_value(outtag, v)
            elif status == STATUS.NOT_FOUND:
                print u'  %s' % cli_bracket(u'tag %s not present' % outtag)
            else:
                print cli_bracket(u'error code %s getting tag %s'
                                  % (error_code(status), uttag))


def execute_whoami_command(db):
    print db.credentials.username


def execute_su_command(db, args):
    source =  get_credentials_file(username=args[0])
    dest = get_credentials_file()
    shutil.copyfile(source, dest)
    db = FluidDB(Credentials(filename=dest))
    username = db.credentials.username
    file = args[0].decode(DEFAULT_ENCODING)
    extra = u'' if args[0] == username else (u' (file %s)' % file)
    print u'Credentials set to user %s%s.' % (username, extra)


def execute_http_request(action, args, db, options):
    """Executes a raw HTTP command (GET, PUT, POST, DELETE or HEAD)
       as specified on the command line."""
    method = action.upper()
    if method not in HTTP_METHODS:
        raise UnrecognizedHTTPMethodError(u'Only supported HTTP methods are'
                u'%s and %s' % (' '.join(HTTP_METHODS[:-1], HTTP_METHODS[-1])))

    if len(args) == 0:
        raise TooFewArgsForHTTPError(u'HTTP command %s requires a URI'
                                     % method)
    uri = args[0]
    tags = form_tag_value_pairs(args[1:])
    if method == u'PUT':
        body = {tags[0].tag: tags[0].value}
        tags = tags[1:]
    else:
        body = None
    hash = {}
    for pair in tags:
        hash[pair.name] = pair.value
    status, result = db.call(method, uri, body, hash)
    print u'Status: %d' % status
    print u'Result: %s' % toStr(result)


def describe_by_mode(specifier, mode):
    """mode can be a string (about, id or query) or a flags object
        with flags.about, flags.query and flags.id"""
    if mode == u'about':
        return describe_by_about(specifier)
    elif mode == u'id':
        return describe_by_id(specifier)
    elif mode == u'query':
        return describe_by_id(specifier)
    raise ModeError(u'Bad Mode')


def describe_by_about(specifier):
    return u'with about="%s"' % specifier


def describe_by_id(specifier):
    return specifier


def formatted_tag_value(tag, value):
    if value == None:
        return tag
    elif type(value) in types.StringTypes:
        return u'%s = "%s"' % (tag, value)
    else:
        return u'%s = %s' % (tag, toStr(value))


def form_tag_value_pairs(tags):
    pairs = []
    for tag in tags:
        eqPos = tag.find('=')
        if eqPos == -1:
            pairs.append(TagValue(tag, None))
        else:
            t = tag[:eqPos]
            v = get_typed_tag_value(tag[eqPos + 1:])
            pairs.append(TagValue(t, v))
    return pairs


def warning(msg):
    sys.stderr.write(u'%s\n' % msg)


def fail(msg):
    warning(msg)
    sys.exit(1)


def nothing_to_do():
    print u'Nothing to do.'
    sys.exit(0)


def cli_bracket(s):
    return u'(%s)' % s


def get_ids_or_fail(query, db):
    ids = db.query(query)
    if type(ids) == types.IntType:
        fail(u'Query failed')
    else:   # list of ids
        print u'%s matched' % plural(len(ids), u'object')
        return ids


def plural(n, s, pl=None, str=False, justTheWord=False):
    """Returns a string like '23 fields' or '1 field' where the
        number is n, the stem is s and the plural is either stem + 's'
        or stem + pl (if provided)."""
    smallints = [u'zero', u'one', u'two', u'three', u'four', u'five',
                 u'six', u'seven', u'eight', u'nine', u'ten']

    if pl == None:
        pl = u's'
    if str and n < 10 and n >= 0:
        strNum = smallints[n]
    else:
        strNum = int(n)
    if n == 1:
        if justTheWord:
            return s
        else:
            return (u'%s %s' % (strNum, s))
    else:
        if justTheWord:
            return u'%s%s' % (s, pl)
        else:
            return (u'%s %s%s' % (strNum, s, pl))


def parse_args(args=None):
    if args is None:
        args = [a.decode(DEFAULT_ENCODING) for a in sys.argv[1:]]
    if Credentials().unixStyle:
        usage = USAGE_FI if '-F' in args else USAGE
    else:
        usage = USAGE if '-U' in args else USAGE_FI
    parser = OptionParser(usage=usage)
    general = OptionGroup(parser, 'General options')
    general.add_option('-a', '--about', action='append', default=[],
            help='used to specify objects by about tag')
    general.add_option('-i', '--id', action='append', default=[],
            help='used to specify objects by ID')
    general.add_option('-q', '--query', action='append', default=[],
            help='used to specify objects with a FluidDB query')
    general.add_option('-v', '--verbose', action='store_true', default=False,
            help='encourages FDB to report what it\'s doing (verbose mode)')
    general.add_option('-D', '--debug', action='store_true', default=False,
            help='enables debug mode (more output)')
    general.add_option('-T', '--timeout', type='float', default=HTTP_TIMEOUT,
            metavar='n', help='sets the HTTP timeout to n seconds')
    general.add_option('-U', '--unixstylepaths', action='store_true',
                       default=False,
            help='Forces unix-style paths for tags and namespaces.')
    general.add_option('-u', '--user', action='append', default=[],
            help='used to specify a different user (credentials file)')
    general.add_option('-F', '--fluidinfostylepaths', action='store_true',
                       default=False,
            help='Forces Fluidinfo--style paths for tags and namespaces.')
    general.add_option('-V', '--version', action='store_true',
                       default=False,
            help='Report version number.')
    general.add_option('-R', '--recurse', action='store_true',
                       default=False,
            help='recursive (for ls and rm).')
    general.add_option('-l', '--long', action='store_true',
                       default=False,
            help='long listing (for ls).')
    general.add_option('-L', '--longer', action='store_true',
                       default=False,
            help='longer listing (for ls).')
    general.add_option('-g', '--group', action='store_true',
                       default=False,
            help='long listing with groups (for ls).')
    general.add_option('-d', '--namespace', action='store_true',
                       default=False,
            help='don\'t list namespace; just name of namespace.')
    general.add_option('-n', '--ns', action='store_true',
                       default=False,
            help='don\'t list namespace; just name of namespace.')
    parser.add_option_group(general)

    other = OptionGroup(parser, 'Other flags')
    other.add_option('-s', '--sandbox', action='store_const',
                     dest='hostname', const=SANDBOX_PATH,
            help='use the sandbox at http://sandbox.fluidinfo.com')
    other.add_option('--hostname', default=FLUIDDB_PATH, dest='hostname',
            help=('use the specified host (which should start http:// or '
                   'https://; http:// will be added if it doesn\'t) default '
                   'is %default'))
    parser.add_option_group(other)

    options, args = parser.parse_args(args)

    if args == []:
        action = 'version' if options.version else 'help'
    else:
        action, args = args[0], args[1:]

    return action, args, options, parser


def execute_command_line(action, args, options, parser):
    if not action == 'ls':
        credentials = Credentials(options.user[0]) if options.user else None
        db = FluidDB(host=options.hostname, credentials=credentials,
                     debug=options.debug, unixStylePaths=path_style(options))
    ids_from_queries = chain(*imap(lambda q: get_ids_or_fail(q, db),
        options.query))
    ids = chain(options.id, ids_from_queries)

    objs = [O({'mode': 'about', 'specifier': a}) for a in options.about] + \
            [O({'mode': 'id', 'specifier': id}) for id in ids]

    if options.version:
        print 'fdb %s' % version()
        if action == 'version':
            sys.exit(0)
    if action == 'help':
        print USAGE if db.unixStyle else USAGE_FI
        sys.exit(0)
    elif (action.upper() not in HTTP_METHODS + ARGLESS_COMMANDS
          and not args):
        parser.error('Too few arguments for action %s' % action)
    elif action == 'count':
        print 'Total: %s' % (flags.Plural(len(objs), 'object'))
    elif action == 'tags':
        execute_tags_command(objs, db, options)
    elif action in ('tag', 'untag', 'show'):
        if not (options.about or options.query or options.id):
            parser.error('You must use -q, -a or -i with %s' % action)
        tags = args
        if len(tags) == 0 and action != 'count':
            nothing_to_do()
        actions = {
            'tag': execute_tag_command,
            'untag': execute_untag_command,
            'show': execute_show_command,
        }
        command = actions[action]

        command(objs, db, args, options)
    elif action == 'ls':
        ls.execute_ls_command(objs, args, options)
    elif action == 'chmod':
        ls.execute_chmod_command(objs, args, options)
    elif action == 'perms':
        ls.execute_perms_command(objs, args, options)
    elif action in ('pwd', 'pwn', 'whoami'):
        execute_whoami_command(db)
    elif action == 's':
        execute_su_command(db, args)
    elif action in ['get', 'put', 'post', 'delete']:
        execute_http_request(action, args, db, options)
    else:
        parser.error('Unrecognized command %s' % action)
