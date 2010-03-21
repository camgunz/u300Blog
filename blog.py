# -*- coding: UTF-8 -*-
from __future__ import with_statement # needs Python >= 2.5!
import os, cgi, sys, email, email.message, fcntl, codecs, operator
# import cgitb; cgitb.enable()
from string import Template
from urllib import quote, url2pathname
from decimal import Decimal
from datetime import date, datetime, timedelta
from contextlib import contextmanager
# Configuration
BLOG_TITLE = u'Completely Unique, Yet Clever'
RSS_TITLE = BLOG_TITLE + u' RSS'
RSS_DESC = u'The latest posts from ' + BLOG_TITLE
BASE_URL = u'blog'            # means http://www.server.com/blog
BASE_CSS_URL = u'/styles'     # means http://www.server.com/styles
BLOG_FOLDER = u'/var/www/html/blog'
MAKE_STATIC_AFTER = -1  # see http://charlieg.net/blog/u300 Blog/ for details
THEME_FOLDER = u'/var/www/html/blog'
THEME_NAME = u'brazil'
POSTS_PER_PAGE = 5
POST_FORMAT = 'markdown'    # can also be 'textile' or 'raw' (default == 'raw')
COMMENT_FORMAT = 'markdown' # same as above
FSYNC_AFTER_WRITING = False # fsync's a file after writing to it
# End configuration
POST_FORMAT = (POST_FORMAT or 'raw').lower().strip()
COMMENT_FORMAT = (COMMENT_FORMAT or 'raw').lower().strip()
PPARSE, POST_EXT, POST_FILENAME = (lambda x: x, u'.html', u'post.html')
CPARSE = lambda x: x
MORE_TAG = u'<!-- MORE -->'

def send_response(data, mime_type='text/plain', headers=[]):
    s = u'%sContent-Type: %s; charset=UTF-8\n\r\n%s\r'
    print (s % ('\n'.join(headers), mime_type, data)).encode('utf8')
    sys.exit(0)

try:
    if POST_FORMAT == 'markdown':
        from markdown import markdown as PPARSE
        POST_EXT, POST_FILENAME = (u'.mkd', u'post.mkd')
    elif POST_FORMAT == 'textile':
        from textile import textile as PPARSE
        POST_EXT, POST_FILENAME = (u'.textile', u'post.textile')
    if COMMENT_FORMAT == 'markdown':
        from markdown import markdown as CPARSE
    elif COMMENT_FORMAT == 'textile':
        from textile import textile as CPARSE
except ImportError, e:
    es, fs = (str(e), "Can't import %(x)s, try 'easy_install %(x)s' as root")
    'textile' in es and send_response(fs % {'x': 'textile'})
    'markdown' in es and send_response(fs % {'x': 'markdown'})
    raise

STATIC_DAYS = timedelta(days=MAKE_STATIC_AFTER)
STATIC_DAYS = MAKE_STATIC_AFTER<0  and timedelta(days=0) or STATIC_DAYS
STATIC_DAYS = MAKE_STATIC_AFTER==0 and timedelta(days=999999999) or STATIC_DAYS
MAX_HEADER_SIZE = 256
BASE_URL = BASE_URL.strip('/')
BLOG_URL = u'http://%s/' % os.environ.get('SERVER_NAME', u'localhost')+BASE_URL
CSS_URL = u'/'.join([BASE_CSS_URL, u'u300_%s.css' % (THEME_NAME)])
BLOG_FOLDER = os.path.abspath(os.path.expanduser(BLOG_FOLDER))
THEME_FOLDER = os.path.abspath(os.path.expanduser(THEME_FOLDER))
TEMPLATE_FOLDER = os.path.join(THEME_FOLDER, THEME_NAME)
COMMENT_SPLITTER = 80 * '='
POST_TIMESTAMP_FORMAT = COMMENT_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'
WDNS = (u'Mon', u'Tue', u'Wed', u'Thu', u'Fri', u'Sat', u'Sun')
MNS = (u'Jan', u'Feb', u'Mar', u'Apr', u'May', u'Jun',
       u'Jul', u'Aug', u'Sep', u'Oct', u'Nov', u'Dec')

def slurp_file(file_path, decode=True, offset=None, size=None):
    f = lambda: open(file_path.encode('utf8'))
    if decode:
        f = lambda: codecs.open(file_path.encode('utf8'), encoding='utf8')
    with f() as fobj:
        offset and fobj.seek(offset)
        return (size is not None and fobj.read(size) or fobj.read())

def parse(s, decode=False):
    m = email.message_from_string(s)
    if 'date' in m:
        fmt = decode and COMMENT_TIMESTAMP_FORMAT or POST_TIMESTAMP_FORMAT
        m.replace_header('date', datetime.strptime(m['date'], fmt))
    else:
        raise Exception("Required header 'date' not found in [%r]" % (s))
    if 'commenter' in m:
        m['commenter'] = m['commenter'].decode('base64').decode('utf8')
    elif not 'poster' in m:
        raise Exception
    d = dict(m.items())
    d['get_payload'] = lambda: m.get_payload(decode=decode).decode('utf8')
    return d

read_template = lambda x: Template(slurp_file(os.path.join(TEMPLATE_FOLDER, x)))
get_base_dict = lambda: dict(BASE_DICT.items())
tsub = lambda t, d: t.substitute(d)

HEADER_TEMPLATE = read_template(u'header_template.html')
POST_TEMPLATE = read_template(u'post_template.html')
MORE_TEMPLATE = read_template(u'more_template.html')
OLDER_TEMPLATE = read_template(u'older_template.html')
COMMENT_TEMPLATE = read_template(u'comment_template.html')
FULL_POST_TEMPLATE = read_template(u'full_post_template.html')
COMMENT_TEMPLATE = read_template(u'comment_template.html')
FOOTER_TEMPLATE = read_template(u'footer_template.html')
RSS_TEMPLATE = read_template(u'rss_template.html')
POST_RSS_TEMPLATE = read_template(u'post_rss_template.html')
make_page_template = \
    lambda x: Template(HEADER_TEMPLATE.template + x + FOOTER_TEMPLATE.template)
FRONT_PAGE_TEMPLATE = make_page_template(OLDER_TEMPLATE.template)
LAST_PAGE_TEMPLATE = make_page_template('')
EPOCH = datetime(1970, 1, 1)
BASE_DICT = {'blog_title': BLOG_TITLE, 'base_url': BASE_URL, 'css_url': CSS_URL,
             'rss_title': RSS_TITLE, 'blog_url': BLOG_URL, 'rss_desc': RSS_DESC}

def get_rfc822_timestamp(dt=None):
    dt = dt or datetime.utcnow()
    return u'%s, %02d %s %04d %02d:%02d:%02d UTC' % (WDNS[dt.weekday()],
            dt.day, MNS[dt.month-1], dt.year, dt.hour, dt.minute, dt.second)

def milliseconds_since_epoch(dt=None):
    td = (dt or datetime.utcnow()) - EPOCH
    return ((td.days * 86400) + td.seconds + 
            (Decimal(td.microseconds) / Decimal(1000000))) * Decimal(1000)

def until_more(f):
    s = f()
    i = s.find(MORE_TAG)
    return i != -1 and (True, lambda: s[:i]) or (False, lambda: s)

def list_post_paths():
    out = []
    for x in os.listdir(BLOG_FOLDER):
        p = os.path.join(BLOG_FOLDER, x.decode('utf8'))
        q = os.path.join(p, POST_FILENAME.decode('utf8')).encode('utf8')
        os.path.isdir(p.encode('utf8')) and os.path.isfile(q) and out.append(p)
    return out

@contextmanager
def open_file_exclusively(file_path, exists=True):
    fp = file_path.encode('utf8')
    flags = os.O_RDWR | os.O_APPEND
    if not os.path.isfile(fp):
        flags |= (os.O_CREAT | os.O_EXCL)
    fd = os.open(fp, flags)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        yield fd
        FSYNC_AFTER_WRITING and os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

@contextmanager
def open_file_shared(file_path):
    fd = os.open(file_path.encode('utf8'), os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_SH)
    fobj = os.fdopen(fd, 'rb')
    try:
        yield fobj
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fobj.close()

def add_comment(timestamp, c, b, comment_filepath):
    msg = email.message.Message()
    t = (timestamp, commenter.encode('base64').strip(), 'base64')
    msg['date'], msg['commenter'], msg['content-transfer-encoding'] = t
    msg.set_payload(b.encode('base64').strip())
    with open_file_exclusively(comment_filepath) as fd:
        os.write(fd, msg.as_string() + '\n' + COMMENT_SPLITTER)

def parse_comments(post_folder, just_count=False):
    comments_file = os.path.join(post_folder, u'comments.txt')
    if not os.path.isfile(comments_file.encode('utf8')):
        return u''
    with open_file_shared(comments_file) as fobj:
        file_data = fobj.read()
    if just_count:
        return file_data.count(COMMENT_SPLITTER)
    comments = []
    for chunk in (x.strip() for x in file_data.split(COMMENT_SPLITTER)):
        if chunk:
            try:
                comments.append(parse(chunk, decode=True))
            except Exception, e:
                pass
    return comments

def parse_post(post_folder, show_comments=False):
    post_file = os.path.join(post_folder, POST_FILENAME)
    d = parse(slurp_file(post_file, decode=False))
    d['raw_title'] = os.path.basename(post_folder)
    d['post_file'], d['title'] = (post_file, cgi.escape(d['raw_title']))
    d['url_title'] = cgi.escape(quote(d['raw_title'].encode('utf8')))
    d['rfc822_date'] = get_rfc822_timestamp(d['date'])
    d['static_post_file'] = os.path.join(post_folder, u'index.html')
    d['make_static'] = \
            MAKE_STATIC_AFTER < 0 or datetime.now() - d['date'] >= STATIC_DAYS
    pcs = parse_comments(post_folder)
    d['get_body'] = lambda: PPARSE(d['get_payload']())
    found_more, d['get_until_more'] = until_more(d['get_body'])
    d['comment_num'] = len(pcs)
    d.update(get_base_dict())
    if not show_comments:
        d['get_comments'] = lambda: u''
        d['template'] = found_more and MORE_TEMPLATE or POST_TEMPLATE
    else:
        d['get_comments'] = lambda: u'\n'.join([render_comment(x) for x in pcs])
        d['template'] = \
            d['make_static'] and POST_TEMPLATE or FULL_POST_TEMPLATE
    return d

def get_parsed_posts(paths, page_num=0, show_comments=False):
    start, end = (page_num * POSTS_PER_PAGE, (page_num+1) * POSTS_PER_PAGE)
    ds = [parse_post(x, show_comments=show_comments) for x in paths]
    return sorted(ds, reverse=True, key=operator.itemgetter('date'))[start:end]

def render_comment(parsed_comment):
    parsed_comment['date'] = milliseconds_since_epoch(parsed_comment['date'])
    parsed_comment['body'] = parsed_comment['get_payload']()
    return tsub(COMMENT_TEMPLATE, parsed_comment)

def render_post(d, show_comments=False):
    d['comments'] = d['get_comments']()
    s = d['comment_num'] == 1 and u'%d comment' or u'%d comments'
    d['comment_count'] = s % (d['comment_num'])
    d['until_more_body'], d['body'], d['date'] = (d['get_until_more'](),
                          d['get_body'](), milliseconds_since_epoch(d['date']))
    if d['make_static']:
        old_body = d['body']
        d['body'] = tsub(d['template'], d)
        with open_file_exclusively(d['static_post_file']) as fd:
            os.write(fd, tsub(LAST_PAGE_TEMPLATE, d).encode('utf8'))
        d['body'] = old_body
    return tsub(d['template'], d)

def render_page(paths, page_num=None):
    show, page_num = (page_num is None, page_num or 0)
    use_main = not show and len(paths) > ((page_num + 1) * POSTS_PER_PAGE)
    d, parsed = (get_base_dict(), get_parsed_posts(paths, page_num, show))
    if page_num and not parsed:
        send_response(u'Sorry, 404', headers=['Status: 404 Not Found'])
    d['body'] = len(parsed) == 1 and render_post(parsed[0], show) or \
                            u'\n'.join([render_post(x, show) for x in parsed])
    d['next_page'] = page_num + 1
    return tsub(use_main and FRONT_PAGE_TEMPLATE or LAST_PAGE_TEMPLATE, d)

def render_rss():
    d, pposts = (get_base_dict(), get_parsed_posts(list_post_paths(), 0))
    if not len(pposts):
        d['build_date'], d['items'] = (get_rfc822_timestamp(), u'')
    else:
        d['build_date'] = pposts[0]['rfc822_date']
        d['items'] = u''.join([tsub(POST_RSS_TEMPLATE, pp) for pp in pposts])
    return tsub(RSS_TEMPLATE, d)

form = cgi.FieldStorage()
try:
    uri = os.environ['REQUEST_URI'].lstrip('/')
    uri = url2pathname(uri.replace(BASE_URL.encode('utf8'), '', 1)).strip('/')
    post_title = uri.decode('utf8')
    if os.environ.get('QUERY_STRING', ''):
        post_title = uri[:-(len(os.environ['QUERY_STRING'])+1)].decode('utf8')
except KeyError:
    post_title = None
if not post_title:
    page_num = form.getfirst('p', 0)
    page_num == 'rss' and send_response(render_rss(), 'application/rss+xml')
    send_response(render_page(list_post_paths(), int(page_num)), 'text/html')
post_folder = os.path.join(BLOG_FOLDER, post_title)
if not os.path.isdir(post_folder.encode('utf8')):
    send_response(u'Sorry, 404', headers=['Status: 404 Not Found'])
if os.environ.get('REQUEST_METHOD', 'GET') == 'POST':
    if not 'body' in form or not form.getfirst('body', u''):
        send_response(u'No body', headers=['Status: 400 Bad Request'])
    if os.path.isfile(os.path.join(post_folder, u'index.html').encode('utf8')):
        send_response(u'Comments disabled', headers=['Status: 400 Bad Request'])
    comment_body = form.getfirst('body', u'').decode('utf8')
    timestamp = datetime.utcnow().strftime(COMMENT_TIMESTAMP_FORMAT)
    commenter = form.getfirst('commenter', u'anon').decode('utf8')
    post_comment_file_path = os.path.join(post_folder, u'comments.txt')
    add_comment(timestamp, commenter, comment_body, post_comment_file_path)
if post_title:
    if os.path.isfile(os.path.join(post_folder, POST_FILENAME)):
        send_response(render_page([post_folder]), 'text/html')
    send_response(u'Sorry, 404', headers=['Status: 404 Not Found'])
send_response(render_page(list_post_paths()), 'text/html')

