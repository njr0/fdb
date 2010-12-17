#
# delicious2fluiddb.py: Import all public bookmarks and their tags
#                       from del.icio.us and upload them to FluidDB.
#
# Copyright (c) Nicholas J. Radcliffe 2009
#
# See LICENSE for license.
#
import types, sys
import fdb
#import fdbdummy as fdb
from delicious import *
try:
    from abouttag.uri import URI
except ImportError:
    print 'You need the abouttag library on your PYTHONPATH.'
    print 'It is available from https://github.com/njr0/abouttag'
    raise


class Entry:
    def __init__ (self, url, description, tags, shared, extended):
        self.url = url
        self.description = description
        self.tags = tags
        self.shared = shared
        self.extended = extended

    def __str__ (self):
        return '\n'.join (['%12s: %s' % (k, str (self.__dict__[k]))
                for k in ['url', 'description', 'tags', 'extended', 'shared']])

def Process (entries, p):
    doc = ParseXMLString (entries)
    entries = []
    posts = FindFirstNamedChild (doc, 'posts')
    for node in posts.childNodes:
        description = ''
        extended = ''
        url = ''
        tags = []
        shared = True
	if isElement (node):
	    for key in node.attributes.keys ():
		if key == 'shared':
                    shared = node.attributes[key].value.encode ('ascii', 
			       'ignore')  != "no"
		if key == 'tag':
                    tags = node.attributes[key].value.encode ('ascii', 
			       'ignore').split (' ')
		elif key == 'extended':
		    extended = node.attributes[key].value.encode ('ascii', 
			   'ignore')
		elif key == 'description':
		    description = node.attributes[key].value.encode ('ascii', 
			   'ignore')
		elif key == 'href':
		    url = node.attributes[key].value
            entries.append (Entry (url, description, tags, shared, extended))
    return entries        

def GetEntryList (p):
    xmlEntries = ReadXML (p.cache)
    entries = Process (xmlEntries, p)
    return entries 


if __name__ == '__main__':
    startAt = 0 if len(sys.argv) < 2 else int(sys.argv[1])
    p = GetCredentials()
    entries = GetEntryList(p)
    nTotal = len(entries)
    entries = [e for e in entries if e.shared == True]
    nShared = len(entries)
    print 'Removed %d private entries' % (nTotal - nShared)

    db = fdb.FluidDB()
    nURLs = nTags = 0
    tagsUsed = set()
    for i, entry in enumerate(entries[startAt:]):
        if entry.url:
            uri = URI(unicode(entry.url)).encode('UTF-8')
            print '%4d: Tagging %s as %s:' % (i + startAt, entry.url, uri)
            nURLs += 1
        else:
            print 'Blank URL'
        o = db.create_object(uri)
        if type (o) == types.IntType:   # error
            print 'Error occurred, code %d' % o
        else:
            for tag in [t for t in entry.tags if t]: # no empty tags
                error = db.tag_object_by_id (o.id, tag)
                print '   %s' % tag,
                sys.stdout.flush ()
                if error == 0:
                    nTags += 1
                    tagsUsed.add (tag)
                else:
                    print '\n ---> FAILURE!'
            print
    print ('%d URLs tagged in FluidDB, with a total of %d tags (%d distinct)'
                % (nURLs, nTags, len (tagsUsed)))
    print '\nTags were: %s' % (' '.join ([tag for tag in tagsUsed]))
