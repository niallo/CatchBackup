#!/usr/bin/env python2.7

"""

Backup notes and media from Catch account to local disk

:copyright: Copyright 2011 Niall O'Higgins
:license: BSD, see LICENSE for details.

"""

import argparse
import base64
import datetime
import getpass
import httplib
import json
import sqlite3
import sys
import urllib

API = "api.catch.com"

def get_username():
    ''' Read username from terminal '''
    while True:
        sys.stdout.write("Username: ")
        username = sys.stdin.readline().strip()
        if username:
            break

    return username

def get_password():
    ''' Read password from terminal '''
    while True:
        password = getpass.getpass("Password: ")
        if password:
            break

    return password

class UsernameRequired(Exception):
    pass

class PasswordRequired(Exception):
    pass

class FilenameRequired(Exception):
    pass

class NoDataError(Exception):
    pass


class CatchBackup(object):

    def __init__(self, username=None, password=None):

        if not username:
            raise UsernameRequired()
        if not password:
            raise PasswordRequired()

        self.username = username
        self.password = password
        self.raw_data = None
        self.cooked_data = None

    def _make_basic_auth_header(self):
        ''' Basic auth '''
        return {"Authorization":"Basic %s" %(
            base64.b64encode("%s:%s" %(self.username, self.password)))}

    def fetch_data(self):

        ''' Fetch the raw unstructured workout data from Catch API. Other
        methods will parse this into structured  '''

        self.conn = httplib.HTTPSConnection(API)
        headers = self._make_basic_auth_header()

        req = self.conn.request("GET", "/v2/notes.json?full=1", headers=headers)

        res = self.conn.getresponse()

        if res.status != 200:
            sys.stderr.write("%d response from server.\n Reason: %s" %(
                res.status,
                res.reason))
            sys.exit(1)

        data = res.read()

        self.raw_data = data
        notes = json.loads(data)
        res.close()

        def parse_rfc3339(s):
            if not s: return None
            return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ')

        # convert timestamps to native Python types
        for note in notes["notes"]:
            note["created_at"] = parse_rfc3339(note.get("created_at"))
            note["modified_at"] = parse_rfc3339(note.get("modified_at"))
            note["reminder_at"] = parse_rfc3339(note.get("reminder_at"))

        self.cooked_data = notes

        return notes

    def dump_notes(self, filename=None):
        if not filename:
            raise FilenameRequired()

        if not self.raw_data:
            raise NoDataError()

        f = open(filename, "w")
        f.write(self.raw_data)
        f.close()

def main():
    parser = argparse.ArgumentParser(description='Backup data from Catch API')
    parser.add_argument('-f', '--file', dest='outfile',
            help='JSON data file to write (default: notes.json)',
            default="notes.json")

    parser.add_argument('-u', '--username', dest='username', help='username to use')


    args = parser.parse_args()

    if not args.username:
        args.username = get_username()
    args.password = get_password()

    cb = CatchBackup(username=args.username, password=args.password)

    sys.stdout.write("Fetching notes...\n")
    data = cb.fetch_data()

    sys.stdout.write("Writing notes to %s\n" %(args.outfile))
    cb.dump_notes(filename=args.outfile)
    sys.stdout.write("Backup complete!\n")

if __name__ == "__main__":
    main()
