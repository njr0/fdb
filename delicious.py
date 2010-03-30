#
# delicious.py: Construct a home page from del.icio.us
#
# Copyright (c) Nicholas J. Radcliffe 2008-2009
#
# See LICENSE for license.
#
# V0.1   3. 5.2008      Initial version; not CGI-refreshable, yet.
# V0.2   4. 5.2008      Minor refactoring;
#                       Now reads user/password from credentials.txt
# V0.3   4. 5.2008      Allow list of tags
# V0.4   4. 5.2008      Made credentials relocatable
# V0.5   4. 5.2008      ...and made that actually work
# V0.6   4. 5.2008      ...and again
# V0.7   4. 5.2008      Changed usage so that -c forces rebuild from cache
# V0.8   4. 5.2008      Added 'Completed OK'
# V0.9   4. 5.2008      Annotated config file and created README
# V1.0  10. 5.2008      Added support for refresh link at bottom through
#                       delicious.cgi
# V1.1  10. 5.2008      Allowed refresh link to be 'just another link'
# V1.2  22. 8.2009      Removed dependence on jython-compatible XML library
# V1.3  24. 8.2009      Made font specification work


import sys, os, time
import base64
import urllib2
from xml.dom import minidom
from deliconfig import *

USAGE = 'delicious [-c]      use the -c option to rebuild from the cache'

API_URL='https://api.del.icio.us/v1/posts/all'

def isElement (node):
    return node.nodeType == node.ELEMENT_NODE

def isNamedElement (node, name):
    return isElement (node) and node.nodeName == name

def FindFirstNamedChild (node, name):
    for child in node.childNodes:
	if isNamedElement (child, name):
	   return child

def ParseXMLFile (xmlFile):
    return minidom.parse (xmlFile)

def ParseXMLString (xmlString):
    return minidom.parseString (xmlString)

class PageTemplate:
    def __init__ (self, p, phone):
        nCols = p.phonecols if phone else p.cols
        align = 'div' if phone else 'center'
        self.COLSPEC = ('<col width="%d%%"/>' % (100/nCols)) * nCols

        if p.font:
            self.FONT_OPEN = '<font face="%s">' % p.font
            self.FONT_CLOSE = '</font>'
        else:
            self.FONT_OPEN = '' 
            self.FONT_CLOSE = ''

        self.REFRESH_LINK = ''
        if p.refreshurl and p.refreshAtBottom:
            self.REFRESH_LINK = '<a href="%s">%s</a>' % (p.refreshurl,
                                                         p.refreshLabel)
        h1title = ('<center><h1><font color="%s">%s</font></h1></center>'
                    % (p.titleColor,
                       p.title.encode('utf-8')) if not phone else '')
        self.PAGEHEAD = \
'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html>
<head>
<title>%s</title>
<style type="text/css">
td { padding:  0 6px 0 6px;
}
body {
   font-size: %s%%;
}
</style>
</head>
<body alink="%s" vlink="%s" link="%s" bgcolor="%s" text="%s">
%s
<%s>
%s
<table  cellpadding="0">
<colgroup>
%s
</colgroup>
''' % (p.title.encode('utf-8'), "400" if phone else "100",
       p.alink, p.vlink, p.link, p.bgcolor, p.text,
       h1title,
       align,
       self.FONT_OPEN, self.COLSPEC)


        self.PAGEFOOT = '''
</table>
<br/>
%s
%s
</%s>
</body>
</html>
''' % (self.REFRESH_LINK, self.FONT_CLOSE, align)

def Report (s, p):
    if p.verbose:
        print s

def Usage (exitCode):
    print USAGE
    sys.exit (exitCode)

def GetAllDeliciousEntries (p):
    request = urllib2.Request(API_URL)
    credentials64 = base64.encodestring ('%s:%s' % (p.username, p.password))
    request.add_header ('Authorization', 'Basic %s' % credentials64)
    f = urllib2.urlopen (request)
    return f.read ()

def WriteFileWithBackup (content, filename):
    BackupFile (filename)
    f = open (filename, 'w')
    f.write (content)
    f.close ()

def WriteFileBackupTimestamp (content, filename, p):
    WriteFileWithBackup (content, filename)
    if p.addDatestampCopy:
        ts = time.strftime ('%Y%m%d%-%H%M%S')
        (stem, ext) = os.path.splitext (filename)
        WriteFileWithBackup (content, '%s%s%s' % (stem, ts, ext))


def PrintAllResults (entries):
    doc = ParseXMLString (entries)
    print type (doc)
    posts = FindFirstNamedChild (doc, 'posts')
    n = 0
    for node in posts.childNodes:
	if isElement (node):
	    for key in node.attributes.keys ():
	        print '%s : "%s"' % (key,
		     node.attributes[key].value.encode ('ascii', 'ignore'))
            print
	    n += 1
    print '%d Posts' % n

def GetHomeResults (entries, p):
    doc = ParseXMLString (entries)
    home = {}
    posts = FindFirstNamedChild (doc, 'posts')
    if not p.caseSensitive:
        tagList = p.tags.lower().split ()
    else:
        tagList = p.tags.split ()
    for node in posts.childNodes:
	if isElement (node):
	    includeEntry = False
	    description = ''
	    extended = ''
	    url = ''
	    for key in node.attributes.keys ():
		if key == 'tag':
		    if p.caseSensitive:
		        tags = node.attributes[key].value.encode ('ascii', 
			       'ignore').split (' ')
		        for t in tagList:
                            if t in tags:
                                includeEntry = True
		    else:
		        tags = node.attributes[key].value.encode ('ascii', 
			       'ignore').lower ().split (' ')
		        for t in tagList:
                            if t in tags:
                                includeEntry = True
		elif key == 'extended':
		    extended = node.attributes[key].value.encode ('ascii', 
			   'ignore')
		elif key == 'description':
		    description = node.attributes[key].value.encode ('ascii', 
			   'ignore')
		elif key == 'href':
		    url = node.attributes[key].value
	    if includeEntry:
	        if extended == '':
		    extended = description
		if home.has_key (extended):
		    print 'Duplicate key :', extended
		home[extended] = url

    if p.refreshurl and not p.refreshAtBottom:
        home[p.refreshLabel] = p.refreshurl
		
    return home

def ReadXML (filename):
    f = open (filename)
    e = f.read ()
    f.close
    return e

def Sort (keys, p):
    if p.caseSensitive:
        keys.sort ()
    else:
        lckeys = [k.lower () for k in keys]
        z = zip (lckeys, keys)
        z.sort ()
        sorted = [k for (j,k) in z]
        for i in range (len (keys)):
            keys[i] = sorted[i]

def BuildPage (home, h, p, phone):
    keys = home.keys ()
    keys.sort ()

    additional = [k for k in keys if '+' in k]
    for a in additional:
	(main, rem) = a.split ('+')
	main = main.strip ()
	if main in keys:
	    home[main] = (home[main], rem.strip (), home[a])
	    del home[a]
	else:
	    print 'Warning: additional key "%s" matches no main key;' % a
            print 'Making separate entry.'
    keys = home.keys ()
    Sort (keys, p)
    nEntries = len (keys)
    nCols = p.phonecols if phone else p.cols
    uneven = nEntries % nCols > 0
    nRows = nEntries / nCols + uneven
    s = [h.PAGEHEAD]
    for row in range (nRows):
	s += ['<tr>']
	if row == nRows - 1:
	    N = nEntries % nCols
	else:
	    N = nCols
        count = [0] * nCols
	for col in range (N):
            count[col] = nEntries / nCols + (nEntries % nCols > col)
	for col in range (N):
	    index = sum (count[:col]) + row
            key = keys[index]
	    if type (home[key]) == type (()):
                (url, key2, url2) = home[key]
                s += ['<td><a href="%s">%s</a> <a href="%s">%s</a></td>' % \
                        (url, key, url2, key2)]
	    else:
	        s += ['<td><a href="%s">%s</a></td>' % (home[key], key)]
	s += ['</tr>']
    s += [h.PAGEFOOT]
    return '\n'.join (s)


def BackupFile (path, backupExt='~'):
    backup = '%s%s' % (path, backupExt)
    if (os.path.exists (backup)):
        try:
            os.unlink (backup)
        except:
            pass
    if os.path.exists (path):
        try:
            os.rename (path, backup)
        except:
            print 'Could not rename %s to %s~' % (path, path)
            print 'Continuing'



def GetCredentials ():
    p = Params ()
    if os.path.exists (p.credentials):
        try:
            f = open (p.credentials)
            username = f.readline ().strip ()
            password = f.readline ().strip ()
            f.close ()
        except:
            print 'Need file %s with del.icio.us username on first ' \
                  'line and password on second.'
            sys.exit (1)
    else:
        print 'No credentials file (%s) found.' % p.credentials
        sys.exit (1)

    p.SetCredentials (username, password)

    return p
    

def RefreshHomepageFromDelicious (useCache=0, phone=False):
    p = GetCredentials ()
    h = PageTemplate (p, phone)

    if useCache:
        Report ('Reading entries from cache %s' % p.cache, p)
        xmlEntries = ReadXML (p.cache)
    else:
        Report ('Reading entries from del.icio.us', p)
        xmlEntries = GetAllDeliciousEntries (p)
        Report  ('Writing cache %s' % p.cache, p)
        WriteFileBackupTimestamp (xmlEntries, p.cache, p)

    home = GetHomeResults (xmlEntries, p)
    homepage = p.phonepage if phone else p.homepage
    Report ('Building home page %s' % homepage, p)
    page = BuildPage (home, h, p, phone)
    WriteFileBackupTimestamp (page, homepage, p)
    Report ('Home page built and backed up', p)
    Report ('Completed OK.', p)

if __name__ == '__main__':
    if len (sys.argv) == 1:
        RefreshHomepageFromDelicious (useCache=False)
    elif len (sys.argv) == 2 and sys.argv[1] == '-c':
        RefreshHomepageFromDelicious (useCache=True)
    elif len (sys.argv) == 2 and sys.argv[1] == '-p':
        RefreshHomepageFromDelicious (useCache=True, phone=True)
    elif len (sys.argv) == 2 and sys.argv[1] == '-h':
        Usage (0)
    else:
        Usage (1)
