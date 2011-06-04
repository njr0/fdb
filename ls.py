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
        self.actions = actions + [u'control']
        self.names = names + [u'control']


RAW_PERMS = {
    u'abstract-tag': PermissionDesc(u'abstract-tag', u'tags',
                                   [u'update', u'delete'],
                                   [u'metadata', u'delete']),
    u'tag': PermissionDesc(u'tag', u'tag-values',
                          [u'create', u'read', u'delete'],
                          [u'tag', u'read', u'untag']),
    u'namespace': PermissionDesc(u'namespace', u'namespaces',
                                [u'create', u'update', u'delete', u'list'],
                                [u'create', u'metadata', u'delete', u'read'])
}

RAW_PERM_ENTITIES = RAW_PERMS.keys()


class FDBPerm:
    def __init__(self, name):
        self.name = u'read'
        self.tag = None
        self.namepspace = None

    def tag_map(self, perm):
        self.tag = perm

    def namespace_map(self, perm):
        self.ns = perm

READ = FDBPerm(u'read')
READ.tag_map({u'tag-values': [u'see', u'read']})
READ.namespace_map({u'namespaces': [u'list']})

WRITE = FDBPerm(u'write')
WRITE.tag_map({u'tag-values': [u'create', u'update', u'delete']})
WRITE.namespace_map({u'namespaces': [u'create']})

ADMINISTER = FDBPerm(u'administer')
ADMINISTER.tag_map({u'tags': [u'update', u'delete']})
ADMINISTER.namespace_map({u'namespaces': [u'update', u'delete']})


def string_format(n):
    return u'%%-%ds' % n


def to_string_grid(items, pageWidth=78, maxCols=9):
    if items == []:
        return u''
    widest = max([len(s) for s in items])
    nCols = min(max(pageWidth / (widest + 1), 1), maxCols)
    colWidth = int(math.ceil(float(pageWidth) / nCols)) - 1
    fmt = string_format(colWidth)
    nItems = len(items)
    nRows = int(math.ceil(float(nItems) / nCols))

    return u'\n'.join([u' '.join([fmt % items[col * nRows + row]
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
        status, content = self.call(u'GET', u'/namespaces/%s' % ns, None,
                                    returnDescription=returnDescription,
                                    returnNamespaces=returnNamespaces,
                                    returnTags=returnTags)
        return content if status == STATUS.OK else status

    def list_r_namespace(self, rootns):
        L = self.list_namespace(rootns, returnDescription=False)
        if L == fdb.STATUS.NOT_FOUND:
            return fdb.STATUS.NOT_FOUND
        if type(L) == int:
            return {u'namespaceNames': [], u'tagNames': [], u'failures': True}
        failures = False
        namespaces = [u'%s/%s' % (rootns, space)
                        for space in L[u'namespaceNames']]
        tags = [u'%s/%s' % (rootns, tag) for tag in L[u'tagNames']]
        subns = []
        subtags = []
        for s in namespaces:
            L = self.list_namespace(s, returnDescription=False)
            if type(L) == int:
                failures = True
            else:
                subns.extend([u'%s/%s' % (s, space)
                                  for space in L[u'namespaceNames']])
                subtags.extend([u'%s/%s' % (s, space)
                                  for space in L[u'tagNames']])
        namespaces.extend(subns)
        tags.extend(subtags)
        return {u'namespaceNames': namespaces, u'tagNames': tags,
                u'failures': failures}

    def rm_r(self, rootns):
        L = self.list_r_namespace(rootns)
        if L == fdb.STATUS.NOT_FOUND:
            return L
        elif L[u'failures']:
            return 1            # non-zero failure code
        # First delete all the tags & sub-namespaces
        for items, fn in ((L[u'tagNames'], self.delete_abstract_tag),
                          (L[u'namespaceNames'], self.delete_namespace)):
            si = [(i.split(u'/'), i) for i in items]
            z = [(len(s), i) for (s, i) in si]
            z.sort()
            z.reverse()
            failed = False
            for (n, i) in z:
                r = self.delete_abstract_tag(u'/%s' % i)
                failed = failed or (r != fdb.STATUS.NO_CONTENT)
        if failed:
            return 1
        return self.delete_namespace(u'/' + rootns)

    def list_sorted_ns(self, ns, long_=False, columns=True, recurse=False,
                       prnt=False):
        h = self.list_namespace(ns)
        return self.list_sorted_nshash(h, ns, long_, columns, recurse,
                                       prnt=prnt)

    def list_sorted_nshash(self, h, ns, long_=False, columns=True,
                           recurse=False, prnt=False):
        if type(h) == types.IntType:
            if h == STATUS.UNAUTHORIZED:
                return u'Permission denied.'
            else:
                return u'Error status %s' % h

        tagNames = h[u'tagNames']
        tagNames.sort()
        spaces = h[u'namespaceNames']
        spaces.sort()
        items = tagNames[:] + [u'%s/' % space for space in spaces]
        items.sort()
        if items:
            fmt = string_format(max([len(item) for item in items]))
        if recurse:
            print u'\n%s:' % ns
        if long_:
            res = []
            for item in items:
                r = u'%s   %s' % (self.perms_string(ns + u'/' +  fmt % item),
                                 fmt % item)
                res.append(r)
                if prnt:
                    print r
            result = u'\n'.join(res)
        elif columns == False:
            result = u'\n'.join(items)
            if prnt:
                print result
        else:
            result = to_string_grid(items)
            if prnt:
                print result
        if recurse:
            others = u'\n'.join([self.list_sorted_ns(u'%s/%s' % (ns, space),
                                        long_, columns, recurse, prnt=prnt)
                                        for space in spaces])
            return u'%s:\n%s\n\n%s' % (ns, result, others)
        else:
            return result

    def get_raw_perm(self, entity, name, action):
        assert entity in RAW_PERM_ENTITIES
        perm = RAW_PERMS[entity]
        assert action in perm.actions
        path = u'/permissions/%s/%s' % (perm.path, name)
        status, content = self.call(u'GET', path, None, action=action)
        return content if status == STATUS.OK else status

    def get_tag_perms_hash(self, tag):
        h = {}
        for entity in [u'abstract-tag', u'tag']:
            desc = RAW_PERMS[entity]
            for (action, name) in zip(desc.actions, desc.names):
                h[name] = self.get_raw_perm(entity, tag, action)
        return h

    def get_ns_perms_hash(self, ns):
        h = {}
        for entity in [u'namespace']:
            desc = RAW_PERMS[entity]
            for (action, name) in zip(desc.actions, desc.names):
                h[name] = self.get_raw_perm(entity, ns, action)
        return h

    def tag_perms_string(self, tag):
        h = self.get_tag_perms_hash(tag)
        s = []
        owner = tag.split(u'/')[0]
        r = h[u'read']
        writes = (h[u'tag'], h[u'untag'], h[u'metadata'], h[u'delete'])
        ownerRead = (u'r' if r[u'policy'] == u'open'
                             or owner in r[u'exceptions']
                          else u'-')
        ownerWrites = [w[u'policy'] == u'open' or owner in w[u'exceptions']
                       for w in writes]
        worldRead = u'r' if r[u'policy'] == u'open' else u'-'
        worldWrites = [w[u'policy'] == u'open' for w in writes]
        ownerWrite = write_status(ownerWrites)
        worldWrite = write_status(worldWrites)
 
        return u'-%s%sc---%s%s-' % (ownerRead, ownerWrite,
                                   worldRead, worldWrite)
    def ns_perms_string(self, ns):
        h = self.get_ns_perms_hash(ns)
        s = []
        owner = ns.split(u'/')[0]
        r = h[u'read']
        writes = (h[u'create'], h[u'metadata'], h[u'delete'])
        ownerRead = (u'r' if r[u'policy'] == u'open'
                             or owner in r[u'exceptions']
                          else u'-')
        ownerWrites = [w[u'policy'] == u'open' or owner in w[u'exceptions']
                       for w in writes]
        worldRead = u'r' if r[u'policy'] == u'open' else u'-'
        worldWrites = [w[u'policy'] == u'open' for w in writes]
        ownerWrite = write_status(ownerWrites)
        worldWrite = write_status(worldWrites)
 
        return u'n%s%sc---%s%s-' % (ownerRead, ownerWrite,
                                   worldRead, worldWrite)

    def perms_string(self, tagOrNS):
        tagOrNS = tagOrNS.strip()
        if tagOrNS.endswith(u'/'):
            return self.ns_perms_string(tagOrNS[:-1])
        else:
            return self.tag_perms_string(tagOrNS)
                
    def set_raw_perm(self, entity, name, action, policy, exceptions):
        assert entity in RAW_PERM_ENTITIES
        perm = RAW_PERMS[entity]
        assert action in perm.actions
        assert policy in (u'open', u'closed')
        assert not type(exceptions) in types.StringTypes    # forgot the []
        body = json.dumps({u'policy': policy, u'exceptions': exceptions})
        path = u'/permissions/%s/%s' % (perm.path, name)
        status, content = self.call(u'PUT', path, body, action=action)
        return 0 if status == STATUS.NO_CONTENT else status


def write_status(writes):
    if sum(writes) == len(writes):
        return u'w'
    else:
         return u'-' if sum(writes) == 0 else u'.'


def execute_ls_command(objs, tags, options):
    credentials = Credentials(options.user[0]) if options.user else None
    db = ExtendedFluidDB(host=options.hostname, credentials=credentials,
                         debug=options.debug,
                         unixStylePaths=fdblib.path_style(options))

    if len(tags) == 0:
        fulltag = db.abs_tag_path(u'', inPref=True)[:-1]
    else:
        fulltag = db.abs_tag_path(tags[0], inPref=True)
    if options.namespace:
        if db.ns_exists(fulltag):
            perms = ((db.perms_string(db.abs_tag_path(fulltag,
                                                      inPref=True)[1:] + u'/')
                     + u'   ') if options.long else u'')
            nsResult = perms + tags[0]
            print nsResult
        else:
            nsResult = u'Not Found'
    else:
        nsResult = db.list_sorted_ns(fulltag[1:], long_=options.long,
                                     recurse=options.recurse, prnt=True)
    tagExists = db.tag_exists(fulltag)
    if nsResult == u'Error status 404':
        if not tagExists:
            print u'%s not found' % db.abs_tag_path(fulltag, inPref=True)
    if tagExists:
        perms = ((db.perms_string(db.abs_tag_path(fulltag, inPref=True)[1:])
                  + u'   ') if options.long else u'')
        print perms + tags[0]


if __name__ == '__main__':
    db = ExtendedFluidDB()
    testdb = ExtendedFluidDB()
    testdb.credentials = fdb.Credentials(u'test', u'test')

    user = db.credentials.username
    if 0:
        assert db.set_raw_perm(u'tag', u'%s/rating' % user, u'read', u'open',
                                [u'test']) == 0
        print db.get_raw_perm(u'abstract-tag', u'%s/rating' % user, u'update')
        print db.get_raw_perm(u'tag', u'%s/rating' % user, u'read')
        print db.get_raw_perm(u'namespace', u'%s' % user, u'update')

        assert (db.set_raw_perm(u'tag', u'%s/rating' % user, u'read', u'open', [])
                == 0)
        print db.get_raw_perm(u'tag', u'%s/rating' % user, u'read')

    # First get rid of any existing namespace

    print db.list_sorted_ns(u'njr', recurse=True)
    r = db.rm_r(u'njr/test')
    if r == fdb.STATUS.NOT_FOUND:
        print u'Not found'
    elif r == 0:
        print u'deleted OK'
    else:
        print u'error', r

    status, content = db.call(u'DELETE', u'/namespaces/%s/test' % user)
    assert status in (fdb.STATUS.NO_CONTENT, fdb.STATUS.NOT_FOUND)
    print u'Ensured namspace %s/test does not exist' % user

    # Ensure namespace user/test exists and tag user/test/tag

    id = db.tag_object_by_about(u'DADGAD', u'test/rating', 0)
    assert id == 0
    print u'%s/test/rating created / verified' % user
    assert db.set_raw_perm(u'namespace', u'%s/test' % user, u'create', u'closed',
                            [user]) == 0

    p = db.get_raw_perm(u'namespace', u'%s/test' % user, u'create')
    assert (p[u'policy'], p[u'exceptions']) == (u'closed', [user])
    p = db.get_raw_perm(u'tag', u'%s/test/rating' % user, u'create')
    assert (p[u'policy'], p[u'exceptions']) == (u'closed', [user])

    # should fail
    ok = testdb.tag_object_by_about(u'DADGAD', u'/%s/test/rating' % user, u'0')
    assert ok == 0
    print u'Test user correctly failed to write /%s/test/rating' % user

    # now allow test to write namespace
    assert db.set_raw_perm(u'namespace', u'%s/test' % user, u'create', u'closed',
                            [user, u'test']) == 0
    print (u'Test user should have create permission on namespace %s/test:'
           % user)

    p = db.get_raw_perm(u'namespace', u'%s/test' % user, u'create')
    assert (p[u'policy'], set(p[u'exceptions'])) == (u'closed',
                                                   set([user, u'test']))
    print u'Test user *has* create permission on namespace %s/test:' % user

    assert testdb.tag_object_by_about(u'DADGAD', u'/%s/test/rating2' % user,
                                        u'0') == 0
    print u'Test user succeeded in tagging with new %s/test/rating2' % user

    status, content = db.call(u'DELETE', u'/tags/%s/test/rating2' % user)
    assert status == fdb.STATUS.NO_CONTENT
    print u'Tag %s/test/rating2 successfully deleted' % user

    status, content = db.call(u'DELETE', u'/tags/%s/test/rating' % user)
    assert status == fdb.STATUS.NO_CONTENT
    print u'Tag %s/test/rating successfully deleted' % user
