# fdb.py
#
# Copyright (c) Nicholas J. Radcliffe 2009.
# Licence terms in LICENCE.
#
#     building on fluiddb.py by Sanghyeon Seo and Nicholas Tollervey,
#     which is available from
#         http://bitbucket.org/sanxiyn/fluidfs/
#
#
# 2008/08/20 v0.1       Initial version.   6 tests pass
#                       Used to import 1456 objects from delicious sucessfully
#
# 2008/08/20 v0.2       Added some path tests and new tag_path_split method.
#                       Added untag_object_by_id for removing a tag.
#                       Made it so that 'absolute' paths for tags can be
#                       used (e.g. '/njr/rating') to denote tags, as well
#                       as relative paths (e.g. 'rating').
#                       Subnamespaces still not recognized by tag/untag
#                       but that should change soon.
#                       Also, the tests should all actually work for people
#                       whose FluidDB username isn't njr now :-)
#                       10 tests pass now.
#
# 2008/08/20 v0.3       Reads the credentials file from the home
#                       directory (unix/windows).
#                       Removed import of no-longer-used fuilddb.py
#                         (most of it was in-lined then bastardized)
#                       Added ability to use the code from the command line
#                       for tagging, untagging and retriving objects.
#                       Currently this can be done by specifying the
#                       about tag or object ID, though it will soon
#                       support queries to select objects too (for some value
#                       of 'soon').
#                       See the USAGE string for command line usage
#                       or run with the command line argument -h, or help.
#
# 2008/08/21 v0.4       Added query function to execute a query against
#                       FluidDB and extended all the command line functions
#                       to handle query, so that now you can tag, untag
#                       and get tag values based on a query.
#                       Also now specify json as the format on PUT
#                       when creating tags; apparently they were binary before.
#                       Also fixed things so that objects without an
#                       about field can be created (I think).
#                       Certainly, they don't cause an error.
#                       A few other minor changes to put more sensible
#                       defaults in for credentials etc., making it
#                       easier to use the lirary interactively.
#
# 2008/08/21 v0.5       Renamed command line command get to show to avoid
#                       clash with http GET command.
#                       Plan to add raw put, get, post, delete, head commands.
#                       The tests now assume that the credentials are in
#                       the standard place (~/.fluidDBcredentials on unix,
#                       or fluidDBcredential.ini in the home folder on
#                       windows) and use that, though credentials can still
#                       be provided in any of the old ways in the interface.
#
#                       New class for testing the command line interface (CLI)
#
#                       Can now run tests with
#                           fdb         --- run all tests
#                           fdb test    --- run all tests
#                           fdb testcli --- test CLI only
#                           fdb testcli --- test DB only
#
# 2008/08/22 v0.6       Added delicious2fluiddb.py and its friends
#                       (delicious.py, delicious.cgi, deliconfig.py)
#                       to the repository.   This allows all public
#                       bookmarks from delicious to be uploaded to
#                       FluidDB.   (In fact, a one line change would
#                       allow private ones to be uploaded too, but
#                       since fdb.py knows nothing about permissions
#                       on tags yet, that seems like a bad idea for now.)
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

__version__ = '0.6'

import unittest, os, types, sys, httplib2, urllib, re
if sys.version_info < (2, 6):
    import simplejson as json
else:
    import json
from flags import Flags

USAGE = """Usage examples:
  Run Tests:
    fdb test            (runs all tests)
    fdb testcli         (tests command line interface only)
    fdb testdb          (tests core FluidDB interface only)

  Tag objects:
    fdb tag -a 'DADGAD' tuning rating=10
    fdb tag -i a984efb2-67d8-4b5c-86d0-267b87832fa4 /njr/tuning /njr/rating=10
    fdb tag -q 'about = "DADGAD"' tuning rating=10

  Untag objects:
    fdb untag -a 'DADGAD' /njr/tuning rating
    fdb untag -i a984efb2-67d8-4b5c-86d0-267b87832fa4
    fdb untag -q 'about = "DADGAD"' tuning rating

  Fetch objects and show tags
    fdb show -a 'DADGAD' /njr/tuning /njr/rating 
    fdb show -i  a984efb2-67d8-4b5c-86d0-267b87832fa4 tuning rating 
    fdb show -q 'about = "DADGAD"' tuning rating 

  In general:
    -i is used to specify objects by ID
    -a is used to specify objects by about tag
    -q is used to specify objects with a FluidDB query

"""


class ProblemReadingCredentialsFileError (Exception): pass
class BadCredentialsError (Exception): pass
class CredentialsFileNotFoundError (Exception): pass
class NotHandledYetError (Exception): pass
class TagPathError (Exception): pass
class ModeError (Exception): pass

class STATUS:
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    INTERNAL_SERVER_ERROR = 500
    NOT_FOUND = 404

FLUIDDB_PATH = 'http://fluidDB.fluidinfo.com'
UNIX_CREDENTIALS_FILE='.fluidDBcredentials'
WINDOWS_CREDENTIALS_FILE='fluidDBcredentials.ini'

SIMPLE_NUMBER_RE = re.compile (r'^[0-9]+$')
SIGNED_NUMBER_RE = re.compile (r'^[+-]{0,1}[0-9]+$')
NONNEG_DECIMAL_RE = re.compile (r'^[0-9]+[\.\,]{0,1}[0-9]*$')
NEG_DECIMAL_RE = re.compile (r'^\-[0-9]+[\.\,]{0,1}[0-9]*$')

GROUPABLE_FLAGS = {
    'i' : 'id',
    'a' : 'about',
    'q' : 'query',
    'v' : 'verbose'
}

DADGAD_ID = 'a984efb2-67d8-4b5c-86d0-267b87832fa4'

class O:
    """This is really a dummy class that just sticks everything in
       the hash (dictionary) that initializes it into self.dict
       so that you can use o.id instead of hash['id'] etc.,
       and to allow some string formatting etc.

       Most objects returned natively as hashes by the FluidDB API
       are mapped to these dummy objects in this library."""
    def __init__ (self, hash):
        for k in hash:
            self.__dict__[k] = hash[k]

    def __str__ (self):
        keys = self.__dict__.keys ()
        keys.sort ()
        return '\n'.join (['%20s: %s' % (key, str (self.__dict__[key]))
                                for key in keys])

class TagValue:
    def __init__ (self, name, value=None):
        self.name = name
        self.value = value

class Credentials:
    """Simple store for user credentials.
        Can be initialized with username and password
        or by pointing to a file (filename) with the username
        on the first line and the password on the second line.
        If neither password nor filename is given,
        th default credentials file will be used, if available.
    """
    def __init__ (self, username=None, password=None, id=None, filename=None):
        if username:
            self.username = username
            self.password = password
        else:
            if filename == None:
                filename = get_credentials_file ()
            if os.path.exists (filename):
                try:
                    f = open (filename)
                    lines = f.readlines ()
                    self.username = lines[0].strip ()
                    self.password = lines[1].strip ()
                    f.close ()
                except:
                    raise ProblemReadingCredentialsFileError, ('Failed to read'
                            ' credentials from %s.' % str (filename))
            else:
                raise CredentialsFileNotFoundError, ('Couldn\'t find or '
                            'read credentials from %s.' % str (filename))
                
        self.id = id

class FluidDB:
    """Connection to FluidDB that remembers credentials and provides
        methods for some of the common operations."""

    def __init__ (self, credentials=None):
        if credentials == None:
            credentials = Credentials ()
        self.credentials = credentials
        # the following based on fluiddb.py
        userpass = '%s:%s' % (credentials.username, credentials.password)
        auth = 'Basic %s' % userpass.encode ('base64').strip()
        self.headers = {
                'Accept': 'application/json',
                'Authorization' : auth
        }

    def call (self, method, path, body=None, **kw):
        """Calls FluidDB with the attributes given.
           This function was lifted nearly verbatim from fluiddb.py,
           by Sanghyeon Seo, with additions by Nicholas Tollervey.

           Returns: a 2-tuple consisting of the status and result
        """
        http = httplib2.Http()
        url = FLUIDDB_PATH + urllib.quote(path)
        if kw:
            url = '%s?%s' % (url, urllib.urlencode(kw))
        headers = self.headers.copy()
        if body:
            headers['content-type'] = 'application/json'
        response, content = http.request(url, method, body, headers)
        status = response.status
        if response['content-type'].startswith('application/json'):
            result = json.loads(content)
        else:
            result = content
        return status, result

    def create_object (self, about=None):
        """Creates an object with the about tag given.
           If the object already exists, returns the object instead.

           Returns: the object returned if successful, wrapped up in
           an (O) object whose class variables correspond to the
           values returned by FluidDB, in particular, o.id and o.URL.
           If there's a failure, the return value is an integer error code.
        """
        if about:
            jAbout = json.dumps ({'about' : about})
        else:
            jAbout = json.dumps ({'about' : about})     # was None
        (status, o) = self.call ('POST', '/objects', jAbout)
        return O(o) if status == STATUS.CREATED else status

    def create_abstract_tag (self, tag, description=None, indexed=True):
        """Creates an (abstract) tag with the name (full path) given.
           The tag is not applied to any object.
           If the tag's name (tag) contains slashes, namespaces are created
           as needed.

           Doesn't handle tags with subnamespaces yet.

           Returns (O) object corresponding to the tag if successful,
           otherwise an integer error code.
        """
        (user, subnamespace, tagname) = self.tag_path_split (tag)
        if subnamespace:
            raise NotHandledYetError
        fullnamespace = '/tags/%s' % user
        hash = {'indexed' : indexed, 'description' : description or '',
                'name' : tagname}
        fields = json.dumps (hash)
        (status, o) = self.call ('POST', fullnamespace, fields)
        return O(o) if status == STATUS.CREATED else status

    def delete_abstract_tag (self, tag):
        """Deletes an abstract tag, removing all of its concrete
           instances from objects.   Use with care.
           So db.delete_abstract_tag ('njr/rating') removes
           the njr/rating from ALL OBJECTS IN FLUIDDB.

           Returns 0 if successful; otherwise returns an integer error code.
        """
        fullTag = self.full_tag_path (tag)
        (status, o) = self.call ('DELETE', fullTag)
        return 0 if status == STATUS.NO_CONTENT else status

    def tag_object_by_id (self, id, tag, value=None,
                                createTagIfNeeded=True):
        """Tags the object with the given id with the tag
           given, and the value given, if present.
           If the (abstract) tag with corresponding to the
           tag given doesn't exist, it is created unless
           createTagIfNeeded is set to False.
        """
        fullTag = self.abs_tag_path (tag)
        hash = {'value' : value, 'format' : 'json'}
        fields = json.dumps (hash)
        objTag = '/objects/%s%s' % (id, fullTag)
        (status, o) = self.call ('PUT', objTag, fields)
        if status == STATUS.NOT_FOUND and createTagIfNeeded:
            o = self.create_abstract_tag (tag)
            if type (o) == types.IntType:       # error code
                return o
            else:
                return self.tag_object_by_id (id, tag, value, False)
        else:
            return 0 if status == STATUS.NO_CONTENT else status

    def tag_object_by_about (self, about, tag, value=None,
                             createTagIfNeeded=True):
        """Tags the object with whose about tag is as specified
           with the tag and and with the value given, if present.
           If the (abstract) tag with corresponding to the
           tag given doesn't exist, it is created unless
           createTagIfNeeded is set to False.
        """
        o = self.create_object (about=about)
        if type (o) == types.IntType:   # error code
            return o
        return self.tag_object_by_id (o.id, tag, value, createTagIfNeeded)

    def untag_object_by_id (self, id, tag, missingConstitutesSuccess=True):
        """Removes the tag from the object with id if present.
           If the tag, or the object, doesn't exist,
           the default is that this is considered successful,
           but missingConstitutesSuccess can be set to False
           to override this behaviour.

           Returns 0 for success, non-zero error code otherwise.
        """
        fullTag = self.abs_tag_path (tag)
        objTag = '/objects/%s%s' % (id, fullTag)
        (status, o) = self.call ('DELETE', objTag)
        ok = (status == STATUS.NO_CONTENT
                or status == STATUS.NOT_FOUND and missingConstitutesSuccess)
        return 0 if ok else status

    def untag_object_by_about (self, about, tag,
                               missingConstitutesSuccess=True):
        """Removes the tag from the object having the about tag
           specified, if the tag is present.
           If the tag, or the object, doesn't exist,
           the default is that this is considered successful,
           but missingConstitutesSuccess can be set to False
           to override this behaviour.

           Returns 0 for success, non-zero error code otherwise.
        """
        o = self.create_object (about=about)
        if type (o) == types.IntType:   # error code
            return o
        return self.untag_object_by_id (o.id, tag, missingConstitutesSuccess)

    def get_tag_value_by_id (self, id, tag):
        """Gets the value of a tag on an object identified by the
           object's ID.

           Returns  returns a 2-tuple, in which the first component
           is the status, and the second is either the tag value,
           if the return stats is STATUS.OK, or None otherwise.
        """
        fullTag = self.abs_tag_path (tag)
        objTag = '/objects/%s%s' % (id, fullTag)
        (status, o) = self.call ('GET', objTag)
        if status == STATUS.OK:
            if type (o) == types.DictType:
                return status, o['value']
            else:
                return status, o        # fluiddb/about seems to return a
                                        # a raw string.   Weird.
        else:
            return status, None

    def get_tag_value_by_about (self, about, tag):
        """Gets the value of a tag on an object having the given about tag.

           Returns  returns a 2-tuple, in which the first component
           is the status, and the second is either the tag value,
           if the return stats is STATUS.OK, or None otherwise.
        """
        o = self.create_object (about=about)
        if type (o) == types.IntType:   # error code
            return o
        return self.get_tag_value_by_id (o.id, tag)

    def get_tag_values_by_id (self, id, tags):
        return [self.get_tag_value_by_id (id, tag) for tag in tags]

    def get_tag_values_by_about (self, about, tags):
        return [self.get_tag_value_by_about (about, tag) for tag in tags]

    def query (self, query):
        """Runs the query to get the IDs of objects satisfying the query.
           If the query is successful, the list of ids is returned, as a list;
           otherwise, an error code is returned.
        """
        (status, o) = self.call ('GET', '/objects', query=query)
        return status if status != STATUS.OK else o['ids']

    def abs_tag_path (self, tag):
        """Returns the absolute path for the tag nominated,
           in the form
                /namespace/.../shortTagName
           If the already tag starts with a '/', no action is taken;
           if it doesn't, the username from the current credentials
           is added.

           if /tags/ is present at the start of the path,
           /tags is stripped off (which might be a problem if there's
           a user called tags...

           Examples: (assuming the user credentials username is njr):
                abs_tag_path ('rating') = '/njr/rating'
                abs_tag_path ('/njr/rating') = '/njr/rating'
                abs_tag_path ('/tags/njr/rating') = '/njr/rating'

                abs_tag_path ('foo/rating') = '/njr/foo/rating'
                abs_tag_path ('/njr/foo/rating') = '/njr/foo/rating'
                abs_tag_path ('/tags/njr/foo/rating') = '/njr/foo/rating'
        """
        if tag.startswith ('/'):
            if tag.startswith ('/tags/'):
                return tag[5:]
            else:
                return tag
        else:
            return '/%s/%s' % (self.credentials.username, tag)
        
    def full_tag_path (self, tag):
        """Returns the absolute tag path (see above), prefixed with /tag.

           Examples: (assuming the user credentials username is njr):
                full_tag_path ('rating') = '/tags/njr/rating'
                full_tag_path ('/njr/rating') = '/tags/njr/rating'
                full_tag_path ('/tags/njr/rating') = '/tags/njr/rating'
                full_tag_path ('foo/rating') = '/tags/njr/foo/rating'
                full_tag_path ('/njr/foo/rating') = '/tags/njr/foo/rating'
                full_tag_path ('/tags/njr/foo/rating') = '/tags/njr/foo/rating'
        """
        if tag.startswith ('/tag/'):
            return tag
        else:
            return '/tags%s' % self.abs_tag_path (tag)

    def tag_path_split (self, tag):
        """A bit like os.path.split, this splits any old kind of a FluidDB
           tag path into a user, a subnamespace (if there is one) and a tag.
           But unlike os.path.split, if no namespace is given,
           the one from the user credentials is returned.

           Any /tags/ prefix is discarded and the namespace is returned
           with no leading '/'.

           Examples: (assuming the user credentials username is njr):
                tag_path_split ('rating') = ('njr', '', 'rating')
                tag_path_split ('/njr/rating') = ('njr', '', 'rating')
                tag_path_split ('/tags/njr/rating') = ('njr', '', 'rating')
                tag_path_split ('foo/rating') = ('njr', 'foo', 'rating')
                tag_path_split ('/njr/foo/rating') = ('njr', 'foo', 'rating')
                tag_path_split ('/tags/njr/foo/rating') = ('njr', 'foo',
                                                                  'rating')
                tag_path_split ('foo/bar/rating') = ('njr', 'foo/bar', 'rating')
                tag_path_split ('/njr/foo/bar/rating') = ('njr', 'foo/bar',
                                                                 'rating')
                tag_path_split ('/tags/njr/foo/bar/rating') = ('njr', 'foo/bar',
                                                                  'rating')

           Returns (user, subnamespace, tagname)
        """
        if tag in ('', '/'):
            raise TagPathError, ('%s is not a valid tag path' % tag)
        tag = self.abs_tag_path (tag)
        parts = tag.split ('/')
        subnamespace = ''
        tagname = parts[-1]
        if len (parts) < 3:
            raise TagPathError, ('%s is not a valid tag path' % tag)
        user = parts[1]
        if len (parts) > 3:
            subnamespace = '/'.join (parts[2:-1])
        return (user, subnamespace, tagname)


def object_uri (id):
    """Returns the full URI for the FluidDB object with the given id."""
    return '%s/objects/%s' % (FLUIDDB_PATH, id)

def tag_uri (namespace, tag):
    """Returns the full URI for the FluidDB tag with the given id."""
    return '%s/tags/%s/%s' % (FLUIDDB_PATH, namespace, tag)

def get_credentials_file (unixFile=UNIX_CREDENTIALS_FILE,
                          windowsFile=WINDOWS_CREDENTIALS_FILE):
    if os.name == 'posix':
        homeDir = os.path.expanduser('~')
        return os.path.join (homeDir, unixFile)
    elif os.name :
        from win32com.shell import shellcon, shell
        homeDir = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
        return os.path.join (homeDir, windowsFile)
    else:
        return None

def get_typed_tag_value (v):
    """Uses some simple rules to extract simple typed values from strings.
        Specifically:
           true and t (any case) return True (boolean)
           false and f (any case) return False (boolean)
           simple integers (possibly signed) are returned as ints
           simple floats (possibly signed) are returned as floats
                (supports '.' and ',' as floating-point separator,
                 subject to locale)
           Everything else is returned as a string, with matched
                enclosing quotes stripped.
    """
    if v.lower () in ('true', 't'):
        return True
    elif v.lower () in ('false', 'f'):
        return False
    elif re.match (SIMPLE_NUMBER_RE, v) or re.match (SIGNED_NUMBER_RE, v):
        return int (v)
    elif re.match (NONNEG_DECIMAL_RE, v) or re.match (NEG_DECIMAL_RE, v):
        try:
            r = float (v)
        except ValueError:
            return str (v)
    elif len (v) > 1 and v[0] == v[-1] and v[0] in ('"\''):
        return v[1:-1]
    else:
        return str (v)

def form_tag_value_pairs (tags):
    pairs = []
    for tag in tags:
        eqPos = tag.find ('=')
        if eqPos == -1:
            pairs.append (TagValue (tag, None))
        else:
            t = tag[:eqPos]
            v = get_typed_tag_value (tag[eqPos+1:])
            pairs.append (TagValue (t, v))
    return pairs

def usage (error=True):
    if error:
        sys.stderr.write (USAGE)
        sys.exit (1)
    else:
        print USAGE
        sys.exit (0)

def warning (msg):
    sys.stderr.write ('%s\n' % msg)

def fail (msg):
    warning (msg)
    sys.exit (1)

def nothing_to_do ():
    print 'Nothing to do.'
    sys.exit (0)

def describe_by_mode (specifier, mode):
    """mode can be a string (about, id or query) or a flags object
        with flags.about, flags.query and flags.id"""    
    flags = mode
    if mode == 'about' or (hasattr (flags, 'about') and flags.about):
        return describe_by_about (specifier)
    elif mode == 'id' or (hasattr (flags, 'id') and flags.id):
        return describe_by_id (specifier)
    elif mode == 'query' or (hasattr (flags, 'query') and flags.query):
        return describe_by_id (specifier)
    raise ModeError, 'Bade Mode'

def describe_by_about (specifier):
    return 'with about="%s"' % specifier

def describe_by_id (specifier):
    return specifier

def cli_bracket (s):
    return '(%s)' % s

def execute_tag_command (flags, db, tags, specifier):
    tags = form_tag_value_pairs (tags)
    description = describe_by_mode (specifier, flags)
    if len (tags) == 0:
        nothing_to_do ()
    if flags.about:
        about = specifier
        for tag in tags:
            o = db.tag_object_by_about (about, tag.name, tag.value)
            if o == 0:
                if flags.verbose:
                    print ('Tagged object %s with %s'
                            % (description,
                               formatted_tag_value (tag.name, tag.value)))
            else:
                warning ('Failed to tag object %s with %s'
                            % (description, tag.name))
                warning ('Error code %d' % o)
    else:
        id = specifier
        for tag in tags:
            o = db.tag_object_by_id (id, tag.name, tag.value)
            if o == 0:
                if flags.verbose:
                    print ('Tagged object %s with %s'
                           % (id, formatted_tag_value (tag.name,tag.value)))
            else:
                warning ('Failed to tag object %s with %s'
                            % (id, tag.name))
                warning ('Error code %d' % o)

def execute_untag_command (flags, db, tags, specifier):
    description = describe_by_mode (specifier, flags)
    if flags.about:
        about = specifier
        for tag in tags:
            o = db.untag_object_by_about (about, tag)
            if o == 0:
                if flags.verbose:
                    print ('Removed tag %s from object %s'
                         % (tag, description))
            else:
                warning ('Failed to remove tag %s from object %s'
                            % (tag, description))
                warning ('Error code %d' % o)
    else:
        id = specifier
        for tag in tags:
            o = db.untag_object_by_id (id, tag)
            if o == 0:
                if flags.verbose:
                    print ('Removed tag %s from object %s' % (tag,
                                description))
            else:
                warning ('Failed to remove tag %s from object %s '
                                % (tag, description))
                warning ('Error code %d' % o)

def formatted_tag_value (tag, value):
    if value == None:
        return tag
    elif type (value) in types.StringTypes:
        return '%s = "%s"' % (tag, value)
    else:
        return '%s = %s' % (tag, str (value))

def get_ids_or_fail (query, db):
    ids = db.query (query)
    if type (ids) == types.IntType:
        fail ('Query failed')
    else:   # list of ids
        return ids

def execute_show_command (flags, db, tags, specifier):
    description = describe_by_mode (specifier, flags)
    if flags.about:
        print 'Object %s:' % description
    else:
        print 'Object %s:' % description
    for tag in tags:
        fulltag = db.abs_tag_path (tag)
        if flags.about:
            status, v = db.get_tag_value_by_about (specifier, tag)
        else:
            status, v = db.get_tag_value_by_id (specifier, tag)
        if status == STATUS.OK:
            print '  %s' % formatted_tag_value (fulltag, v)
        elif status == STATUS.NOT_FOUND:
            print '  %s' % cli_bracket ('tag %s not present' % fulltag)
        else:
            print cli_bracket ('error code %d getting tag %s' % (o, fulltag))

def execute_command_line (flags, db):
    if len (flags.args) < 2:
        usage ()
    elif flags.command in ('tag', 'untag', 'show'):
        if not (flags.about or flags.query or flags.id):
            fail ('You must use -q, -a or -i with %s' % flags.command)
        tags = flags.args[1:]
        if len (tags) == 0:
            nothing_to_do ()
        if flags.command == 'tag':
            command = execute_tag_command
        elif flags.command == 'untag':
            command = execute_untag_command
        elif flags.command == 'show':
            command = execute_show_command
        if flags.query:
            ids = get_ids_or_fail (flags.args[0], db)
            for id in ids:
                command (flags, db, tags, id)
        else:
            command (flags, db, tags, flags.args[0])
    else:
        warning ('Unrecognized command %s' % flags.command)

class TestFluidDB (unittest.TestCase):
    db = FluidDB ()

    def testCreateObject (self):
        db = self.db
        o = db.create_object ('DADGAD')
        self.assertEqual (o.id, DADGAD_ID)
        self.assertEqual (o.URI, object_uri (DADGAD_ID))

    def testCreateObjectNoAbout (self):
        db = self.db
        o = db.create_object ()
        self.assertEqual (type (o) != types.IntType, True)

    def testCreateObjectFail (self):
        bad = Credentials ('doesnotexist', 'certainlywiththispassword')
        db = FluidDB (bad)
        o = db.create_object ('DADGAD')
        self.assertEqual (o, STATUS.INTERNAL_SERVER_ERROR)

    def testCreateTag (self):
        db = self.db
        o = db.delete_abstract_tag ('testrating')
        # doesn't really matter if this works or not

        o = db.create_abstract_tag ('testrating',
                                "njr's testrating (0-10; more is better)")
        self.assertEqual (type (o.id) in types.StringTypes, True)
        self.assertEqual (o.URI, tag_uri (db.credentials.username,
                                                'testrating'))

    def testSetTagByID (self):
        db = self.db
        user = db.credentials.username
        o = db.delete_abstract_tag ('testrating')
        o = db.create_abstract_tag ('testrating',
                                "njr's testrating (0-10; more is better)")
        o = db.tag_object_by_id (DADGAD_ID, '/%s/testrating' % user, 5)
        self.assertEqual (o, 0)
        status, v = db.get_tag_value_by_id (DADGAD_ID, 'testrating')
        self.assertEqual (v, 5)

    def testSetTagByAbout (self):
        db = self.db
        user = db.credentials.username
        o = db.delete_abstract_tag ('testrating')
        o = db.tag_object_by_about ('DADGAD', '/%s/testrating' % user, 'five')
        self.assertEqual (o, 0)
        status, v = db.get_tag_value_by_about ('DADGAD', 'testrating')
        self.assertEqual (v, 'five')

    def testSetNonExistentTag (self):
        db = self.db
        o = db.delete_abstract_tag ('testrating')
        o = db.tag_object_by_id (DADGAD_ID, 'testrating', 5)
        self.assertEqual (o, 0)
        status, v = db.get_tag_value_by_id (DADGAD_ID, 'testrating')
        self.assertEqual (v, 5)

    def testUntagObjectByID (self):
        db = self.db

        # First tag something
        o = db.tag_object_by_id (DADGAD_ID, 'testrating', 5)
        self.assertEqual (o, 0)

        # Now untag it
        error = db.untag_object_by_id (DADGAD_ID, 'testrating')
        self.assertEqual (error, 0)
        status, v = db.get_tag_value_by_id (DADGAD_ID, 'testrating')
        self.assertEqual (status, STATUS.NOT_FOUND)

        # Now untag it again (should be OK)
        error = db.untag_object_by_id (DADGAD_ID, 'testrating')
        self.assertEqual (error, 0)

        # And again, but this time asking for error if untagged
        error = db.untag_object_by_id (DADGAD_ID, 'testrating', False)
        self.assertEqual (error, STATUS.NOT_FOUND)

    def testUntagObjectByAbout (self):
        db = self.db

        # First tag something
        o = db.tag_object_by_id (DADGAD_ID, 'testrating', 5)
        self.assertEqual (o, 0)

        # Now untag it
        error = db.untag_object_by_about ('DADGAD', 'testrating')
        self.assertEqual (error, 0)
        status, v = db.get_tag_value_by_about ('DADGAD', 'testrating')
        self.assertEqual (status, STATUS.NOT_FOUND)

    def testAddValuelessTag (self):
        db = self.db
        o = db.delete_abstract_tag ('testconvtag')
        o = db.create_abstract_tag ('testconvtag',
                                "a conventional (valueless) tag")
        o = db.tag_object_by_id (DADGAD_ID, 'testconvtag')
        self.assertEqual (o, 0)
        status, v = db.get_tag_value_by_id (DADGAD_ID, 'testconvtag')
        self.assertEqual (v, None)

    def testFullTagPath (self):
        db = self.db
        user = db.credentials.username
        self.assertEqual (db.full_tag_path ('rating'),
                          '/tags/%s/rating' % user)
        self.assertEqual (db.full_tag_path ('/%s/rating' % user),
                          '/tags/%s/rating' % user)
        self.assertEqual (db.full_tag_path ('/tags/%s/rating' % user),
                          '/tags/%s/rating' % user)
        self.assertEqual (db.full_tag_path ('foo/rating'),
                          '/tags/%s/foo/rating' % user)
        self.assertEqual (db.full_tag_path ('/%s/foo/rating' % user),
                          '/tags/%s/foo/rating' % user)
        self.assertEqual (db.full_tag_path ('/tags/%s/foo/rating' % user),
                          '/tags/%s/foo/rating' % user)

    def testAbsTagPath (self):
        db = self.db
        user = db.credentials.username
        self.assertEqual (db.abs_tag_path ('rating'), '/%s/rating' % user)
        self.assertEqual (db.abs_tag_path ('/%s/rating' % user),
                          '/%s/rating' % user)
        self.assertEqual (db.abs_tag_path ('/tags/%s/rating' % user),
                          '/%s/rating' % user)
        self.assertEqual (db.abs_tag_path ('foo/rating'),
                          '/%s/foo/rating' % user)
        self.assertEqual (db.abs_tag_path ('/%s/foo/rating' % user),
                          '/%s/foo/rating' % user)
        self.assertEqual (db.abs_tag_path ('/tags/%s/foo/rating' % user),
                          '/%s/foo/rating' % user)

    def testTagPathSplit (self):
        db = self.db
        user = db.credentials.username
        self.assertEqual (db.tag_path_split ('rating'), (user, '', 'rating'))
        self.assertEqual (db.tag_path_split ('/%s/rating' % user),
                          (user, '', 'rating'))
        self.assertEqual (db.tag_path_split ('/tags/%s/rating' % user),
                          (user, '', 'rating'))
        self.assertEqual (db.tag_path_split ('foo/rating'),
                          (user, 'foo', 'rating'))
        self.assertEqual (db.tag_path_split ('/%s/foo/rating' % user),
                          (user, 'foo', 'rating'))
        self.assertEqual (db.tag_path_split ('/tags/%s/foo/rating' % user),
                          (user, 'foo', 'rating'))
        self.assertEqual (db.tag_path_split ('foo/bar/rating'),
                                (user, 'foo/bar', 'rating'))
        self.assertEqual (db.tag_path_split ('/%s/foo/bar/rating' % user),
                          (user, 'foo/bar', 'rating'))
        self.assertEqual (db.tag_path_split ('/tags/%s/foo/bar/rating' % user),
                          (user, 'foo/bar', 'rating'))
        self.assertRaises (TagPathError, db.tag_path_split, '')
        self.assertRaises (TagPathError, db.tag_path_split, '/')
        self.assertRaises (TagPathError, db.tag_path_split, '/foo')

class SaveOut:
    def __init__ (self):
        self.buffer = []

    def write (self, msg):
        self.buffer.append (msg)

    def clear (self):
        self.buffer = []

def specify_DADGAD (mode='about'):
    if mode == 'about':
        return ('-a', 'DADGAD')
    elif mode == 'id':
        return ('-i', DADGAD_ID)
    elif mode == 'query':
        return ('-q', 'fluiddb/about="DADGAD"')
    else:
        raise ModeError, 'Bad mode'


class TestCLI (unittest.TestCase):
    db = FluidDB ()

    def setUp (self):
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        self.stealOutput ()

    def stealOutput (self):
        self.out = SaveOut ()
        self.err = SaveOut ()
        sys.stdout = self.out
        sys.stderr = self.err

    def reset (self):
        sys.stdout = self.stdout
        sys.stderr = self.stderr

    def Print (self, msg):
        self.stdout.write (str (msg) + '\n')

    def testOutputManipulation (self):
        print 'one'
        sys.stderr.write ('two')
        self.reset ()
        self.assertEqual (self.out.buffer, ['one', '\n'])
        self.assertEqual (self.err.buffer, ['two'])

    def tagTest (self, mode, verbose=True):
        self.stealOutput ()
        (flag, spec) = specify_DADGAD (mode)
        description = describe_by_mode (spec, mode)
        flags = ['-v', flag] if verbose else [flag]
        args = ['tag'] + flags + [spec, 'rating=10']
        flags = Flags (args, groupable = GROUPABLE_FLAGS)
        execute_command_line (flags, self.db)
        self.reset ()
        if verbose:
            target = ['Tagged object %s with rating = 10' % description, '\n']
        else:
            target = []
        self.assertEqual (self.out.buffer, target)
        self.assertEqual (self.err.buffer, [])

    def untagTest (self, mode, verbose=True):
        self.stealOutput ()
        (flag, spec) = specify_DADGAD (mode)
        description = describe_by_mode (spec, mode)
        flags = ['-v', flag] if verbose else [flag]
        args = ['untag'] + flags + [spec, 'rating']
        flags = Flags (args, groupable = GROUPABLE_FLAGS)
        execute_command_line (flags, self.db)
        self.reset ()
        if verbose:
            target = ['Removed tag rating from object %s' % description, '\n']
        else:
            target = []
        self.assertEqual (self.out.buffer, target)
        self.assertEqual (self.err.buffer, [])

    def showTaggedSuccessTest (self, mode):
        self.stealOutput ()
        (flag, spec) = specify_DADGAD (mode)
        description = describe_by_mode (spec, mode)
        args = ['show', '-v', flag, spec, 'rating', '/fluiddb/about']
        flags = Flags (args, groupable = GROUPABLE_FLAGS)
        execute_command_line (flags, self.db)
        self.reset ()
        self.assertEqual (self.out.buffer,
                ['Object %s:' % description, '\n',
                 '  /njr/rating = 10', '\n',
                 '  /fluiddb/about = "DADGAD"', '\n'])
        self.assertEqual (self.err.buffer, [])

    def showUntagSuccessTest (self, mode):
        self.stealOutput ()
        (flag, spec) = specify_DADGAD (mode)
        description = describe_by_mode (spec, mode)
        args = ['show', '-v', flag, spec, 'rating', '/fluiddb/about']
        flags = Flags (args, groupable = GROUPABLE_FLAGS)
        execute_command_line (flags, self.db)
        self.reset ()
        user = self.db.credentials.username
        self.assertEqual (self.out.buffer,
                ['Object %s:' % description, '\n',
                 '  %s' % cli_bracket ('tag /%s/rating not present' % user),

                '\n', '  /fluiddb/about = "DADGAD"', '\n'])
        self.assertEqual (self.err.buffer, [])

    def testTagByAboutVerboseShow (self):
        self.tagTest ('about')
        self.showTaggedSuccessTest ('about')

    def testTagByIDVerboseShow (self):
        self.tagTest ('id')
        self.showTaggedSuccessTest ('id')

    def testTagByQueryVerboseShow (self):
        self.tagTest ('query', verbose=False)
        self.showTaggedSuccessTest ('id')

    def testTagSilent (self):
        self.tagTest ('about', verbose=False)
        self.showTaggedSuccessTest ('about')

    def testUntagByAboutVerboseShow (self):
        self.untagTest ('about')
        self.showUntagSuccessTest ('about')

    def testUntagByIDVerboseShow (self):
        self.untagTest ('id')
        self.showUntagSuccessTest ('id')

        
if __name__ == '__main__':
    flags = Flags (sys.argv[1:], groupable=GROUPABLE_FLAGS)
    if len (sys.argv) == 1 or flags.command.startswith ('test'):
        cases = [
            TestCLI,
            TestFluidDB
        ]
        if flags.command == 'testcli':
            cases = [TestCLI]
        if flags.command == 'testdb':
            cases = [TestFluidDB]
        suite = unittest.TestSuite ()
        for c in cases:
            s = unittest.TestLoader ().loadTestsFromTestCase (c)
            suite.addTest (s)
        unittest.TextTestRunner(verbosity=1).run(suite)
    else:
        db = FluidDB ()
        execute_command_line (flags, db)

