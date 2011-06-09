#
# 2009/08/20 v0.1       Initial version.   6 tests pass
#                       Used to import 1456 objects from delicious sucessfully
#
# 2009/08/20 v0.2       Added some path tests and new tag_path_split method.
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
# 2009/08/20 v0.3       Reads the credentials file from the home
#                       directory (unix/windows).
#                       Removed import of no-longer-used fuilddb.py
#                         (most of it was in-lined then bastardized)
#                       Added ability to use the code from the command line
#                       for tagging, untagging and retriving objects.
#                       Currently this can be done by specifying the
#                       about tag or object ID, though it will soon
#                       support queries to select objects too (for some value
#                       of 'soon').
#                       See the USAGE string for command line usage
#                       or run with the command line argument -h, or help.
#
# 2009/08/21 v0.4       Added query function to execute a query against
#                       FluidDB and extended all the command line functions
#                       to handle query, so that now you can tag, untag
#                       and get tag values based on a query.
#                       Also now specify json as the format on PUT
#                       when creating tags; apparently they were binary before.
#                       Also fixed things so that objects without an
#                       about field can be created (I think).
#                       Certainly, they don't cause an error.
#                       A few other minor changes to put more sensible
#                       defaults in for credentials etc., making it
#                       easier to use the lirary interactively.
#
# 2009/08/21 v0.5       Renamed command line command get to show to avoid
#                       clash with http GET command.
#                       Plan to add raw put, get, post, delete, head commands.
#                       The tests now assume that the credentials are in
#                       the standard place (~/.fluidDBcredentials on unix,
#                       or fluidDBcredential.ini in the home folder on
#                       windows) and use that, though credentials can still
#                       be provided in any of the old ways in the interface.
#
#                       New class for testing the command line interface (CLI)
#
#                       Can now run tests with
#                           fdb         --- run all tests
#                           fdb test    --- run all tests
#                           fdb testcli --- test CLI only
#                           fdb testcli --- test DB only
#
# 2009/08/22 v0.6       Added delicious2fluiddb.py and its friends
#                       (delicious.py, delicious.cgi, deliconfig.py)
#                       to the repository.   This allows all public
#                       bookmarks from delicious to be uploaded to
#                       FluidDB.   (In fact, a one line change would
#                       allow private ones to be uploaded too, but
#                       since fdb.py knows nothing about permissions
#                       on tags yet, that seems like a bad idea for now.)
#
# 2009/08/22 v0.7       Corrected copyright year on delicious code
#
# 2009/08/22 v0.8       Added README and README-DELICIOUS files as
#                       a form of documentation.
#
# 2009/08/22 v0.9       Added GET, POST, PUT, DELETE, HEAD commands to
#                       command line interface.
#                       To be honest, haven't tested most of these,
#                          but get works in simple cases.
#                       Added note of count of objects matching a query.
#                       Added special case: '/about' expands to
#                           '/fluiddb/about'
#                       Added count command to CLI.
#                       Also, in the CLI (but not the API), you can now
#                          use /id as shorthand for the object's id.
#                       Changed name of createTagIfNeeded parameters
#                          to createAbstractTagIfNeeded. (Thanks, Xavi!)
#
# 2009/08/23 v1.0       Fixed fdb show -a DADGAD /id
#                       which was doubly broken.
#                       Hit v1.0 by virtue of adding 0.1 to 0.9 :-)
#
# 2009/08/23 v1.01      Added delicious2fluiddb.pdf
#
# 2009/08/24 v1.11      Added missing README to repository
#
# 2009/08/24 v1.12      Fixed four tests so that they work even
#                       for user's *not* called njr...
#
# 2009/08/24 v1.13      Fixed bug that prevented tagging with real values.
#                       Added tests for reading various values.
#                       Made various minor corrections to
#                       delicious2fluiddb.pdf.
#                       Split out test class for FDB internal unit tests
#                       that don't exercise/require the FluidDB API.
#                       Added command for that and documented '-v'
#                       (Also, in fact, fixed and simplied the regular
#                       expressions for floats and things, which were wrong.)
#
# 2009/08/24 v1.14      Fixed delicious.py so it sets the font on the page.
#
# 2009/08/24 v1.15      Fixed problem with value encoding when setting tags.
#                       (The json format was specification was in the wrong
#                       place.)
#                       @paparent helped to locate the problem --- thanks.
#                       Also changed things so that -host/-sand
#                       and -D (debug) work when
#                       running the tests; unfortunately, this works by
#                       reading the global flags variable.
#                       Created KNOWN-PROBLEMS file, which is not empty
#                       for v1.15.
# 2009/08/26 v1.16      Changed import httplib2 statement to avoid
#                       strange hang when importing fdb from somewhere
#                       other than the current directory through the python
#                       path.
#                       Corrected variable used in error reporting
#                       in execute show_ command.
#
# 2009/08/26 v1.17      Added blank line between objects on show -q
#                       Added -T to allow specification of an Http
#                       timeout (useful at the moment, where the
#                       sandbox can hang) and a default timeout of c. 300s.
#                       Also, I've made the tests set the timeout to 5s
#                       unless it has been set to something
#                       explcitly by the user.
#
# 2009/08/26 v1.18      Yevgen did various bits of cleaning up, debugging
#                       and standardization, most notably:
#                          -- Using a decorator to avoid code repition
#                          -- Moving flag/option handling to use the standard
#                             optparse library instead of the custom flags lib.
#                          -- fixing a couple of bugs
#                          -- making everything work against the sandbox
#                             as well as the main instance.
#                       Also made the DADGAD_ID host-dependent.
#                       May get FluidDB to cache IDs associated with about
#                       tags and then load at start, save at end of session.
#                       The cache would improve performance, and could
#                       get emptied if corrupted or if the sandbox is reset
#                       or whatever.
#
# 2009/09/01 v1.19      Added calls to the API (only) for creating
#                       (sub)namespaces, deleting (sub)namespaces and
#                       fetching descriptions of namespaces.
#                       These have been manually tested, but no
#                       units tests have been written yet, and the
#                       command line interface has neither been extended
#                       to make use of these calls or to provide new
#                       primatives to let users use them from the command line.
#                       All this and more will come.
#                       The new functions, all methods on FluidDB, are:
#                           create_namespace
#                           delete_namespace
#                           describe_namespace
#                       create_namespace has an option to recurse if the
#                       parent doesn't exist.   Although planned for the
#                       the future (and arguments have been included in the
#                       function signature), delete does not currently
#                       support recursive deletion or forcing (in the case
#                       tags or subnamspaces exist in the namespace).
#
# 2009/09/01 v1.20      Added nstest.py to git to illstrate namespace functions
#                       added in 1.19.
#
# 2009/09/01 v1.21      Made tagging of objects create intermediate namespaces
#                       as required.   This affects both the command line
#                       utilities and the API calls.   Still no unit tests
#                       though.
#
# 2009/09/24 v1.22      Updated to "new" API (thanks, Terry...)
#
# 2010/03/08 v1.23      Typo fixed; test changed to reflect new (improved)
#                       FluidDB response to using bad credentials.
# 2010/03/26 v1.24      Fixed some weird indentation. Added encoding.
# 2010/03/28 v1.25      Fixed a unicode problem and some help text.
# 2010/03/30 v1.26      Changed the default action to be help, rather
#                       than running tests.
#                       Added tags command.
# 2010/03/30 v1.27      Removed extra namespace in output from tag above.
# 2011/01/33 v1.28      Modified testUntagObjectByID to reflect API changes
# 2011/01/34 v1.29      Added first stage of support for /values API.
#                       Currently this is just a few functions to let this
#                       be used programatically.
#                       These new calls are unicode-based; also started adding
#                       support for a future upgrade to the library to be
#                       100% unicode.
# 2011/04/14 v1.30      Added __unicode__ method to class O.
#                       Corrected version number.
# 2011/04/14 v1.31      Split into modules fdb.py, testfdb.py, cli.py,
#                       and fdbcore.py
# 2011/04/14 v1.32      Added support for switching between unix-style
#                       paths and Fluidinfo-style paths.   This can be
#                       controlled by a line in the credentials file
#                       or with command line flags (-F/-U).
#                       See help and README for details.
# 2011/04/14 v1.33      Made help sensitive to path config/flags.
#
# 2011/05/26 v2.00      Switched to use Fluidinfo-style paths by default.
#                       Fixed bug affecting some unicode characters in queries.
#                       Added --version/-V flag to report version
#
# 2011/06/04 v2.01      Added pwd/pwn, whoami and su commands.
#                       Added embryonic ls command (including embryonic
#                       ls -l).
#                       Added -u option to allow a user to be specified.
#                       Improved handling of encoding to use
#                       sys.getfilesystemencoding() rather than assuming
#                       UTF-8, at least in some places, but this transition
#                       is incomplete.
#
# 2011/06/04 v2.02      Fixed encodings so that unicode usernames
#                       and passwords work.
#                       Credentials file must be encoded in UTF-8.
#
# 2011/06/04 v2.03      More complete unicode improvements.
#                       To a very good approximation, it is now true that
#                          - All strings are stored internally as unicode
#                          - Keyboard input is read correctly using the
#                            encoding specified by sys.getfilesystemencoding()
#                          - Data is UTF-8-encoded just before transmitting
#                            to Fluidinfo
#                          - Data is decode from UTF-8 immediately upon
#                            receipt from Fluidinfo.
#                      Not all the test data has yet been upgraded this way
#                      and there is still far too little unicode data in
#                      the tests.
#
#                      At the time of this commit, lots of things are
#                      not working with unicode namespaces, but that appears
#                      to be a problem with the main instance; similar
#                      things are working on the Sandbox.
#
# 2011/06/05 v2.04     Completed ls command, adding ls -L
#                      (well, -g still to add...)
#                      Completed draft of complete documentation.
#
# 2011/06/05 v2.05     Added -g (group) flag to ls.
#                      Added fdb perms command.
#                      Completed first draft of full command line
#                      which is now included in the distribution
#                      and available online, hosted in Fluidinfo
#                      itself/ at
#                      http://fluiddb.fluidinfo.com/about/fdb/njr/index.html.
#
# 2011/06/07 v2.06     Fixed some import problems caused by renaming
#                      fdb.py as fdb.
#
# 2011/06/07 v2.07     Added perms lock command (to remove all write perms)
#
# 2011/06/09 v2.08     Changed all the optparse stuff back not to use
#                      unicode as a lot of versions of optparse don't
#                      seem to work with unicode.



