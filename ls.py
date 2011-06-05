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
        self.actions = actions
        self.names = names


RAW_PERMS = {
    u'abstract-tag': PermissionDesc(u'abstract-tag', u'tags',
                                    [u'update', u'delete', u'control'],
                                    [u'metadata', u'delete', u'acontrol']),
    u'tag': PermissionDesc(u'tag', u'tag-values',
                           [u'create', u'read', u'delete', u'control'],
                           [u'tag', u'read', u'untag', 'tcontrol']),
    u'namespace': PermissionDesc(u'namespace', u'namespaces',
                                 [u'create', u'update', u'delete', u'list',
                                  u'control'],
                                 [u'create', u'metadata', u'delete', u'read',
                                  u'control'])
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
READ.tag_map({u'tag-values': [u'read']})
READ.namespace_map({u'namespaces': [u'list']})

WRITE = FDBPerm(u'write')
WRITE.tag_map({u'tag-values': [u'create', u'update', u'delete']})
WRITE.namespace_map({u'namespaces': [u'create']})

ADMINISTER = FDBPerm(u'administer')
ADMINISTER.tag_map({u'tags': [u'update', u'delete']})
ADMINISTER.namespace_map({u'namespaces': [u'update', u'delete']})


def string_format(n):
    return u'%%-%ds' % n


def len_exc(exceptions, owner):
    return len(exceptions) - 1 if owner in exceptions else len(exceptions)


def combined_status(list_):
    L = list_[0]
    return L if all(ell == L for ell in list_) else u'/'

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
                       prnt=False, longer=False):
        h = self.list_namespace(ns)
        return self.list_sorted_nshash(h, ns, long_, columns, recurse,
                                       prnt=prnt, longer=longer)

    def list_sorted_nshash(self, h, ns, long_=False, columns=True,
                           recurse=False, prnt=False, longer=False):
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
        if long_ or longer:
            res = []
            for item in items:
                r = self.full_perms(ns + u'/' + fmt % item, longer)
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
                                                     long_, columns, recurse,
                                                     prnt=prnt, longer=longer)
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
        a, t = h[u'acontrol'], h[u'tcontrol']
        writes = (h[u'metadata'], h[u'delete'], h[u'tag'], h[u'untag'])
        ownerRead = (u'r' if r[u'policy'] == u'open'
                             or owner in r[u'exceptions']
                          else u'-')
        ownerWrites = [w[u'policy'] == u'open' or owner in w[u'exceptions']
                       for w in writes]
        ownerControl = combined_status((self.control_status(t, owner),
                                        self.control_status(a, owner)))
        worldControlT = u'c' if t[u'policy'] == u'open' else u'-'
        worldControlA = u'c' if a[u'policy'] == u'open' else u'-'
        worldControl = (worldControlT if worldControlT == worldControlA
                                      else u'/')
        worldRead = u'r' if r[u'policy'] == u'open' else u'-'
        worldWrites = [w[u'policy'] == u'open' for w in writes]
        ownerWrite = write_status(ownerWrites)
        worldWrite = write_status(worldWrites)

        groupRead = self.group_perm(u'r', r, owner)
        groupWrite = combined_status([self.group_perm(u'w', w, owner)
                                      for w in writes])
        groupControl = combined_status([self.group_perm(u'c', c, owner)
                                        for c in (a, t)])

        return u't%s%s%s%s%s%s%s%s%s' % (ownerRead, ownerWrite, ownerControl,
                                         groupRead, groupWrite, groupControl,
                                         worldRead, worldWrite, worldControl)

    def group_perm(self, code, perm, owner):
        n = len_exc(perm[u'exceptions'], owner)
        if perm[u'policy'] == u'closed':
            return code if n > 0 else u'-'
        else:
            return u'-' if n > 0 else code

    def control_status(self, perm, owner):
        return (u'c' if perm[u'policy'] == u'open'
                        or owner in perm[u'exceptions']
                     else u'-')

    def fi_tag_perms_string(self, tag):
        h = self.get_tag_perms_hash(tag)
        s = []
        owner = tag.split(u'/')[0]
        read = h[u'read']
        writes = (u'metadata', u'delete', u'tag', u'untag')
        controls = (h[u'acontrol'], h[u'tcontrol'])
        for kind in (u'ABSTRACT TAG', u'TAG'):
            desc = RAW_PERMS[u'tag' if kind == u'TAG' else u'abstract-tag']
            s.append(kind + u' (/%s)' % desc.path)
            if kind == u'TAG':
                s.append(u'  Read')
                s.append(u'    %-18s  %s' % (u'read (read):',
                                             self.fi_perm_desc(h[u'read'])))
            s.append(u'  Write')
            for (fi, fdb) in zip(desc.actions, desc.names):
                if fdb in writes:
                    s.append(u'    %-18s  %s' % (u'%s (%s):' % (fi, fdb),
                                                 self.fi_perm_desc(h[fdb])))
            s.extend([u'  Control'])
            s.append(u'    %-18s  %s' % (u'control (control):',
                                         self.fi_perm_desc(h[desc.names[-1]])))
            s.append(u'')
        return u'\n'.join(s)

    def fi_perm_desc(self, perm):
        return (u'policy: %s; exceptions [%s]'
                % (perm[u'policy'],
                   u', '.join(u for u in perm[u'exceptions'])))

    def ns_perms_string(self, ns):
        h = self.get_ns_perms_hash(ns)
        s = []
        owner = ns.split(u'/')[0]
        r = h[u'read']
        control = h[u'control']
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
        ownerControl = self.control_status(control, owner)
        worldControl = u'c' if control[u'policy'] == u'open' else u'-'
        groupRead = self.group_perm(u'r', r, owner)
        groupWrite = combined_status([self.group_perm(u'w', w, owner)
                                      for w in writes])
        groupControl = self.group_perm(u'c', control, owner)

        return u'n%s%s%s%s%s%s%s%s%s' % (ownerRead, ownerWrite, ownerControl,
                                         groupRead, groupWrite, groupControl,
                                         worldRead, worldWrite, worldControl)


    def fi_ns_perms_string(self, ns):
        h = self.get_ns_perms_hash(ns)
        s = []
        owner = ns.split(u'/')[0]
        read = h[u'read']
        writes = (u'create', u'update', u'delete')
        desc = RAW_PERMS[u'namespace']
        s.append(u'NAMESPACE (/%s)' % desc.path)
        s.append(u'  Read')
        s.append(u'    %-18s  %s' % (u'list (read):',
                                     self.fi_perm_desc(h[u'read'])))
        s.append(u'  Write')
        for (fi, fdb) in zip(desc.actions, desc.names):
            if fdb in writes:
                s.append(u'    %-18s  %s' % (u'%s (%s):' % (fi, fdb),
                                             self.fi_perm_desc(h[fdb])))
        s.append(u'  Control')
        s.append(u'    %-18s  %s' % (u'control (control):',
                                     self.fi_perm_desc(h[u'control'])))
        s.append(u'')
        return u'\n'.join(s)

    def perms_string(self, tagOrNS, longer=False):
        tagOrNS = tagOrNS.strip()
        if tagOrNS.endswith(u'/'):
            if longer:
                return self.fi_ns_perms_string(tagOrNS[:-1])
            else:
                return self.ns_perms_string(tagOrNS[:-1])
        else:
            if longer:
                return self.fi_tag_perms_string(tagOrNS)
            else:
                return self.tag_perms_string(tagOrNS)

    def full_perms(self, tagOrNS, longer):
        perms = self.perms_string(tagOrNS, longer)
        if longer:
            return u'\n%s:\n\n%s' % (tagOrNS, perms)
        else:
            return u'%s   %s' % (perms, tagOrNS)
                
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
        tags = [(u'/' if db.unixStyle else u'') + db.credentials.username]
    fulltag = db.abs_tag_path(tags[0], inPref=True)
    if options.namespace:
        if db.ns_exists(fulltag):
            if options.long or options.longer:
                nsResult = db.full_perms(fulltag[1:] + u'/', options.longer)
            else:
                nsResult = fulltag
            print nsResult
        else:
            nsResult = u'Not Found'
    else:
        nsResult = db.list_sorted_ns(fulltag[1:], long_=options.long,
                                     recurse=options.recurse, prnt=True,
                                     longer=options.longer)
    tagExists = db.tag_exists(fulltag)
    if nsResult == u'Error status 404':
        if not tagExists:
            print u'%s not found' % fulltag
    if tagExists:
        if options.long or options.longer:
            print db.full_perms(fulltag[1:], options.longer)
        else:
            print tags[0]
