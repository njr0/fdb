# -*- coding: utf-8 -*-
#
# testfdb.py
#
# Copyright (c) Nicholas J. Radcliffe 2009-2011 and other authors specified
#               in the AUTHOR
# Licence terms in LICENCE.
#
import unittest
from fdblib import *
from cli import *

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
        self.assertEqual(error, 0)  # The API has changed so that in fact
                                    # a 204 (NO CONTENT) is always returned,
                                    # so this test and the flag are now
                                    # less meaningful.
                                    # For now, just updated to be consistent
                                    # with the latest API.
                                    

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
                u'TRUE': (True, bool),
                u'tRuE': (True, bool),
                u't': (True, bool),
                u'T': (True, bool),
                u'f': (False, bool),
                u'false': (False, bool),
                u'1': (1, int),
                u'+1': (1, int),
                u'-1': (-1, int),
                u'0': (0, int),
                u'+0': (0, int),
                u'-0': (0, int),
                u'123456789': (123456789, int),
                u'-987654321': (-987654321, int),
                u'011': (11, int),
                u'-011': (-11, int),
                u'3.14159': (float('3.14159'), float),
                u'-3.14159': (float('-3.14159'), float),
                u'.14159': (float('.14159'), float),
                u'-.14159': (float('-.14159'), float),
                u'"1"': ('1', unicode),
                u'DADGAD': ('DADGAD', unicode),
                u'': ('', unicode),
                u'1,300': ('1,300', unicode),
                u'.': ('.', unicode),
                u'+.': ('+.', unicode),
                u'-.': ('-.', unicode),
                u'+': ('+', unicode),
                u'-': ('-', unicode),
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
        self.stdout.write(toStr(msg) + '\n')

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
        args = ['tag'] + ['-U'] + flags + [spec, 'rating=10'] + hostname
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
        args = ['untag'] + ['-U'] + flags + [spec, 'rating'] + hostname
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
        args = (['show', '-U', '-v', flag, spec, 'rating', '/fluiddb/about']
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
        args = (['show', '-U', '-v', flag, spec, 'rating', '/fluiddb/about']
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

if __name__ == '__main__':
    unittest.main()

