" Copyright (C) 2010 Charles Gunyon
"
" This program is free software; you can redistribute it and/or modify
" it under the terms of the GNU General Public License as published by
" the Free Software Foundation; either version 2, or (at your option)
" any later version.
"
" This program is distributed in the hope that it will be useful,
" but WITHOUT ANY WARRANTY; without even the implied warranty of
" MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
" GNU General Public License for more details.
"
" You should have received a copy of the GNU General Public License
" along with this program; if not, write to the Free Software Foundation,
" Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.  
"
" This is based on blog.vim, by Adrien Friggeri.
"
" Maintainer:	Charlie Gunyon <charles.gunyon@gmail.com>
" URL:		    http://charlieg.net/blog/u3b.vim
" Version:	    0.3
" Last Change:  March 21, 2010
"
" Commands :
" ":U3Blist"
"   Lists all posts
" ":U3Bnew"
"   Creates a new post
" ":U3Bedit <post>"
"   Edits the specified post
" ":U3Bsave <post>"
"   Saves a post
" ":U3Beditcomments <post>"
"   Edits the specified post's comments
" ":U3Bsavecomments <post>"
"   Saves the specified post's comments
"
" Configuration : 
"   Edit the "Settings" section (starts at line 51).
"
" Usage : 
"   Just fill in the blanks, do not modify the highlighted parts and everything
"   should be ok.  You also need the paramiko library (easy_install paramiko).

command! -nargs=0 U3Blist exec("py u3b_list_posts()")
command! -nargs=0 U3Bnew exec("py u3b_new_post()")
command! -nargs=1 U3Bsave exec('py u3b_send_post(<f-args>)')
command! -nargs=1 U3Bwrite exec('py u3b_send_post(<f-args>)')
command! -nargs=1 U3Bedit exec('py u3b_open_post(<f-args>)')
command! -nargs=1 U3Beditcomments exec('py u3b_edit_comments(<f-args>)')
command! -nargs=1 U3Bsavecomments exec('py u3b_send_comments(<f-args>)')
python <<EOF
# -*- coding: utf-8 -*-

from __future__ import with_statement
import os, sys, vim, stat, email, email.generator, urllib2, datetime
from contextlib import contextmanager
from paramiko import SSHClient, AutoAddPolicy
from StringIO import StringIO

#####################
#      Settings     #
#####################

# The hostname of the server that hosts your blog
U3B_BLOG_HOSTNAME = 'superblog.com'
# The root URL of your blog
U3B_BLOG_URL = 'http://superblog.com/blog'
# The port where it listens for SSH
U3B_BLOG_PORT = 22
# The username to login with
U3B_BLOG_USERNAME = 'superblogger'
# The corresponding password (optional if you have keys setup)
U3B_BLOG_PASSWORD = ''
# Whether or not to use ssh-agent
U3B_ALLOW_AGENT = True
# Whether or not to register SSH keys located in the default locations
U3B_LOOK_FOR_KEYS = True
# The full path to a public key to use for authentication
U3B_PUBLIC_KEY_FILENAME = None
# How many seconds to wait on the server before timing out
U3B_TIMEOUT = 20
# The full path to your blog folder on the server
U3B_BLOG_FOLDER = '/var/www/html/blog'
# The markup your posts use
U3B_POST_FORMAT = 'markdown'
# How to set textwidth when editing a post
U3B_TEXTWIDTH = 79
# The type of server that hosts your u300 Blog, 'windows' or something else
U3B_SERVER_TYPE = 'unix'

#####################
# Do not edit below #
#####################

if U3B_SERVER_TYPE.lower().strip() == 'windows':
    U3B_PATH_SEP = '\\'
else:
    U3B_PATH_SEP = '/'
u3b_join = lambda *x: U3B_PATH_SEP.join(x)
U3B_DIR_MODE =  stat.S_ISGID | stat.S_IRWXU | stat.S_IRWXG
U3B_FILE_MODE = stat.S_ISGID | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP |\
                stat.S_IROTH
U3B_POST_FILENAME, U3B_SYNTAX = ('post.html', 'html')
U3B_COMMENT_SPLITTER = 80 * '='
U3B_COMMENT_FILENAME = 'comments.txt'
U3B_STATIC_FILENAME = 'index.html'
if U3B_POST_FORMAT == 'markdown':
    U3B_POST_FILENAME, U3B_SYNTAX = ('post.mkd', 'mkd')
elif U3B_POST_FORMAT == 'textile':
    U3B_POST_FILENAME, U3B_SYNTAX = ('post.textile', 'textile')
U3B_EDIT = True
if U3B_BLOG_URL.startswith('http://'):
    U3B_BLOG_URL = U3B_BLOG_URL[7:]
U3B_BLOG_URL = 'http://' + urllib2.quote(U3B_BLOG_URL)

def read_file(sftp, file_path):
    fobj = sftp.open(file_path)
    try:
        data = fobj.read()
    finally:
        fobj.close()
    return data

def write_file(sftp, file_path, data):
    fobj = sftp.open(file_path, 'w')
    try:
        fobj.write(data)
        fobj.flush()
    finally:
        fobj.close()

def delete_file(sftp, file_path):
    sftp.unlink(file_path)

def mkdir(sftp, dir_path):
    try:
        sftp.stat(dir_path)
    except IOError, e:
        if e.errno == 2:
            sftp.mkdir(post_name)
            sftp.chmod(post_name, U3B_DIR_MODE)
        else:
            raise

def make_abs(path):
    if not os.path.isabs(path):
        return u3b_join(U3B_POST_FOLDER, path)
    else:
        return path

class FakeSFTP(object):

    def open(self, post_name, mode='r'):
        post_name = make_abs(post_name)
        return open(post_name, mode)

    def unlink(self, file_path):
        os.unlink(make_abs(file_path))

    def stat(self, path):
        return os.stat(make_abs(path))

    def mkdir(self, path):
        os.mkdir(make_abs(path))

    def chmod(self, path, mode):
        os.chmod(make_abs(path), mode)

    def listdir(self, path):
        return os.listdir(make_abs(path))

    def rename(self, old, new):
        return os.rename(make_abs(old), make_abs(new))

class U3B(object):

    @contextmanager
    def connection(self):
        if U3B_BLOG_HOSTNAME in ('localhost', '127.0.0.1'):
            yield FakeSFTP()
        else:
            ssh = SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            ssh.connect(U3B_BLOG_HOSTNAME, port=U3B_BLOG_PORT,
                        username=U3B_BLOG_USERNAME, allow_agent=U3B_ALLOW_AGENT,
                        look_for_keys=U3B_LOOK_FOR_KEYS,
                        key_filename=U3B_PUBLIC_KEY_FILENAME,
                        timeout=U3B_TIMEOUT)
            try:
                sftp = ssh.open_sftp()
                # sftp.chdir(U3B_BLOG_FOLDER)
                yield sftp
            finally:
                ssh.close()

    def list_post_names(self):
        post_names = []
        with self.connection() as conn:
            ls = conn.listdir(U3B_BLOG_FOLDER)
            ls = [u3b_join(U3B_BLOG_FOLDER, x) for x in ls]
            for d in [x for x in ls if stat.S_ISDIR(conn.stat(x).st_mode)]:
                try:
                    conn.stat(u3b_join(d, U3B_POST_FILENAME))
                    post_names.append(os.path.basename(d))
                except (OSError, IOError), e:
                    if not e.errno == 2:
                        raise
        return post_names

    def read_rendered_post(self, post_name):
        url = '/'.join([U3B_BLOG_URL, urllib2.quote(post_name)])
        urlobj = urllib2.urlopen(url)
        data = urlobj.read()
        urlobj.close()
        return data

    def make_post_static(self, conn, post_name):
        pfp = u3b_join(U3B_BLOG_FOLDER, post_name, U3B_STATIC_FILENAME)
        write_file(conn, pfp, self.read_rendered_post(post_name))

    def make_post_dynamic(self, conn, post_name):
        pfp = u3b_join(U3B_BLOG_FOLDER, post_name, U3B_STATIC_FILENAME)
        delete_file(conn, pfp)

    def read_post_comments(self, post_name):
        output = StringIO()
        dg = email.generator.DecodedGenerator(output)
        with self.connection() as conn:
            self.make_post_static(conn, post_name)
            p = u3b_join(U3B_BLOG_FOLDER, post_name, U3B_COMMENT_FILENAME)
            data = read_file(conn, p)
            for chunk in (x.strip() for x in data.split(U3B_COMMENT_SPLITTER)):
                if chunk:
                    try:
                        msg = email.message_from_string(chunk)
                        msg.replace_header('commenter',
                                           msg['commenter'].decode('base64'))
                        dg.flatten(msg)
                        output.write('\n' + U3B_COMMENT_SPLITTER)
                    except Exception, e:
                        pass
        return output.getvalue().splitlines()

    def save_post_comments(self, post_name, data):
        output = StringIO()
        dg = email.generator.Generator(output)
        for chunk in (x.strip() for x in data.split(U3B_COMMENT_SPLITTER)):
            if chunk:
                try:
                    msg = email.message_from_string(chunk)
                    msg.replace_header('commenter',
                                       msg['commenter'].encode('base64'))
                    msg.set_payload(msg.get_payload().encode('base64'))
                    dg.flatten(msg)
                    output.write('\n' + U3B_COMMENT_SPLITTER)
                except Exception, e:
                    pass
        p = u3b_join(U3B_BLOG_FOLDER, post_name, U3B_COMMENT_FILENAME)
        with self.connection() as conn:
            self.make_post_dynamic(conn, post_name)
            write_file(conn, p, output.getvalue())

    def read_post(self, post_name):
        with self.connection() as conn:
            p = u3b_join(U3B_BLOG_FOLDER, post_name, U3B_POST_FILENAME)
            return read_file(conn, p)

    def save_post(self, post_name, post_data):
        post_path = u3b_join(U3B_BLOG_FOLDER, post_name)
        with self.connection() as conn:
            try:
                conn.stat(post_path)
            except IOError, e:
                if e.errno == 2:
                    conn.mkdir(post_path)
                    conn.chmod(post_path, U3B_DIR_MODE)
                else:
                    raise
            temp_fn = '.' + U3B_POST_FILENAME + '.tmp'
            temp_p = u3b_join(U3B_BLOG_FOLDER, post_name, temp_fn)
            p = u3b_join(U3B_BLOG_FOLDER, post_name, U3B_POST_FILENAME)
            write_file(conn, temp_p, post_data)
            conn.chmod(temp_p, U3B_FILE_MODE)
            try:
                conn.unlink(p)
            except IOError, e:
                if e.errno != 2:
                    raise
            conn.rename(temp_p, p)

def u3b_edit_off():
    global U3B_EDIT
    if U3B_EDIT:
        U3B_EDIT = False
        for x in ["i","a","s","o","I","A","S","O"]:
            vim.command('map %s <nop>' % (x))

def u3b_edit_on():
    global U3B_EDIT
    if not U3B_EDIT:
        U3B_EDIT = True
        for x in ["i","a","s","o","I","A","S","O"]:
            vim.command('unmap %s' % (x))

def u3b_new_post():
    del vim.current.buffer[:]
    u3b_edit_on()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    vim.current.buffer[0] = 'date: ' + now
    vim.current.buffer.append('poster: ')
    vim.current.buffer.append('')
    vim.current.buffer.append('')
    vim.current.window.cursor = (2, 8)
    vim.command('set nomodified')
    vim.command('set textwidth=' + str(U3B_TEXTWIDTH))
    vim.command("set syntax=" + U3B_SYNTAX)

def u3b_send_post(post_name):
    U3B().save_post(post_name, '\n'.join(vim.current.buffer))
    vim.command('set nomodified')

def u3b_open_post(post_name):
    u3b_edit_on()
    vim.current.buffer[:] = U3B().read_post(post_name).splitlines()
    vim.current.window.cursor = (len(vim.current.buffer), 0)
    vim.command('set nomodified')
    vim.command('set textwidth=' + str(U3B_TEXTWIDTH))
    vim.command("set syntax=" + U3B_SYNTAX)

def u3b_edit_comments(post_name):
    u3b_edit_on()
    comments = U3B().read_post_comments(post_name)
    # print "Comments: %r" % (comments)
    vim.current.buffer[:] = comments
    vim.command('set nomodified')

def u3b_send_comments(post_name):
    U3B().save_post_comments(post_name, '\n'.join(vim.current.buffer))
    vim.command('set nomodified')

def u3b_list_edit():
    row, col = vim.current.window.cursor
    post_name = vim.current.buffer[row-1]#.split()[0]
    u3b_open_post(post_name)

def u3b_list_posts():
    vim.current.buffer[:] = U3B().list_post_names()
    vim.command('set nomodified')
    u3b_edit_off()
    # vim.current.window.cursor = (2, 0)
    vim.command('map <enter> :py u3b_list_edit()<cr>')

