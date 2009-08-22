#!/usr/bin/python
#
# delicious.cgi: CGI script for building home page from delicious
#                bookmarks tagged home.
#
# Copyright (c) Nicholas J. Radcliffe 2008-2009
#
# See LICENSE for license.
#

import sys, re, socket
import cgi
host = socket.gethostbyaddr(socket.gethostname())[0]
from delicious import *

HEAD="""
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<style type="text/css">
	.sq {width: 4ex;}
        .Sans {font-family : Helvetica, Arial, Verdana, Sans;}
        .Serif {font-family : Times, Serif;}
        .Mono {font-family : Courier, monospace;}
        .Giant {font-size : 72pt;
                font-family: Times, Garamond, Baskerville, Serif;}
        .Subtitle { font-family : Garamond, Times, Serif;
                font-style : italic;
                font-size: large;
                padding: 0 0 12pt 0;
                color: darkgreen; }
        .PushRight { padding: 0 0 0 40pt; }
        .Help { font-family : Helvetica, Arial, Verdana, Sans;
                font-size : small; }
        

        a:link
        {
          color:#006000;
          text-decoration:none;
        }
        a:visited
        {
          color:#003000;
          text-decoration:none;
        }
        a:hover
        {
          color:#007F00;
          text-decoration:underline;
        }
        a img
        {
          border-width:0;
        }
</style>
<title>Delicious Updater</title>
</head>
<body>
<p>Hi</p>
"""

TAIL="""
</body>
</html>"""





def HTMLHeader ():
    return 'Content-Type: text/html\n'

def TextHeader ():
    return 'Content-Type: text/plain\n'

print (TextHeader ())
RefreshHomepageFromDelicious ()
