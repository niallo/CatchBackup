#!/usr/bin/env python

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
import mimetypes
import os
import re
import shutil
import string
import sys
import urllib

API = "api.catch.com"

OUTPUT_TEMPLATE = """
Created Date: $created_at
Modified Date: $modified_at
Longitude: $longitude
Latitude: $latitude
Tags: $tags
Attachments: $attachments

$text
"""

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
        # See http://bugs.python.org/issue11236
        if "\x03" in password:
            raise KeyboardInterrupt()

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

class DirectoryRequired(Exception):
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

        ''' Fetch the data from Catch '''

        self.conn = httplib.HTTPSConnection(API)
        headers = self._make_basic_auth_header()

        req = self.conn.request("GET", "/v2/notes.json?full=1", headers=headers)

        res = self.conn.getresponse()

        if res.status != 200:
            sys.stderr.write("ERROR: %d response from server. Reason: %s\n" %(
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

    def dump_raw_notes(self, filename=None):
        if not filename:
            raise FilenameRequired()

        if not self.raw_data:
            raise NoDataError()

        f = open(filename, "w")
        f.write(self.raw_data)
        f.close()

    def dump_cooked_notes_and_media(self, directory=None):
        if not directory:
            raise DirectoryRequired()
        shutil.rmtree(directory, ignore_errors=True)
        try:
            os.makedirs(directory)
        except os.error:
            pass

        if not self.cooked_data:
            raise NoDataError()

        def fetch_attachments(note, directory):
            try:
                os.makedirs("%s/media" %(directory))
            except os.error:
                pass

            def get_extension(content_type):
                mimetypes.init()
                mappings = { 'image/jpeg' : '.jpg' }
                return mappings.get(content_type,
                        mimetypes.guess_extension(content_type))


            attachments = []
            for idx, media in enumerate(note["media"]):
                src = "%s?original=true" %(media["src"])
                filename = "%s/media/%s-%s%s" %(directory, note["id"], idx,
                        get_extension(media["content_type"]))
                sys.stdout.write("Fetching media for note %s size %d bytes\n"
                        %(note["id"], int(media["size"])))
                uf = urllib.urlopen(src)
                data = uf.read()
                uf.close()
                f = open(filename, "w")
                f.write(data)
                f.close()
                attachments.append(filename)

            return attachments

        def make_note_filename(note):
            sample_text = ""
            l = note.get("text", "").splitlines()
            if l:
                sample_text = re.sub(r"[^A-Za-z0-9]*", "", l[0])[:32]
                if sample_text:
                    sample_text = "%s-" % sample_text

            filename = "%s%s-%s.txt" %(sample_text, note["id"],
                note["created_at"].strftime("%Y%m%d-%H%M%S"))

            return filename

        def render_note_template(note, attachments):
            longitude = ""
            latitude = ""
            if note.get("location"):
                longitude = note["location"]["features"][0]["geometry"]["coordinates"][1]
                latitude = note["location"]["features"][0]["geometry"]["coordinates"][0]

            attachments = " ".join(attachments)
            s = string.Template(OUTPUT_TEMPLATE)

            subs = {
                "created_at" : note["created_at"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "modified_at" : note["modified_at"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "text" : note.get("text", ""),
                "tags" : " ".join(["#%s" %(tag) for tag in note.get("tags",
                    [])]),
                "longitude" : longitude,
                "latitude" : latitude,
                "attachments" : attachments }

            return s.safe_substitute(subs)

        for note in self.cooked_data["notes"]:
            filename = make_note_filename(note)
            attachments = fetch_attachments(note, directory)
            data = render_note_template(note, attachments)
            f = open("%s/%s" %(directory, filename), "w")
            f.write(data.encode("utf-8"))
            f.close()


def main():
    parser = argparse.ArgumentParser(description='Backup data from Catch API')
    parser.add_argument('-f', '--file', dest='outfile',
            help='JSON data file to write (default: notes.json)',
            default="notes.json")

    parser.add_argument('-d', '--dir', dest='dir',
            help='output directory for media and one note per file dump')

    parser.add_argument('-u', '--username', dest='username', help='username to use')

    args = parser.parse_args()

    if not args.username:
        args.username = get_username()
    args.password = get_password()

    cb = CatchBackup(username=args.username, password=args.password)

    sys.stdout.write("Fetching notes...\n")
    data = cb.fetch_data()

    sys.stdout.write("Writing notes to %s\n" %(args.outfile))
    cb.dump_raw_notes(filename=args.outfile)
    sys.stdout.write("JSON Backup complete!\n")

    if args.dir:
        sys.stdout.write("Starting one-note-per-file and media dump. Output dir: %s\n"
                %(args.dir))
        cb.dump_cooked_notes_and_media(directory=args.dir)
        sys.stdout.write("One-note-per-file and media dump complete\n")



if __name__ == "__main__":
    main()
