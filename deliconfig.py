import os, sys

class Params:
    homepage = '/Users/njr/Sites/intranet/cache/index.html'
                                        # Target homepage location.
                                        # Must be writable by web server
                                        # if CGI script is to be used.
    cache = '/Users/njr/Sites/intranet/cache/delicious.xml'
                                        # Cache of delicious entries.
                                        # Must be writable by web server
                                        # if CGI script is to be used.
    credentials = '/Users/njr/python/delicious/credentials.txt'
                                        # file containing delicious
                                        # username and password
                                        # (on separate lines).
                                        # Must be readable by web server
                                        # if CGI script is to be used.

    refreshurl = 'http://localhost/cgi-bin/delicious.cgi'
                                        # URL for delicious.cgi, which
                                        # refreshes the page.
                                        # Leave blank if not required or
                                        # or not configured

    refreshLabel = 'Refresh'            # Label for refresh link

    refreshAtBottom = False             # If not at bottom, refresh
                                        # just becomes another normal entry
                                        # in the list ('Refresh')

    alink="#800000"                     # Link colours, text & background
    vlink="#800000"                     # colours.   Can be 6-digit hex
    link="#C00000"                      # RGB values like #800000 for
    bgcolor="#FFFFFF"                   # dark red or HTML string colours
    text="#000000"                      # such as blue, purple etc.

    font="Helvetica,Verdana,Arial"      # Leave blank to use browser default

    cols = 4                            # number of columns for output page
    tags = 'home'                       # space-separated list of tags to use
    caseSensitive = False               # ignore case in matching tags
                                        # and in sort order for page

    title = 'NJR Home'                  # Title for page; leave colour as
    titleColor = "white"                # white if you don't want to see it

    addDatestampCopy = True             # True to keep datestamped versions
                                        # of homepage and delicious data

    verbose = True                      # True to report what the command
                                        # is doing as it runs

    def SetCredentials (self, username, password):
        self.username = username   # Place del.icio.us username and password
        self.password = password   # in two lines of credentials.txt
                                   # (location specified in credentials above)
