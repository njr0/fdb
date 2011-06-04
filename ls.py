import math
import sys
import types
from fdb import STATUS
import fdb
import fdblib

if sys.version_info < (2, 6):
    import simplejson as json
else:
    import json


class PermissionDesc:
    def __init__(self, entity, path, actions, names):
        self.entity = entity
        self.path = path
        self.actions = actions + ['control']
        self.names = names + ['control']


RAW_PERMS = {
    'abstract-tag': PermissionDesc('abstract-tag', 'tags',
                                   ['update', 'delete'],
                                   ['metadata', 'delete']),
    'tag': PermissionDesc('tag', 'tag-values',
                          ['create', 'read', 'delete'],
                          ['tag', 'read', 'untag']),
    'namespace': PermissionDesc('namespace', 'namespaces',
                                ['create', 'update', 'delete', 'list'],
                                ['create', 'metadata', 'delete', 'read'])
}

RAW_PERM_ENTITIES = RAW_PERMS.keys()


class FDBPerm:
    def __init__(self, name):
        self.name = 'read'
        self.tag = None
        self.namepspace = None

    def tag_map(self, perm):
        self.tag = perm

    def namespace_map(self, perm):
        self.ns = perm

READ = FDBPerm('read')
READ.tag_map({'tag-values': ['see', 'read']})
READ.namespace_map({'namespaces': ['list']})

WRITE = FDBPerm('write')
WRITE.tag_map({'tag-values': ['create', 'update', 'delete']})
WRITE.namespace_map({'namespaces': ['create']})

ADMINISTER = FDBPerm('administer')
ADMINISTER.tag_map({'tags': ['update', 'delete']})
ADMINISTER.namespace_map({'namespaces': ['update', 'delete']})


def string_format(n):
    return '%%-%ds' % n


def to_string_grid(items, pageWidth=78, maxCols=9):
    if items == []:
        return ''
    widest = max([len(s) for s in items])
    nCols = min(max(pageWidth / (widest + 1), 1), maxCols)
    colWidth = int(math.ceil(float(pageWidth) / nCols)) - 1
    fmt = string_format(colWidth)
    nItems = len(items)
    nRows = int(math.ceil(float(nItems) / nCols))

    return '\n'.join([' '.join([fmt % items[col * nRows + row]
                           for col in range(nCols)
                               if col * nRows + row < nItems])
                                   for row in range(nRows)])


class ExtendedFluidDB(fdb.FluidDB):
    def __init__(self, credentials=None, host=None, debug=False,
                 encoding=fdblib.DEFAULT_ENCODING, unixStylePaths=None):
        fdb.FluidDB.__init__(self, credentials, host, debug,
                             encoding, unixStylePaths)

    def list_namespace(self, ns, returnDescription=True,
                        returnNamespaces=True, returnTags=True):
        status, content = self.call('GET', '/namespaces/%s' % ns, None,
                                    returnDescription=returnDescription,
                                    returnNamespaces=returnNamespaces,
                                    returnTags=returnTags)
        return content if status == STATUS.OK else status

    def list_r_namespace(self, rootns):
        L = self.list_namespace(rootns, returnDescription=False)
        if L == fdb.STATUS.NOT_FOUND:
            return fdb.STATUS.NOT_FOUND
        if type(L) == int:
            return {'namespaceNames': [], 'tagNames': [], 'failures': True}
        failures = False
        namespaces = ['%s/%s' % (rootns, space)
                        for space in L['namespaceNames']]
        tags = ['%s/%s' % (rootns, tag) for tag in L['tagNames']]
        subns = []
        subtags = []
        for s in namespaces:
            L = self.list_namespace(s, returnDescription=False)
            if type(L) == int:
                failures = True
            else:
                subns.extend(['%s/%s' % (s, space)
                                  for space in L['namespaceNames']])
                subtags.extend(['%s/%s' % (s, space)
                                  for space in L['tagNames']])
        namespaces.extend(subns)
        tags.extend(subtags)
        return {'namespaceNames': namespaces, 'tagNames': tags,
                'failures': failures}

    def rm_r(self, rootns):
        L = self.list_r_namespace(rootns)
        if L == fdb.STATUS.NOT_FOUND:
            return L
        elif L['failures']:
            return 1            # non-zero failure code
        # First delete all the tags & sub-namespaces
        for items, fn in ((L['tagNames'], self.delete_abstract_tag),
                          (L['namespaceNames'], self.delete_namespace)):
            si = [(i.split('/'), i) for i in items]
            z = [(len(s), i) for (s, i) in si]
            z.sort()
            z.reverse()
            failed = False
            for (n, i) in z:
                r = self.delete_abstract_tag('/%s' % i)
                failed = failed or (r != fdb.STATUS.NO_CONTENT)
        if failed:
            return 1
        return self.delete_namespace('/' + rootns)

    def list_sorted_ns(self, ns, long_=False, columns=True, recurse=False,
                       prnt=False):
        h = self.list_namespace(ns)
        return self.list_sorted_nshash(h, ns, long_, columns, recurse,
                                       prnt=prnt)

    def list_sorted_nshash(self, h, ns, long_=False, columns=True,
                           recurse=False, prnt=False):
        if type(h) == types.IntType:
            if h == STATUS.UNAUTHORIZED:
                return 'Permission denied.'
            else:
                return 'Error status %s' % h

        tagNames = h['tagNames']
        tagNames.sort()
        spaces = h['namespaceNames']
        spaces.sort()
        items = tagNames[:] + ['%s/' % space for space in spaces]
        items.sort()
        if items:
            fmt = string_format(max([len(item) for item in items]))
        if recurse:
            print '\n%s:' % ns
        if long_:
            res = []
            for item in items:
                r = '%s   %s' % (self.perms_string(ns + '/' +  fmt % item),
                                 fmt % item)
                res.append(r)
                if prnt:
                    print r
            result = '\n'.join(res)
        elif columns == False:
            result = '\n'.join(items)
            if prnt:
                print result
        else:
            result = to_string_grid(items)
            if prnt:
                print result
        if recurse:
            others = '\n'.join([self.list_sorted_ns('%s/%s' % (ns, space),
                                        long_, columns, recurse, prnt=prnt)
                                        for space in spaces])
            return '%s:\n%s\n\n%s' % (ns, result, others)
        else:
            return result

    def get_raw_perm(self, entity, name, action):
        assert entity in RAW_PERM_ENTITIES
        perm = RAW_PERMS[entity]
        assert action in perm.actions
        path = '/permissions/%s/%s' % (perm.path, name)
        status, content = self.call('GET', path, None, action=action)
        return content if status == STATUS.OK else status

    def get_tag_perms_hash(self, tag):
        h = {}
        for entity in ['abstract-tag', 'tag']:
            desc = RAW_PERMS[entity]
            for (action, name) in zip(desc.actions, desc.names):
                h[name] = self.get_raw_perm(entity, tag, action)
        return h

    def get_ns_perms_hash(self, ns):
        h = {}
        for entity in ['namespace']:
            desc = RAW_PERMS[entity]
            for (action, name) in zip(desc.actions, desc.names):
                h[name] = self.get_raw_perm(entity, ns, action)
        return h

    def tag_perms_string(self, tag):
        h = self.get_tag_perms_hash(tag)
        s = []
        owner = tag.split('/')[0]
        r = h['read']
        writes = (h['tag'], h['untag'], h['metadata'], h['delete'])
        ownerRead = ('r' if r['policy'] == 'open' or owner in r['exceptions']
                         else '-')
        ownerWrites = [w['policy'] == 'open' or owner in w['exceptions']
                       for w in writes]
        worldRead = 'r' if r['policy'] == 'open' else '-'
        worldWrites = [w['policy'] == 'open' for w in writes]
        ownerWrite = write_status(ownerWrites)
        worldWrite = write_status(worldWrites)
 
        return '-%s%sc---%s%s-' % (ownerRead, ownerWrite,
                                   worldRead, worldWrite)
    def ns_perms_string(self, ns):
        h = self.get_ns_perms_hash(ns)
        s = []
        owner = ns.split('/')[0]
        r = h['read']
        writes = (h['create'], h['metadata'], h['delete'])
        ownerRead = ('r' if r['policy'] == 'open' or owner in r['exceptions']
                         else '-')
        ownerWrites = [w['policy'] == 'open' or owner in w['exceptions']
                       for w in writes]
        worldRead = 'r' if r['policy'] == 'open' else '-'
        worldWrites = [w['policy'] == 'open' for w in writes]
        ownerWrite = write_status(ownerWrites)
        worldWrite = write_status(worldWrites)
 
        return 'n%s%sc---%s%s-' % (ownerRead, ownerWrite,
                                   worldRead, worldWrite)

    def perms_string(self, tagOrNS):
        tagOrNS = tagOrNS.strip()
        if tagOrNS.endswith('/'):
            return self.ns_perms_string(tagOrNS[:-1])
        else:
            return self.tag_perms_string(tagOrNS)
                
    def set_raw_perm(self, entity, name, action, policy, exceptions):
        assert entity in RAW_PERM_ENTITIES
        perm = RAW_PERMS[entity]
        assert action in perm.actions
        assert policy in ('open', 'closed')
        assert not type(exceptions) in types.StringTypes  # forgot the []
        body = json.dumps({'policy': policy, 'exceptions': exceptions})
        path = '/permissions/%s/%s' % (perm.path, name)
        status, content = self.call('PUT', path, body, action=action)
        return 0 if status == STATUS.NO_CONTENT else status


def write_status(writes):
    if sum(writes) == len(writes):
        return 'w'
    else:
         return '-' if sum(writes) == 0 else '.'


def execute_ls_command(objs, tags, options):
    credentials = Credentials(options.user[0]) if options.user else None
    db = ExtendedFluidDB(host=options.hostname, credentials=credentials,
                         debug=options.debug,
                         unixStylePaths=fdblib.path_style(options))

    if len(tags) == 0:
        fulltag = db.abs_tag_path('', inPref=True)[:-1]
    else:
        fulltag = db.abs_tag_path(tags[0], inPref=True)
    if options.namespace:
        if db.ns_exists(fulltag):
            perms = ((db.perms_string(db.abs_tag_path(fulltag,
                                                      inPref=True)[1:] + '/')
                     + '   ') if options.long else '')
            nsResult = perms + tags[0]
            print nsResult
        else:
            nsResult = 'Not Found'
    else:
        nsResult = db.list_sorted_ns(fulltag[1:], long_=options.long,
                                     recurse=options.recurse, prnt=True)
    tagExists = db.tag_exists(fulltag)
    if nsResult == 'Error status 404':
        if not tagExists:
            print '%s not found' % db.abs_tag_path(fulltag, inPref=True)
    if tagExists:
        perms = ((db.perms_string(db.abs_tag_path(fulltag, inPref=True)[1:])
                  + '   ') if options.long else '')
        print perms + tags[0]


if __name__ == '__main__':
    db = ExtendedFluidDB()
    testdb = ExtendedFluidDB()
    testdb.credentials = fdb.Credentials('test', 'test')

    user = db.credentials.username
    if 0:
        assert db.set_raw_perm('tag', '%s/rating' % user, 'read', 'open',
                                ['test']) == 0
        print db.get_raw_perm('abstract-tag', '%s/rating' % user, 'update')
        print db.get_raw_perm('tag', '%s/rating' % user, 'read')
        print db.get_raw_perm('namespace', '%s' % user, 'update')

        assert (db.set_raw_perm('tag', '%s/rating' % user, 'read', 'open', [])
                == 0)
        print db.get_raw_perm('tag', '%s/rating' % user, 'read')

    # First get rid of any existing namespace

    print db.list_sorted_ns('njr', recurse=True)
    r = db.rm_r('njr/test')
    if r == fdb.STATUS.NOT_FOUND:
        print 'Not found'
    elif r == 0:
        print 'deleted OK'
    else:
        print 'error', r

    status, content = db.call('DELETE', '/namespaces/%s/test' % user)
    assert status in (fdb.STATUS.NO_CONTENT, fdb.STATUS.NOT_FOUND)
    print 'Ensured namspace %s/test does not exist' % user

    # Ensure namespace user/test exists and tag user/test/tag

    id = db.tag_object_by_about('DADGAD', 'test/rating', 0)
    assert id == 0
    print '%s/test/rating created / verified' % user
    assert db.set_raw_perm('namespace', '%s/test' % user, 'create', 'closed',
                            [user]) == 0

    p = db.get_raw_perm('namespace', '%s/test' % user, 'create')
    assert (p['policy'], p['exceptions']) == ('closed', [user])
    p = db.get_raw_perm('tag', '%s/test/rating' % user, 'create')
    assert (p['policy'], p['exceptions']) == ('closed', [user])

    # should fail
    ok = testdb.tag_object_by_about('DADGAD', '/%s/test/rating' % user, '0')
    assert ok == 0
    print 'Test user correctly failed to write /%s/test/rating' % user

    # now allow test to write namespace
    assert db.set_raw_perm('namespace', '%s/test' % user, 'create', 'closed',
                            [user, 'test']) == 0
    print ('Test user should have create permission on namespace %s/test:'
           % user)

    p = db.get_raw_perm('namespace', '%s/test' % user, 'create')
    assert (p['policy'], set(p['exceptions'])) == ('closed',
                                                   set([user, 'test']))
    print 'Test user *has* create permission on namespace %s/test:' % user

    assert testdb.tag_object_by_about('DADGAD', '/%s/test/rating2' % user,
                                        '0') == 0
    print 'Test user succeeded in tagging with new %s/test/rating2' % user

    status, content = db.call('DELETE', '/tags/%s/test/rating2' % user)
    assert status == fdb.STATUS.NO_CONTENT
    print 'Tag %s/test/rating2 successfully deleted' % user

    status, content = db.call('DELETE', '/tags/%s/test/rating' % user)
    assert status == fdb.STATUS.NO_CONTENT
    print 'Tag %s/test/rating successfully deleted' % user
