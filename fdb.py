# fdb.py
#
# By Nicholas J. Radcliffe, Stochasic Solutions Limited.
#     building on fluiddb.py by Sanghyeon Seo and Nicholas Tollervey,
#     which is available from
#         http://bitbucket.org/sanxiyn/fluidfs/
#
#
# 2008/08/20 v0.1       Initial version.   6 tests pass
#                       Used to import 1456 objects from delicious sucessfully
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
#
# Notes: 
#
#       Credentials (username and password) are normally read from
#       a plain text credentials file, or can be passed in explicitly.
#       I store mine in ~/.fluidDBcredentials.   The format is plain text
#       with the username on the first line and the password on the second,
#       no whitespace.   Any further lines are ignored.
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

__version__ = '0.2'

import unittest, os, types, sys, httplib2, urllib
import fluiddb
if sys.version_info < (2, 6):
    import simplejson as json
else:
    import json

class ProblemReadingCredentialsFileError (Exception): pass
class BadCredentialsError (Exception): pass
class CredentialsFileNotFoundError (Exception): pass
class NotHandledYetError (Exception): pass
class TagPathError (Exception): pass

class STATUS:
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    INTERNAL_SERVER_ERROR = 500
    NOT_FOUND = 404

FLUIDDB_PATH = 'http://fluidDB.fluidinfo.com'


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

class Credentials:
    """Simple store for user credentials.
        Can be initialized with username and password
        or by pointing to a file (filename) with the username
        on the first line and the password on the second line.
    """
    def __init__ (self, username=None, password=None, id=None, filename=None):
        if username:
            self.username = username
            self.password = password
        elif filename:
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
                
        else:
            raise BadCredentialsError, ('Neither a username nor a valid '
                        'credentials file was provided.')
            
        self.id = id

class FluidDB:
    """Connection to FluidDB that remembers credentials and provides
        methods for some of the common operations."""

    def __init__ (self, credentials):
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
            jAbout = None
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
                'name' : tag}
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
        fullTag = self.abs_tag_path (tag)
        hash = {'value' : value}
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
            return status, o['value']
        else:
            return status, None

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

class TestFluidDB (unittest.TestCase):
    CREDENTIALS_FILE = '/Users/njr/.fluidDBcredentials'
    DADGAD_ID = 'a984efb2-67d8-4b5c-86d0-267b87832fa4'

    def testCreateObject (self):
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
        o = db.create_object ('DADGAD')
        self.assertEqual (o.id, self.DADGAD_ID)
        self.assertEqual (o.URI, object_uri (self.DADGAD_ID))

    def testCreateObjectFail (self):
        bad = Credentials ('doesnotexist', 'certainlywiththispassword')
        db = FluidDB (bad)
        o = db.create_object ('DADGAD')
        self.assertEqual (o, STATUS.INTERNAL_SERVER_ERROR)

    def testCreateTag (self):
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
        o = db.delete_abstract_tag ('testrating')
        # doesn't really matter if this works or not

        o = db.create_abstract_tag ('testrating',
                                "njr's testrating (0-10; more is better)")
        self.assertEqual (type (o.id) in types.StringTypes, True)
        self.assertEqual (o.URI, tag_uri (db.credentials.username,
                                                'testrating'))

    def testSetTag (self):
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
        user = db.credentials.username
        o = db.delete_abstract_tag ('testrating')
        o = db.create_abstract_tag ('testrating',
                                "njr's testrating (0-10; more is better)")
        o = db.tag_object_by_id (self.DADGAD_ID, '/%s/testrating' % user, 5)
        self.assertEqual (o, 0)
        status, v = db.get_tag_value_by_id (self.DADGAD_ID, 'testrating')
        self.assertEqual (v, 5)

    def testSetNonExistentTag (self):
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
        o = db.delete_abstract_tag ('testrating')
        o = db.tag_object_by_id (self.DADGAD_ID, 'testrating', 5)
        self.assertEqual (o, 0)
        status, v = db.get_tag_value_by_id (self.DADGAD_ID, 'testrating')
        self.assertEqual (v, 5)

    def testUntagObject (self):
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))

        # First tag something
        o = db.tag_object_by_id (self.DADGAD_ID, 'testrating', 5)
        self.assertEqual (o, 0)

        # Now untag it
        error = db.untag_object_by_id (self.DADGAD_ID, 'testrating')
        self.assertEqual (error, 0)
        status, v = db.get_tag_value_by_id (self.DADGAD_ID, 'testrating')
        self.assertEqual (status, STATUS.NOT_FOUND)

        # Now untag it again (should be OK)
        error = db.untag_object_by_id (self.DADGAD_ID, 'testrating')
        self.assertEqual (error, 0)

        # And again, but this time asking for error if untagged
        error = db.untag_object_by_id (self.DADGAD_ID, 'testrating', False)
        self.assertEqual (error, STATUS.NOT_FOUND)

        


    def testAddValuelessTag (self):
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
        o = db.delete_abstract_tag ('testconvtag')
        o = db.create_abstract_tag ('testconvtag',
                                "a conventional (valueless) tag")
        o = db.tag_object_by_id (self.DADGAD_ID, 'testconvtag')
        self.assertEqual (o, 0)
        status, v = db.get_tag_value_by_id (self.DADGAD_ID, 'testconvtag')
        self.assertEqual (v, None)

    def testFullTagPath (self):
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
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
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
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
        db = FluidDB (Credentials (filename=self.CREDENTIALS_FILE))
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


if __name__ == '__main__':
    unittest.main ()
