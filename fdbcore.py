# -*- coding: utf-8 -*-
#
# fdbcore.py
#
# Copyright (c) Nicholas J. Radcliffe 2009-2011 and other authors specified
#               in the AUTHOR
# Licence terms in LICENCE.

__version__ = '1.31'

import os
import re
import sys
import types
import urllib
from functools import wraps
from httplib2 import Http

if sys.version_info < (2, 6):
    import simplejson as json
else:
    import json


DADGAD_ID = u'ca0f03b5-3c0d-4c00-aa62-bdb07f29599c'
UNICODE = False
toStr = unicode if UNICODE else str


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


class BadStatusError(Exception):
    pass


class NonUnicodeStringError(Exception):
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
    """
    This is really a dummy class that just sticks everything in
    the hash (dictionary) that initializes it into self.dict
    so that you can use o.id instead of hash['id'] etc.,
    and to allow some string formatting etc.

    Most objects returned natively as hashes by the FluidDB API
    are mapped to these dummy objects in this library.
    """
    def __init__(self, hash=None):
        if hash:
            for k in hash:
                self.__dict__[k] = hash[k]

    def __str__(self):
        keys = self.__dict__.keys()
        keys.sort()
        return '\n'.join(['%20s: %s' % (key, toStr(self.__dict__[key]))
                                for key in keys])

    def __unicode__(self):
        keys = self.__dict__.keys()
        keys.sort()
        return u'\n'.join([u'%20s: %s' % (key, unicode(self.__dict__[key]))
                           for key in keys])


class Credentials:
    """
    Simple store for user credentials.
    Can be initialized with username and password
    or by pointing to a file (filename) with the username
    on the first line and the password on the second line.
    If neither password nor filename is given,
    the default credentials file will be used, if available.
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
                            ' credentials from %s.' % toStr(filename))
            else:
                raise CredentialsFileNotFoundError('Couldn\'t find or '
                            'read credentials from %s.' % toStr(filename))

        self.id = id


class FluidDB:
    """
    Connection to FluidDB that remembers credentials and provides
    methods for some of the common operations.
    """

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
            url = '%s?%s' % (url, urllib.urlencode(hash, True))
        elif kw:
            url = '%s?%s' % (url, urllib.urlencode(kw, True))
#        print url
        return self.decode(url)

    def set_connection_from_global(self):
        """
        Sets the host on the basis of the global variable flags,
        if that exists.   Used to enable the tests to run against
        alternate hosts.
        """
        self.host = choose_host()
        self.debug = choose_debug_mode()
        self.timeout = choose_http_timeout()

    def set_debug_timeout(self, v):
        if self.timeout == HTTP_TIMEOUT:
            self.timeout = float(v)

    def call(self, method, path, body=None, hash=None, **kw):
        """
        Calls FluidDB with the attributes given.
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
            print u'status: %d; content: %s' % (status, toStr(result))
            if status >= 400:
                for header in response:
                    if header.lower().startswith(u'x-fluiddb-'):
                        print u'\t%s=%s' % (header, response[header])

        return status, result

    def encode(self, value):
        """
        Encode value in chosen encoding if the value is unicode
        and the chosen encoding is not unicode.
        """
        if type(value) == unicode and not self.encoding == 'unicode':
            return value.encode(self.encoding)
        else:
            return value

    def decode(self, value):
        """
        Decode value from chosen encoding into unicode if the
        value is a string.
        """
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
        """
        Creates an object with the about tag given.
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
        """
        Creates the namespace specified by path using the description
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
            return toStr(v)
        return r
    elif len(v) > 1 and v[0] == v[-1] and v[0] in ('"\''):
        return v[1:-1]
    else:
        return toStr(v)


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


#
# VALUES API:
#
# Note: these calls are different from the rest of fdb.py (at present)
# in that (1) they used full Fluidinfo paths with no leading slash,
# and (2) they use unicode throughout (3) tags must exist before being used.
# Things will be made more consistent over time.
#

def format_val(s):
    """
    Formats a value for json (unicode).
    """
    if type(s) == type('s'):
        raise NonUnicodeStringError
    elif type(s) == unicode:
        if s.startswith(u'"') and s.endsswith(u'"'):
            return s
        else:
            return u'"%s"' % s
    elif type(s) == bool:
        return unicode(s).lower()
    else:
        return unicode(s)


def to_typed(v):
    """
    Turns json-formatted string into python value.
    Unicode.
    """
    L = v.lower()
    if v.startswith(u'"') and v.startswith(u'"') and len(v) >= 2:
        return v[1:-1]
    elif v.startswith(u"'") and v.startswith(u"'") and len(v) >= 2:
        return v[1:-1]
    elif L == u'true':
        return True
    elif L == u'false':
        return False
    elif re.match(INTEGER_RE, v):
        return int(v)
    elif re.match(DECIMAL_RE, v) or re.match(DECIMAL_RE2, v):
        try:
            r = float(v)
        except ValueError:
            return unicode(v)
        return r
    else:
        return unicode(v)


def tag_by_query(db, query, tagsToSet):
    """
    Sets one or more tags on objects that match a query.

    db         is an instantiated FluidDB instance.

    query      is a unicode string representing a valid Fluidinfo query.
               e.g. 'has njr/rating'

    tagsToSet  is a dictionary containing tag names (as keys)
               and values to be set.   (Use None to set a tag with no value.)

    Example:

        db = FluidDB()
        tag_by_query(db, u'has njr/rating', {'njr/rated': True})

    sets an njr/rated tag to True for every object having an njr/rating.

    NOTE: Unlike in much of the rest of fdb.py, tags need to be full paths
    without a leading slash.   (This will change.)

    NOTE: Tags must exist before being used.   (This will change.)

    NOTE: All strings must be (and will be) unicode.


    """
    strHash = u'{%s}' % u', '.join(u'"%s": {"value": %s}'
                                   % (tag, format_val(tagsToSet[tag]))
                                   for tag in tagsToSet)
    (v, r) = db.call(u'PUT', u'/values', strHash, {u'query': query})
    assert_status(v, STATUS.NO_CONTENT)


def assert_status(v, s):
    if not v == s:
        raise BadStatusError('Bad status %d (expected %d)' % (v, s))


def get_values(db, query, tags):
    """
    Gets the values of a set of tags satisfying a given query.
    Returns them as a dictionary (hash) keyed on object ID.
    The values in the dictionary are simple objects with each tag
    value in the object's dictionary (__dict__).

    db         is an instantiated FluidDB instance.

    query      is a unicode string representing a valid Fluidinfo query.
               e.g. 'has njr/rating'

    tags       is a list (or tuple) containing the tags whose values are
               required.

    Example:

        db = FluidDB()
        tag_by_query(db, u'has njr/rating < 3', ('fluiddb/about',))

    NOTE: Unlike in much of the rest of fdb.py, tags need to be full paths
    without a leading slash.   (This will change.)

    NOTE: All strings must be (and will be) unicode.

    """
    (v, r) = db.call(u'GET', u'/values', None, {u'query': query,
                                                u'tag': tags})
    assert_status(v, STATUS.OK)
    H = r[u'results'][u'id']
    results = []
    for id in H:
        o = O()
        o.__dict__[u'id'] = id
        for tag in tags:
            o.__dict__[tag] = H[id][tag][u'value']
        results.append(o)
    return results      # hash of objects, keyed on ID, with attributes
                        # corresponding to tags, inc id.
        

