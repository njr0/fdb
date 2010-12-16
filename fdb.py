# -*- coding: utf-8 -*-
#
# fdb.py
#
#
# Copyright (c) Nicholas J. Radcliffe 2009 and other authors specified
#               in the AUTHOR
# Licence terms in LICENCE.
#
#     building on fluiddb.py by Sanghyeon Seo and Nicholas Tollervey,
#     which is available from
#         http://bitbucket.org/sanxiyn/fluidfs/
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

__version__ = '1.27'

import os
import re
import sys
import types
import unittest
import urllib
from functools import wraps
from itertools import chain, imap
from httplib2 import Http
from optparse import OptionParser, OptionGroup

if sys.version_info < (2, 6):
    import simplejson as json
else:
    import json

DADGAD_ID = u'ca0f03b5-3c0d-4c00-aa62-bdb07f29599c'
USAGE = """Run Tests:
   fdb test            (runs all tests)
   fdb testcli         (tests command line interface only)
   fdb testdb          (tests core FluidDB interface only)
   fdb testutil        (runs tests not requiring FluidDB access)

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
   fdb -i %s

 Raw HTTP GET:
   fdb get /tags/njr/google
   fdb get /permissions/tags/njr/rating action=delete
   (use POST/PUT/DELETE/HEAD at your peril; currently untested.)
""" % (DADGAD_ID, DADGAD_ID, DADGAD_ID, DADGAD_ID)


class ProblemReadingCredentialsFileError(Exception):
    pass


class BadCredentialsError(Exception):
    pass


class CredentialsFileNotFoundError(Exception):
    pass


class NotHandledYetError(Exception):
    pass


class TagPathError(Exception):
    pass


class ModeError(Exception):
    pass


class TooFewArgsForHTTPError(Exception):
    pass


class UnexpectedGetValueError(Exception):
    pass


class CannotWriteUserError(Exception):
    pass


class FailedToCreateNamespaceError(Exception):
    pass


class ObjectNotFoundError(Exception):
    pass


class EmptyNamespaceError(Exception):
    pass


class UnrecognizedHTTPMethodError(Exception):
    pass


class STATUS:
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    INTERNAL_SERVER_ERROR = 500
    NOT_FOUND = 404
    UNAUTHORIZED = 401

FLUIDDB_PATH = u'http://fluiddb.fluidinfo.com'
SANDBOX_PATH = u'http://sandbox.fluidinfo.com'
UNIX_CREDENTIALS_FILE = '.fluidDBcredentials'
WINDOWS_CREDENTIALS_FILE = 'fluidDBcredentials.ini'
UNIX_USER_CREDENTIALS_FILE = '.fluidDBcredentials.%s'
WINDOWS_USER_CREDENTIALS_FILE = 'fluidDBcredentials-%s.ini'
HTTP_TIMEOUT = 300.123456       # unlikey the user will choose this
PRIMITIVE_CONTENT_TYPE = u'application/vnd.fluiddb.value+json'

INTEGER_RE = re.compile(r'^[+\-]{0,1}[0-9]+$')
DECIMAL_RE = re.compile(r'^[+\-]{0,1}[0-9]+[\.\,]{0,1}[0-9]*$')
DECIMAL_RE2 = re.compile(r'^[+\-]{0,1}[\.\,]{1}[0-9]+$')

HTTP_METHODS = ['GET', 'PUT', 'POST', 'DELETE', 'HEAD']

IDS_MAIN = {u'DADGAD': u'1fb8e9cb-70b9-4bd0-a7e7-880247384abd'}
IDS_SAND = {u'DADGAD': DADGAD_ID}

DEFAULT_ENCODING = 'UTF-8'


def id(about, host):
    # this might turn into a cache that gets dumped to file and
    # supports more than two fixed hosts in time.
    cache = IDS_MAIN if host == FLUIDDB_PATH else IDS_SAND
    return cache[about]


def by_about(f):
    @wraps(f)
    def wrapper(self, about, *args, **kwargs):
        o = self.create_object(about=about)
        if type(o) == types.IntType:   # error code
            return o
        return f(self, o.id, *args, **kwargs)
    return wrapper


def _get_http(timeout):
    try:
        http = Http(timeout=timeout)
    except TypeError:
        # The user's version of http2lib is old. Omit the timeout.
        http = Http()
    return http


class O:
    """This is really a dummy class that just sticks everything in
       the hash (dictionary) that initializes it into self.dict
       so that you can use o.id instead of hash['id'] etc.,
       and to allow some string formatting etc.

       Most objects returned natively as hashes by the FluidDB API
       are mapped to these dummy objects in this library."""
    def __init__(self, hash):
        for k in hash:
            self.__dict__[k] = hash[k]

    def __str__(self):
        keys = self.__dict__.keys()
        keys.sort()
        return '\n'.join(['%20s: %s' % (key, str(self.__dict__[key]))
                                for key in keys])


class TagValue:
    def __init__(self, name, value=None):
        self.name = name
        self.value = value

    def __str__(self):
        return ('Tag "%s", value "%s" of type %s'
                     % (self.name, str(self.value), str(type(self.value))))


class Credentials:
    """Simple store for user credentials.
        Can be initialized with username and password
        or by pointing to a file (filename) with the username
        on the first line and the password on the second line.
        If neither password nor filename is given,
        th default credentials file will be used, if available.
    """
    def __init__(self, username=None, password=None, id=None, filename=None):
        if username and password:
            self.username = username
            self.password = password
        else:
            if filename == None:
                filename = get_credentials_file(username=username)
            if os.path.exists(filename):
                try:
                    f = open(filename)
                    lines = f.readlines()
                    self.username = lines[0].strip()
                    self.password = lines[1].strip()
                    f.close()
                except:
                    raise ProblemReadingCredentialsFileError('Failed to read'
                            ' credentials from %s.' % str(filename))
            else:
                raise CredentialsFileNotFoundError('Couldn\'t find or '
                            'read credentials from %s.' % str(filename))

        self.id = id


class FluidDB:
    """Connection to FluidDB that remembers credentials and provides
        methods for some of the common operations."""

    def __init__(self, credentials=None, host=None, debug=False,
                 encoding=DEFAULT_ENCODING):
        if credentials == None:
            credentials = Credentials()
        self.credentials = credentials
        if host is None:
            host = choose_host()
        self.host = host
        self.debug = debug
        self.encoding = encoding
        self.timeout = choose_http_timeout()
        if not host.startswith(u'http'):
            self.host = u'http://%s' % host
        # the following based on fluiddb.py
        userpass = '%s:%s' % (credentials.username, credentials.password)
        auth = 'Basic %s' % userpass.encode('base64').strip()
        self.headers = {
            u'Authorization': self.decode(auth)
        }

    def _get_url(self, host, path, hash, kw):
        url = host + urllib.quote(path)
        if hash:
            url = '%s?%s' % (url, urllib.urlencode(hash))
        elif kw:
            url = '%s?%s' % (url, urllib.urlencode(kw))
        return self.decode(url)

    def set_connection_from_global(self):
        """Sets the host on the basis of the global variable flags,
           if that exists.   Used to enable the tests to run against
           alternate hosts."""
        self.host = choose_host()
        self.debug = choose_debug_mode()
        self.timeout = choose_http_timeout()

    def set_debug_timeout(self, v):
        if self.timeout == HTTP_TIMEOUT:
            self.timeout = float(v)

    def call(self, method, path, body=None, hash=None, **kw):
        """Calls FluidDB with the attributes given.
           This function was lifted nearly verbatim from fluiddb.py,
           by Sanghyeon Seo, with additions by Nicholas Tollervey.

           Returns: a 2-tuple consisting of the status and result
        """
        headers = self.headers.copy()
        if body:
            headers[u'content-type'] = u'application/json'

        if True:
            k2 = {}
            for k in kw:
                k2[k] = (kw[k].encode('UTF-8')
                         if type(kw[k]) == types.StringType else kw[k])
            kw = k2
        url = self._get_url(self.host, path, hash, kw)

        if self.debug:
            print(u'method: %r\nurl: %r\nbody: %s\nheaders:' %
                   (method, url, body))
            for k in headers:
                if not k == u'Authorization':
                    print u'  %s=%s' % (k, headers[k])

        http = _get_http(self.timeout)
        response, content = http.request(url, method, body, headers)
        status = response.status
        if response[u'content-type'].startswith(u'application/json'):
            result = json.loads(content)
        else:
            result = content
        if self.debug:
            print u'status: %d; content: %s' % (status, str(result))
            if status >= 400:
                for header in response:
                    if header.lower().startswith(u'x-fluiddb-'):
                        print u'\t%s=%s' % (header, response[header])

        return status, result

    def encode(self, value):
        """Encode value in chosen encoding if the value is unicode
           and the chosen encoding is not unicode"""
        if type(value) == unicode and not self.encoding == 'unicode':
            return value.encode(self.encoding)
        else:
            return value

    def decode(self, value):
        """Decode value from chosen encoding into unicode if the
           value is a string."""
        if type(value) == types.StringType:
            return unicode(value, self.encoding)
        else:
            return value

    def _get_tag_value(self, path):
        headers = self.headers.copy()
        url = self._get_url(self.host, path, hash=None, kw=None)
        http = _get_http(self.timeout)
        response, content = http.request(url, 'GET', None, headers)
        content_type = response['content-type']
        if content_type == PRIMITIVE_CONTENT_TYPE:
            result = json.loads(content)
            content_type = None
        else:
            result = content
        return response.status, (self.encode(result), content_type)

    def _set_tag_value(self, path, value, value_type=None):
        headers = self.headers.copy()
        if value_type is None:
            value = json.dumps(value)
            value_type = PRIMITIVE_CONTENT_TYPE
        headers['content-type'] = value_type
        url = self._get_url(self.host, path, hash=None, kw=None)
        http = _get_http(self.timeout)
        response, content = http.request(url, 'PUT', self.decode(value),
                                         headers)
        return response.status, content

    def create_object(self, about=None):
        """Creates an object with the about tag given.
           If the object already exists, returns the object instead.

           Returns: the object returned if successful, wrapped up in
           an (O) object whose class variables correspond to the
           values returned by FluidDB, in particular, o.id and o.URL.
           If there's a failure, the return value is an integer error code.
        """
        if about:
            body = json.dumps({u'about': self.decode(about)})
        else:
            body = None
        (status, o) = self.call(u'POST', u'/objects', body)
        return O(o) if status == STATUS.CREATED else status

    def create_namespace(self, path, description='',
                          createParentIfNeeded=True, verbose=False):
        """Creates the namespace specified by path using the description
           given.

           If the parent namespace does not exist, by default it is created
           with a blank description; however, this behaviour can be
           overridden by setting createParentIfNeeded to False, in which
           case NOT_FOUND will be returned in this case.

           Any trailing slash is deleted.

           The path, as usual in FDB, is considered absolute if it starts
           with a slash, and relative to the user's namespace otherwise.

           Returns ID of namespace object if created successfully.
           If not, but the request is well formed, the error code returned
           by FluidDB is returned.

           If the request is ill-formed (doesn't look like a valid namespace),
           an exception is raised.
        """
        fullPath = self.abs_tag_path(path)    # now it starts with /user
        parts = fullPath.split(u'/')[1:]       # remove '' before leading '/'
        if parts[-1] == u'':
            parts = parts       # ignore a trailing slash, if there was one
        if len(parts) < 2:     # minimum is 'user' and 'namespace'
            raise EmptyNamespaceError(u'Attempt to create user namespace %s'
                                           % fullPath)
        parent = u'/'.join(parts[:-1])
        containingNS = u'/namespaces/%s' % parent
        subNS = parts[-1]
        body = json.dumps({u'name': subNS,
                           u'description': self.decode(description)})
        status, result = self.call('POST', containingNS, body)
        if status == STATUS.CREATED:
            id = result[u'id']
            if verbose:
                print u'Created namespace /%s/%s with ID %s' % (parent,
                                        subNS, id)
            return self.encode(id)
        elif status == STATUS.NOT_FOUND:    # parent namespace doesn't exist
            if not createParentIfNeeded:
                return status
            if len(parts) > 2:
                self.create_namespace(u'/' + parent, verbose=verbose)
                return self.create_namespace(path, description,
                                              verbose=verbose)  # try again
            else:
                user = parts[-1]
                raise CannotWriteUserError(u'User %s not found or namespace '
                                '/%s not writable' % (user, user))
        else:
            if verbose:
                print u'Failed to create namespace %s (%d)' % (fullPath,
                                                                status)
            return status

    def delete_namespace(self, path, recurse=False, force=False,
                          verbose=False):
        """Deletes the namespace specified by path.

           The path, as usual in FDB, is considered absolute if it starts
           with a slash, and relative to the user's namespace otherwise.

           recurse and force are not yet implemented.
        """
        absPath = self.abs_tag_path(path)
        fullPath = u'/namespaces' + absPath
        if fullPath.endswith(u'/'):
            fullPath = fullPath[:-1]
        status, result = self.call('DELETE', fullPath)
        if verbose:
            if status == STATUS.NO_CONTENT:
                print u'Removed namespace %s' % absPath
            else:
                print u'Failed to remove namespace %s (%d)' % (absPath, status)
        return status

    def describe_namespace(self, path):
        """Returns an object describing the namespace specified by the path.

           The path, as usual in FDB, is considered absolute if it starts
           with a slash, and relative to the user's namespace otherwise.

           The object contains attributes tagNames, namespaceNames and
           path.

           If the call is unsuccessful, an error code is returned instead.
        """
        absPath = self.abs_tag_path(path)
        fullPath = u'/namespaces' + absPath
        if fullPath.endswith(u'/'):
            fullPath = fullPath[:-1]
        status, result = self.call('GET', fullPath, returnDescription=True,
                                      returnTags=True, returnNamespaces=True)
        return O(result) if status == STATUS.OK else status

    def create_abstract_tag(self, tag, description=None, indexed=True):
        """Creates an (abstract) tag with the name (full path) given.
           The tag is not applied to any object.
           If the tag's name (tag) contains slashes, namespaces are created
           as needed.

           Doesn't handle tags with subnamespaces yet.

           Returns (O) object corresponding to the tag if successful,
           otherwise an integer error code.
        """
        (user, subnamespace, tagname) = self.tag_path_split(tag)
        if subnamespace:
            fullnamespace = u'/tags/%s/%s' % (user, subnamespace)
        else:
            fullnamespace = u'/tags/%s' % user
        hash = {u'indexed': indexed, u'description': description or '',
                u'name': tagname}
        fields = json.dumps(hash)
        (status, o) = self.call('POST', fullnamespace, fields)
        if status == STATUS.NOT_FOUND:
            namespace = '/%s/%s' % (user, subnamespace)
            id = self.create_namespace(namespace)
            if type(id) in types.StringTypes:  # is an ID
                print id
                (status, o) = self.call('POST', fullnamespace, fields)
            else:
                raise FailedToCreateNamespaceError(u'FDB could not create'
                        ' the required namespace %s' % namespace)
        return O(o) if status == STATUS.CREATED else status

    def delete_abstract_tag(self, tag):
        """Deletes an abstract tag, removing all of its concrete
           instances from objects.   Use with care.
           So db.delete_abstract_tag('njr/rating') removes
           the njr/rating from ALL OBJECTS IN FLUIDDB.

           Returns 0 if successful; otherwise returns an integer error code.
        """
        fullTag = self.full_tag_path(tag)
        (status, o) = self.call('DELETE', fullTag)
        return 0 if status == STATUS.NO_CONTENT else status

    def tag_object_by_id(self, id, tag, value=None, value_type=None,
                          createAbstractTagIfNeeded=True):
        """Tags the object with the given id with the tag
           given, and the value given, if present.
           If the (abstract) tag with corresponding to the
           tag given doesn't exist, it is created unless
           createAbstractTagIfNeeded is set to False.
        """
        fullTag = self.abs_tag_path(tag)
        objTag = u'/objects/%s%s' % (self.decode(id), fullTag)

        (status, o) = self._set_tag_value(objTag, value, value_type)
        if status == STATUS.NOT_FOUND and createAbstractTagIfNeeded:
            o = self.create_abstract_tag(tag)
            if type(o) == types.IntType:       # error code
                return o
            else:
                return self.tag_object_by_id(id, tag, value, value_type, False)
        else:
            return 0 if status == STATUS.NO_CONTENT else status

    tag_object_by_about = by_about(tag_object_by_id)

    def untag_object_by_id(self, id, tag, missingConstitutesSuccess=True):
        """Removes the tag from the object with id if present.
           If the tag, or the object, doesn't exist,
           the default is that this is considered successful,
           but missingConstitutesSuccess can be set to False
           to override this behaviour.

           Returns 0 for success, non-zero error code otherwise.
        """
        fullTag = self.abs_tag_path(tag)
        objTag = u'/objects/%s%s' % (self.decode(id), fullTag)
        (status, o) = self.call('DELETE', objTag)
        ok = (status == STATUS.NO_CONTENT
                or status == STATUS.NOT_FOUND and missingConstitutesSuccess)
        return 0 if ok else status

    untag_object_by_about = by_about(untag_object_by_id)

    def get_tag_value_by_id(self, id, tag):
        """Gets the value of a tag on an object identified by the
           object's ID.

           Returns  returns a 2-tuple, in which the first component
           is the status, and the second is either the tag value,
           if the return stats is STATUS.OK, or None otherwise.
        """
        fullTag = self.abs_tag_path(tag)
        objTag = u'/objects/%s%s' % (self.decode(id), fullTag)
        status, (value, value_type) = self._get_tag_value(objTag)
        if status == STATUS.OK:
            if value_type is None:
                # A primitive Python value.
                return status, value
            else:
                raise status(value, value_type)
        else:
            return status, None

    get_tag_value_by_about = by_about(get_tag_value_by_id)

    def get_tag_values_by_id(self, id, tags):
        return [self.get_tag_value_by_id(id, tag) for tag in tags]

    def get_tag_values_by_about(self, about, tags):
        return [self.get_tag_value_by_about(about, tag) for tag in tags]

    def get_object_tags_by_id(self, id):
        """Gets the tags on an tag identified by the object's ID.

           Returns list of tags.
        """
        obj = u'/objects/%s' % self.decode(id)
        print obj
        status, (value, value_type) = self._get_tag_value(obj)
        if status == STATUS.OK:
            result = json.loads(value)
            return result[u'tagPaths']
        else:
            raise ObjectNotFoundError(u'Couldn\'t find object %s' % obj)

    get_object_tags_by_about = by_about(get_tag_value_by_id)

    def query(self, query):
        """Runs the query to get the IDs of objects satisfying the query.
           If the query is successful, the list of ids is returned, as a list;
           otherwise, an error code is returned.
        """
        (status, o) = self.call('GET', u'/objects', query=self.decode(query))
        return status if status != STATUS.OK else o[u'ids']

    def abs_tag_path(self, tag):
        """Returns the absolute path for the tag nominated,
           in the form
                /namespace/.../shortTagName
           If the already tag starts with a '/', no action is taken;
           if it doesn't, the username from the current credentials
           is added.

           if /tags/ is present at the start of the path,
           /tags is stripped off (which might be a problem if there's
           a user called tags...

           Always returns unicode.

           Examples: (assuming the user credentials username is njr):
                abs_tag_path('rating') = u'/njr/rating'
                abs_tag_path('/njr/rating') = u'/njr/rating'
                abs_tag_path('/tags/njr/rating') = u'/njr/rating'

                abs_tag_path('foo/rating') = u'/njr/foo/rating'
                abs_tag_path('/njr/foo/rating') = u'/njr/foo/rating'
                abs_tag_path('/tags/njr/foo/rating') = u'/njr/foo/rating'
        """
        tag = self.decode(tag)
        if tag == u'/about':     # special case
            return u'/fluiddb/about'
        if tag.startswith(u'/'):
            if tag.startswith(u'/tags/'):
                return tag[5:]
            else:
                return tag
        else:
            return u'/%s/%s' % (self.decode(self.credentials.username), tag)

    def full_tag_path(self, tag):
        """Returns the absolute tag path (see above), prefixed with /tag.

           Examples: (assuming the user credentials username is njr):
                full_tag_path ('rating') = '/tags/njr/rating'
                full_tag_path ('/njr/rating') = '/tags/njr/rating'
                full_tag_path ('/tags/njr/rating') = '/tags/njr/rating'
                full_tag_path('foo/rating') = '/tags/njr/foo/rating'
                full_tag_path('/njr/foo/rating') = '/tags/njr/foo/rating'
                full_tag_path('/tags/njr/foo/rating') = '/tags/njr/foo/rating'
        """
        utag = self.decode(tag)
        if tag.startswith(u'/tags/'):
            return utag
        else:
            return u'/tags%s' % self.abs_tag_path(tag)

    def tag_path_split(self, tag):
        """A bit like os.path.split, this splits any old kind of a FluidDB
           tag path into a user, a subnamespace (if there is one) and a tag.
           But unlike os.path.split, if no namespace is given,
           the one from the user credentials is returned.

           Any /tags/ prefix is discarded and the namespace is returned
           with no leading '/'.

           Examples: (assuming the user credentials username is njr):
                tag_path_split('rating') = (u'njr', u'', u'rating')
                tag_path_split('/njr/rating') = (u'njr', u'', u'rating')
                tag_path_split('/tags/njr/rating') = (u'njr', u'', u'rating')
                tag_path_split('foo/rating') = (u'njr', u'foo', u'rating')
                tag_path_split('/njr/foo/rating') = (u'njr', u'foo', u'rating')
                tag_path_split('/tags/njr/foo/rating') = (u'njr', u'foo',
                                                                  u'rating')
                tag_path_split('foo/bar/rating') = (u'njr', u'foo/bar',
                                                    u'rating')
                tag_path_split('/njr/foo/bar/rating') = (u'njr', u'foo/bar',
                                                                 u'rating')
                tag_path_split('/tags/njr/foo/bar/rating') = (u'njr',
                                                              u'foo/bar',
                                                              u'rating')

           Returns (user, subnamespace, tagname)
        """
        utag = self.decode(tag)
        if tag in (u'', u'/'):
            raise TagPathError(u'%s is not a valid tag path' % utag)
        tag = self.abs_tag_path(tag)
        parts = tag.split(u'/')
        subnamespace = u''
        tagname = parts[-1]
        if len(parts) < 3:
            raise TagPathError(u'%s is not a valid tag path' % utag)
        user = parts[1]
        if len(parts) > 3:
            subnamespace = u'/'.join(parts[2:-1])
        return (user, subnamespace, tagname)


def object_uri(id):
    """Returns the full URI for the FluidDB object with the given id."""
    return u'%s/objects/%s' % (FLUIDDB_PATH, id)


def tag_uri(namespace, tag):
    """Returns the full URI for the FluidDB tag with the given id."""
    return u'%s/tags/%s/%s' % (FLUIDDB_PATH, namespace, tag)


def get_credentials_file(unixFile=None, windowsFile=None, username=None):
    if os.name == 'posix':
        homeDir = os.path.expanduser('~')
        file = ((UNIX_USER_CREDENTIALS_FILE % username) if username
                else UNIX_CREDENTIALS_FILE)
        return os.path.join(homeDir, file)
    elif os.name:
        from win32com.shell import shellcon, shell
        homeDir = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
        file = ((WINDOWS_USER_CREDENTIALS_FILE % username) if username
                else WINDOWS_CREDENTIALS_FILE)
        return os.path.join(homeDir, file)
    else:
        return None


def get_typed_tag_value(v):
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
    if v.lower() in ('true', 't'):
        return True
    elif v.lower() in ('false', 'f'):
        return False
    elif re.match(INTEGER_RE, v):
        return int(v)
    elif re.match(DECIMAL_RE, v) or re.match(DECIMAL_RE2, v):
        try:
            r = float(v)
        except ValueError:
            return str(v)
        return r
    elif len(v) > 1 and v[0] == v[-1] and v[0] in ('"\''):
        return v[1:-1]
    else:
        return str(v)


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
    sys.stderr.write('%s\n' % msg)


def fail(msg):
    warning(msg)
    sys.exit(1)


def nothing_to_do():
    print 'Nothing to do.'
    sys.exit(0)


def cli_bracket(s):
    return '(%s)' % s


def describe_by_mode(specifier, mode):
    """mode can be a string (about, id or query) or a flags object
        with flags.about, flags.query and flags.id"""
    if mode == 'about':
        return describe_by_about(specifier)
    elif mode == 'id':
        return describe_by_id(specifier)
    elif mode == 'query':
        return describe_by_id(specifier)
    raise ModeError('Bad Mode')


def describe_by_about(specifier):
    return 'with about="%s"' % specifier


def describe_by_id(specifier):
    return specifier


def execute_tag_command(objs, db, tags, options):
    tags = form_tag_value_pairs(tags)
    actions = {
            'id': db.tag_object_by_id,
            'about': db.tag_object_by_about,
            }
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        for tag in tags:
            o = actions[obj.mode](obj.specifier, tag.name, tag.value)
            if o == 0:
                if options.verbose:
                    print('Tagged object %s with %s'
                            % (description,
                               formatted_tag_value(tag.name, tag.value)))
            else:
                warning('Failed to tag object %s with %s'
                            % (description, tag.name))
                warning('Error code %d' % o)


def execute_untag_command(objs, db, tags, options):
    actions = {
            'id': db.untag_object_by_id,
            'about': db.untag_object_by_about,
            }
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        for tag in tags:
            o = actions[obj.mode](obj.specifier, tag)
            if o == 0:
                if options.verbose:
                    print('Removed tag %s from object %s\n'
                         % (tag, description))
            else:
                warning('Failed to remove tag %s from object %s'
                            % (tag, description))
                warning('Error code %d' % o)


def formatted_tag_value(tag, value):
    if value == None:
        return tag
    elif type(value) in types.StringTypes:
        return '%s = "%s"' % (tag, value)
    else:
        return '%s = %s' % (tag, str(value))


def get_ids_or_fail(query, db):
    ids = db.query(query)
    if type(ids) == types.IntType:
        fail('Query failed')
    else:   # list of ids
        print '%s matched' % plural(len(ids), 'object')
        return ids


def execute_show_command(objs, db, tags, options):
    actions = {
            'id': db.get_tag_value_by_id,
            'about': db.get_tag_value_by_about,
            }
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        print 'Object %s:' % description

        for tag in tags:
            fulltag = db.encode(db.abs_tag_path(tag))
            if tag == '/id':
                if obj.mode == 'about':
                    o = db.query('fluiddb/about = "%s"' % obj.specifier)
                    if type(o) == types.IntType:  # error
                        status, v = o, None
                    else:
                        status, v = STATUS.OK, o[0]
                else:
                    status, v = STATUS.OK, obj.specifier
            else:
                status, v = actions[obj.mode](obj.specifier, tag)

            if status == STATUS.OK:
                print '  %s' % formatted_tag_value(fulltag, v)
            elif status == STATUS.NOT_FOUND:
                print '  %s' % cli_bracket('tag %s not present' % fulltag)
            else:
                print cli_bracket('error code %d getting tag %s' % (status,
                                                                     fulltag))


def execute_tags_command(objs, db, options):
    actions = {
        'id': db.get_tag_value_by_id,
        'about': db.get_tag_value_by_about,
    }
    for obj in objs:
        description = describe_by_mode(obj.specifier, obj.mode)
        print 'Object %s:' % description
        id = (db.create_object(obj.specifier).id if obj.mode == 'about'
              else obj.specifier)
        for tag in db.get_object_tags_by_id(id):
            fulltag = '/%s' % tag
            status, v = db.get_tag_value_by_id(id, fulltag)

            if status == STATUS.OK:
                print '  %s' % formatted_tag_value(fulltag, v)
            elif status == STATUS.NOT_FOUND:
                print '  %s' % cli_bracket('tag %s not present' % fulltag)
            else:
                print cli_bracket('error code %d getting tag %s' % (status,
                                                                    fulltag))


def execute_http_request(action, args, db, options):
    """Executes a raw HTTP command (GET, PUT, POST, DELETE or HEAD)
       as specified on the command line."""
    method = action.upper()
    if method not in HTTP_METHODS:
        raise UnrecognizedHTTPMethodError('Only supported HTTP methods are'
                '%s and %s' % (' '.join(HTTP_METHODS[:-1], HTTP_METHODS[-1])))

    if len(args) == 0:
        raise TooFewArgsForHTTPError('HTTP command %s requires a URI' % method)
    uri = args[0]
    tags = form_tag_value_pairs(args[1:])
    if method == 'PUT':
        body = {tags[0].tag: tags[0].value}
        tags = tags[1:]
    else:
        body = None
    hash = {}
    for pair in tags:
        hash[pair.name] = pair.value
    status, result = db.call(method, uri, body, hash)
    print 'Status: %d' % status
    print 'Result: %s' % str(result)


def execute_command_line(action, args, options, parser):
    db = FluidDB(host=options.hostname, debug=options.debug)

    ids_from_queries = chain(*imap(lambda q: get_ids_or_fail(q, db),
        options.query))
    ids = chain(options.id, ids_from_queries)

    objs = [O({'mode': 'about', 'specifier': a}) for a in options.about] + \
            [O({'mode': 'id', 'specifier': id}) for id in ids]

    if action == 'help':
        print USAGE
        sys.exit(0)
    elif (action.upper() not in HTTP_METHODS + ['COUNT', 'TAGS'] and not args):
        parser.error('Too few arguments for action %s' % action)
    elif action == 'count':
        print "Total: %d objects" % (len(objs))
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

        command(objs, db, tags, options)
    elif action in ['get', 'put', 'post', 'delete']:
        execute_http_request(action, args, db, options)
    else:
        parser.error('Unrecognized command %s' % action)


def choose_host():
    if 'options' in globals():
        host = options.hostname
        if options.verbose:
            print "Chosen %s as host" % host
        return host
    else:
        return FLUIDDB_PATH


def choose_debug_mode():
    return options.debug if 'options' in globals() else False


def choose_http_timeout():
    return (options.timeout if 'options' in globals() else HTTP_TIMEOUT)


class TestFluidDB(unittest.TestCase):
    db = FluidDB()
    user = db.credentials.username

    def setUp(self):
        self.db.set_connection_from_global()
        self.db.set_debug_timeout(5.0)
        self.dadgadID = id('DADGAD', self.db.host)

    def testCreateObject(self):
        db = self.db
        o = db.create_object('DADGAD')
        self.assertEqual(o.id, self.dadgadID)
        self.assertEqual(o.URI, object_uri(self.dadgadID))

    def testCreateObjectNoAbout(self):
        db = self.db
        o = db.create_object()
        self.assertEqual(type(o) != types.IntType, True)

    def testCreateObjectFail(self):
        bad = Credentials('doesnotexist', 'certainlywiththispassword')
        db = FluidDB(bad)
        o = db.create_object('DADGAD')
        self.assertEqual(o, STATUS.UNAUTHORIZED)

    def testCreateTag(self):
        db = self.db
        o = db.delete_abstract_tag('testrating')
        # doesn't really matter if this works or not

        o = db.create_abstract_tag('testrating',
                        "%s's testrating (0-10; more is better)" % self.user)
        self.assertEqual(type(o.id) in types.StringTypes, True)
        self.assertEqual(o.URI, tag_uri(db.credentials.username,
                                                'testrating'))

    def testSetTagByID(self):
        db = self.db
        user = db.credentials.username
        o = db.delete_abstract_tag('testrating')
        o = db.create_abstract_tag('testrating',
                         "%s's testrating (0-10; more is better)" % self.user)
        o = db.tag_object_by_id(self.dadgadID, '/%s/testrating' % user, 5)
        self.assertEqual(o, 0)
        _status, v = db.get_tag_value_by_id(self.dadgadID, 'testrating')
        self.assertEqual(v, 5)

    def testSetTagByAbout(self):
        db = self.db
        user = db.credentials.username
        o = db.delete_abstract_tag('testrating')
        o = db.tag_object_by_about('DADGAD', '/%s/testrating' % user, 'five')
        self.assertEqual(o, 0)
        _status, v = db.get_tag_value_by_about('DADGAD', 'testrating')
        self.assertEqual(v, 'five')

    def testDeleteNonExistentTag(self):
        db = self.db
        o = db.delete_abstract_tag('testrating')
        o = db.delete_abstract_tag('testrating')  # definitely doesn't exist

    def testSetNonExistentTag(self):
        db = self.db
        o = db.delete_abstract_tag('testrating')
        o = db.tag_object_by_id(self.dadgadID, 'testrating', 5)
        self.assertEqual(o, 0)
        status, v = db.get_tag_value_by_id(self.dadgadID, 'testrating')
        self.assertEqual(v, 5)

    def testUntagObjectByID(self):
        db = self.db

        # First tag something
        o = db.tag_object_by_id(self.dadgadID, 'testrating', 5)
        self.assertEqual(o, 0)

        # Now untag it
        error = db.untag_object_by_id(self.dadgadID, 'testrating')
        self.assertEqual(error, 0)
        status, v = db.get_tag_value_by_id(self.dadgadID, 'testrating')
        self.assertEqual(status, STATUS.NOT_FOUND)

        # Now untag it again (should be OK)
        error = db.untag_object_by_id(self.dadgadID, 'testrating')
        self.assertEqual(error, 0)

        # And again, but this time asking for error if untagged
        error = db.untag_object_by_id(self.dadgadID, 'testrating', False)
        self.assertEqual(error, STATUS.NOT_FOUND)

    def testUntagObjectByAbout(self):
        db = self.db

        # First tag something
        o = db.tag_object_by_id(self.dadgadID, 'testrating', 5)
        self.assertEqual(o, 0)

        # Now untag it
        error = db.untag_object_by_about('DADGAD', 'testrating')
        self.assertEqual(error, 0)
        status, v = db.get_tag_value_by_about('DADGAD', 'testrating')
        self.assertEqual(status, STATUS.NOT_FOUND)

    def testAddValuelessTag(self):
        db = self.db
        o = db.delete_abstract_tag('testconvtag')
        o = db.create_abstract_tag('testconvtag',
                                "a conventional (valueless) tag")
        o = db.tag_object_by_id(self.dadgadID, 'testconvtag')
        self.assertEqual(o, 0)
        status, v = db.get_tag_value_by_id(self.dadgadID, 'testconvtag')
        self.assertEqual(v, None)


class TestFDBUtilityFunctions(unittest.TestCase):
    db = FluidDB()
    user = db.credentials.username

    def setUp(self):
        self.db.set_connection_from_global()
        self.db.set_debug_timeout(5.0)
        self.dadgadID = id('DADGAD', self.db.host)

    def testFullTagPath(self):
        db = self.db
        user = db.credentials.username
        self.assertEqual(db.full_tag_path('rating'),
                          '/tags/%s/rating' % user)
        self.assertEqual(db.full_tag_path('/%s/rating' % user),
                          '/tags/%s/rating' % user)
        self.assertEqual(db.full_tag_path('/tags/%s/rating' % user),
                          '/tags/%s/rating' % user)
        self.assertEqual(db.full_tag_path('foo/rating'),
                          '/tags/%s/foo/rating' % user)
        self.assertEqual(db.full_tag_path('/%s/foo/rating' % user),
                          '/tags/%s/foo/rating' % user)
        self.assertEqual(db.full_tag_path('/tags/%s/foo/rating' % user),
                          '/tags/%s/foo/rating' % user)

    def testAbsTagPath(self):
        db = self.db
        user = db.credentials.username
        self.assertEqual(db.abs_tag_path('rating'), '/%s/rating' % user)
        self.assertEqual(db.abs_tag_path('/%s/rating' % user),
                          '/%s/rating' % user)
        self.assertEqual(db.abs_tag_path('/tags/%s/rating' % user),
                          '/%s/rating' % user)
        self.assertEqual(db.abs_tag_path('foo/rating'),
                          '/%s/foo/rating' % user)
        self.assertEqual(db.abs_tag_path('/%s/foo/rating' % user),
                          '/%s/foo/rating' % user)
        self.assertEqual(db.abs_tag_path('/tags/%s/foo/rating' % user),
                          '/%s/foo/rating' % user)

    def testTagPathSplit(self):
        db = self.db

        user = db.credentials.username
        self.assertEqual(db.tag_path_split('rating'), (user, '', 'rating'))
        self.assertEqual(db.tag_path_split('/%s/rating' % user),
                         (user, '', 'rating'))
        self.assertEqual(db.tag_path_split('/tags/%s/rating' % user),
                         (user, '', 'rating'))
        self.assertEqual(db.tag_path_split('foo/rating'),
                         (user, 'foo', 'rating'))
        self.assertEqual(db.tag_path_split('/%s/foo/rating' % user),
                         (user, 'foo', 'rating'))
        self.assertEqual(db.tag_path_split('/tags/%s/foo/rating' % user),
                         (user, 'foo', 'rating'))
        self.assertEqual(db.tag_path_split('foo/bar/rating'),
                               (user, 'foo/bar', 'rating'))
        self.assertEqual(db.tag_path_split('/%s/foo/bar/rating' % user),
                         (user, 'foo/bar', 'rating'))
        self.assertEqual(db.tag_path_split('/tags/%s/foo/bar/rating' % user),
                         (user, 'foo/bar', 'rating'))
        self.assertRaises(TagPathError, db.tag_path_split, '')
        self.assertRaises(TagPathError, db.tag_path_split, '/')
        self.assertRaises(TagPathError, db.tag_path_split, '/foo')

    def testTypedValueInterpretation(self):
        corrects = {
                'TRUE': (True, types.BooleanType),
                'tRuE': (True, types.BooleanType),
                't': (True, types.BooleanType),
                'T': (True, types.BooleanType),
                'f': (False, types.BooleanType),
                'false': (False, types.BooleanType),
                '1': (1, types.IntType),
                '+1': (1, types.IntType),
                '-1': (-1, types.IntType),
                '0': (0, types.IntType),
                '+0': (0, types.IntType),
                '-0': (0, types.IntType),
                '123456789': (123456789, types.IntType),
                '-987654321': (-987654321, types.IntType),
                '011': (11, types.IntType),
                '-011': (-11, types.IntType),
                '3.14159': (float("3.14159"), types.FloatType),
                '-3.14159': (float("-3.14159"), types.FloatType),
                '.14159': (float(".14159"), types.FloatType),
                '-.14159': (float("-.14159"), types.FloatType),
                '"1"': ("1", types.StringType),
                "DADGAD": ("DADGAD", types.StringType),
                "": ("", types.StringType),
                '1,300': ("1,300", types.StringType),  # locale?
                '.': (".", types.StringType),  # locale?
                '+.': ("+.", types.StringType),  # locale?
                '-.': ("-.", types.StringType),  # locale?
                '+': ("+", types.StringType),  # locale?
                '-': ("-", types.StringType),  # locale?
        }
        for s in corrects:
            target, targetType = corrects[s]
            v = get_typed_tag_value(s)
            self.assertEqual((s, v), (s, target))
            self.assertEqual((s, type(v)), (s, targetType))


class SaveOut:
    def __init__(self):
        self.buffer = []

    def write(self, msg):
        self.buffer.append(msg)

    def clear(self):
        self.buffer = []


def specify_DADGAD(mode, host):
    if mode == 'about':
        return ('-a', 'DADGAD')
    elif mode == 'id':
        return ('-i', id('DADGAD', host))
    elif mode == 'query':
        return ('-q', 'fluiddb/about="DADGAD"')
    else:
        raise ModeError('Bad mode')


class TestCLI(unittest.TestCase):
    db = FluidDB()
    user = db.credentials.username

    def setUp(self):
        self.db.set_connection_from_global()
        self.db.set_debug_timeout(5.0)
        self.dadgadID = id('DADGAD', self.db.host)
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        self.stealOutput()

    def stealOutput(self):
        self.out = SaveOut()
        self.err = SaveOut()
        sys.stdout = self.out
        sys.stderr = self.err

    def reset(self):
        sys.stdout = self.stdout
        sys.stderr = self.stderr

    def Print(self, msg):
        self.stdout.write(str(msg) + '\n')

    def testOutputManipulation(self):
        print 'one'
        sys.stderr.write('two')
        self.reset()
        self.assertEqual(self.out.buffer, ['one', '\n'])
        self.assertEqual(self.err.buffer, ['two'])

    def tagTest(self, mode, verbose=True):
        self.stealOutput()
        (flag, spec) = specify_DADGAD(mode, self.db.host)
        description = describe_by_mode(spec, mode)
        flags = ['-v', flag] if verbose else [flag]
        hostname = ['--hostname', choose_host()]
        args = ['tag'] + flags + [spec, 'rating=10'] + hostname
        execute_command_line(*parse_args(args))
        self.reset()
        if verbose:
            target = ['Tagged object %s with rating = 10' % description, '\n']
        else:
            if mode == 'query':
                target = ['1 object matched', '\n']
            else:
                target = []
        self.assertEqual(self.out.buffer, target)
        self.assertEqual(self.err.buffer, [])

    def untagTest(self, mode, verbose=True):
        self.stealOutput()
        (flag, spec) = specify_DADGAD(mode, self.db.host)
        description = describe_by_mode(spec, mode)
        flags = ['-v', flag] if verbose else [flag]
        hostname = ['--hostname', choose_host()]
        args = ['untag'] + flags + [spec, 'rating'] + hostname
        execute_command_line(*parse_args(args))
        self.reset()
        if verbose:
            target = ['Removed tag rating from object %s\n' % description,
                      '\n']
        else:
            target = []
        self.assertEqual(self.out.buffer, target)
        self.assertEqual(self.err.buffer, [])

    def showTaggedSuccessTest(self, mode):
        self.stealOutput()
        (flag, spec) = specify_DADGAD(mode, self.db.host)
        description = describe_by_mode(spec, mode)
        hostname = ['--hostname', choose_host()]
        args = (['show', '-v', flag, spec, 'rating', '/fluiddb/about']
                + hostname)
        execute_command_line(*parse_args(args))
        self.reset()
        self.assertEqual(self.out.buffer,
                ['Object %s:' % description, '\n',
                 '  /%s/rating = 10' % self.user, '\n',
                 '  /fluiddb/about = "DADGAD"', '\n'])
        self.assertEqual(self.err.buffer, [])

    def showUntagSuccessTest(self, mode):
        self.stealOutput()
        (flag, spec) = specify_DADGAD(mode, self.db.host)
        description = describe_by_mode(spec, mode)
        hostname = ['--hostname', choose_host()]
        args = (['show', '-v', flag, spec, 'rating', '/fluiddb/about']
                 + hostname)
        execute_command_line(*parse_args(args))
        self.reset()
        user = self.db.credentials.username
        self.assertEqual(self.out.buffer,
                ['Object %s:' % description, '\n',
                 '  %s' % cli_bracket('tag /%s/rating not present' % user),

                '\n', '  /fluiddb/about = "DADGAD"', '\n'])
        self.assertEqual(self.err.buffer, [])

    def testTagByAboutVerboseShow(self):
        self.tagTest('about')
        self.showTaggedSuccessTest('about')

    def testTagByIDVerboseShow(self):
        self.tagTest('id')
        self.showTaggedSuccessTest('id')

    def testTagByQueryVerboseShow(self):
        self.tagTest('query', verbose=False)
        self.showTaggedSuccessTest('id')

    def testTagSilent(self):
        self.tagTest('about', verbose=False)
        self.showTaggedSuccessTest('about')

    def testUntagByAboutVerboseShow(self):
        self.untagTest('about')
        self.showUntagSuccessTest('about')

    def testUntagByIDVerboseShow(self):
        self.untagTest('id')
        self.showUntagSuccessTest('id')


def parse_args(args=None):
    if args is None:
        args = sys.argv[1:]
    parser = OptionParser(usage=USAGE)
    general = OptionGroup(parser, "General options")
    general.add_option("-a", "--about", action="append", default=[],
            help="used to specify objects by about tag")
    general.add_option("-i", "--id", action="append", default=[],
            help="used to specify objects by ID")
    general.add_option("-q", "--query", action="append", default=[],
            help="used to specify objects with a FluidDB query")
    general.add_option("-v", "--verbose", action="store_true", default=False,
            help="encourages FDB to report what it's doing (verbose mode)")
    general.add_option("-D", "--debug", action="store_true", default=False,
            help="enables debug mode (more output)")
    general.add_option("-T", "--timeout", type="float", default=HTTP_TIMEOUT,
            metavar="n", help="sets the HTTP timeout to n seconds")
    parser.add_option_group(general)

    other = OptionGroup(parser, "Other flags")
    other.add_option("-s", "--sandbox", action="store_const", dest="hostname",
            const=SANDBOX_PATH,
            help="use the sandbox at http://sandbox.fluidinfo.com")
    other.add_option("--hostname", default=FLUIDDB_PATH, dest="hostname",
            help="use the specified host (which should start http:// or "\
                    "https://; http:// will be added if it doesn't) default "\
                    "is %default")
    parser.add_option_group(other)

    options, args = parser.parse_args(args)

    if args == []:
        action = 'help'
    else:
        action, args = args[0], args[1:]

    return action, args, options, parser


def plural(n, s, pl=None, str=False, justTheWord=False):
    """Returns a string like '23 fields' or '1 field' where the
        number is n, the stem is s and the plural is either stem + 's'
        or stem + pl (if provided)."""
    smallints = ['zero', 'one', 'two', 'three', 'four', 'five',
                         'six', 'seven', 'eight', 'nine', 'ten']

    if pl == None:
        pl = 's'
    if str and n < 10 and n >= 0:
        strNum = smallints[n]
    else:
        strNum = int(n)
    if n == 1:
        if justTheWord:
            return s
        else:
            return ('%s %s' % (strNum, s))
    else:
        if justTheWord:
            return '%s%s' % (s, pl)
        else:
            return ('%s %s%s' % (strNum, s, pl))


if __name__ == '__main__':
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
        unittest.TextTestRunner(verbosity=1).run(suite)
    else:
        execute_command_line(action, args, options, parser)
