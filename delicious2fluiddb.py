#
# delicious2fluiddb.py: Import all public bookmarks and their tags
#                       from del.icio.us and upload them to FluidDB.
#
# Copyright (c) Nicholas J. Radcliffe
#
# See LICENSE for license.
#
import types, sys
import fdb
from delicious import *

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

START_AT = 0

if __name__ == '__main__':
    p = GetCredentials ()
    entries = GetEntryList (p)
    nTotal = len (entries)
    entries = [e for e in entries if e.shared == True]
    nShared = len (entries)
    print 'Removed %d private entries' % (nTotal - nShared)

    db = fdb.FluidDB ()
    nURLs = nTags = 0
    tagsUsed = set ()
    for entry in entries[START_AT:]:
        if entry.url:
            print 'Tagging %s:' % entry.url
            nURLs += 1
        else:
            print 'Blank URL'
        o = db.create_object (entry.url)
        if type (o) == types.IntType:   # error
            print 'Error occurred, code %d' % o
        else:
            for tag in entry.tags:
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
