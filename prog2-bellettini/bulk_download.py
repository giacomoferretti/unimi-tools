#!/usr/bin/env python3

# Copyright 2021 Giacomo Ferretti
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import sys
import time
import json
import urllib
import argparse

import requests
import youtube_dl
from bs4 import BeautifulSoup

# Config
VERBOSE           = True
USER_AGENT        = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.35'
PROXY_ENABLED     = False
PROXY_URL         = 'http://localhost:8080'
VERIFY_ENABLED    = True
SUPPRESS_WARNINGS = False
SOUP_PARSER       = 'html5lib'

# Initaliaze necessary components
headers = {
    'User-Agent': USER_AGENT
}

proxies = None
if PROXY_ENABLED:
    proxies = {
        'http': PROXY_URL,
        'https': PROXY_URL
    }

if SUPPRESS_WARNINGS:
    __import__('urllib3').disable_warnings(__import__('urllib3').exceptions.InsecureRequestWarning)

# Endpoints
TARGET = 'https://homes.di.unimi.it/bellettini/sito/progII.html'

def mkdir(path):
    try:
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        pass

def print_flush(message, end='', file=sys.stdout, flush=True):
    print(message, end=end, file=file, flush=flush)

# https://stackoverflow.com/questions/1094841/
def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return '%3.1f%s%s' % (num, unit, suffix)
        num /= 1024.0
    return '%.1f%s%s' % (num, 'Yi', suffix)

# BASE https://stackoverflow.com/questions/16694907/
#  MOD https://stackoverflow.com/questions/15644964/
def download_file(session, url, auth=None, name=None, folder=None):
    if name is None:
        name = url.split('/')[-1]

    if folder is not None:
        mkdir(folder)
        name = os.path.join(folder, name)
    
    # NOTE the stream=True parameter below
    with session.get(url, auth=auth, stream=True) as r:
        r.raise_for_status()

        with open(name, 'wb') as f:
            dl = 0
            file_size = r.headers.get('content-length')

            if file_size:
                file_size = int(file_size)

            start = time.perf_counter()

            for chunk in r.iter_content(chunk_size=8192):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                #if chunk:
                f.write(chunk)

                if file_size:
                    dl += len(chunk)
                    done = int(50 * dl / file_size)
                    #print_flush('\r[{}{}] {:3.1f} Mbps'.format('=' * done, ' ' * (50 - done), dl // (time.perf_counter() - start) / 100000))
                    print_flush('\r\x1b[K')
                    print_flush('[{}{}] {}/{} {:3.1f} Mbps'.format('=' * done, ' ' * (50 - done), sizeof_fmt(dl), sizeof_fmt(file_size), dl // (time.perf_counter() - start) / 100000))

    print(' Done!')
    return name


def slugify(string):
    simple_string = ''.join(e for e in string if e.isalnum() or e == ' ')

    return '-'.join(simple_string.lower().strip().split())


class BellettiniScraper():
    endpoints = {
        'homepage': 'https://homes.di.unimi.it/bellettini/sito/progII.html',
        'login': 'https://homes.di.unimi.it/bellettini/down.php'
    }

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.auth = (username, password)

        # Prepare session
        self.session = requests.session()
        self.session.proxies = proxies
        self.session.headers = headers
        self.session.verify = VERIFY_ENABLED

        # Test credentials
        r = self.session.get(self.endpoints['login'], auth=(self.username, self.password))
        r.raise_for_status()

        # Get homepage
        r = self.session.get(self.endpoints['homepage'])
        r.raise_for_status()

        # Extract tables
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        main_div = soup.find_all('div', {'class': 'row neuin py-2'})[2]
        theory_entries = main_div.find_all('table')[0].find('tbody').find_all('tr')
        laboratory_entries = main_div.find_all('table')[1].find('tbody').find_all('tr')

        self.data = {}

        theory = []
        for entry in theory_entries:
            td = entry.find_all('td')

            links = []
            for a in td[3].find_all('a'):
                links.append({
                    'title': a.text.strip(),
                    'slug': slugify(a.text.strip()),
                    'url': a.get('href'),
                })

            theory.append({
                'date': td[0].text.strip(),
                'title': td[1].text.strip(),
                'slug': slugify(td[1].text.strip()),
                'links': links
            })
        self.data['theory'] = theory
            
        laboratory = []
        for entry in laboratory_entries:
            td = entry.find_all('td')

            links = []
            for a in td[3].find_all('a'):
                links.append({
                    'title': a.text.strip(),
                    'slug': slugify(a.text.strip()),
                    'url': a.get('href'),
                })

            laboratory.append({
                'date': td[0].text.strip(),
                'title': td[1].text.strip(),
                'slug': slugify(td[1].text.strip()),
                'links': links
            })
        self.data['laboratory'] = laboratory

    def get_all_links(self):
        for entry in self.data.get('theory'):
            for link in entry.get('links'):
                yield link.get('url')

        for entry in self.data.get('laboratory'):
            for link in entry.get('links'):
                yield link.get('url')

    def get_youtube_links(self):
        for link in self.get_all_links():
            if 'youtu' in link:
                yield link

    def get_files_links(self):
        for link in self.get_all_links():
            if 'youtu' not in link:
                yield link


def main(args):
    scraper = BellettiniScraper(args.username, args.password)

    # Download all files if user didn't specify anything
    if args.videos == False and args.files == False:
        args.videos = True
        args.files = True

    # Download files
    if args.files:
        for link in scraper.get_files_links():
            print(link)
            download_file(scraper.session, link, auth=scraper.auth, name=link.split('down.php?FILENAME=')[1])

    # Download videos
    if args.videos:
        with youtube_dl.YoutubeDL({'format': 'best', 'retries': 5}) as ydl:
            for link in scraper.get_youtube_links():
                try:
                    ydl.download([link])
                except:
                    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('username', help='your unimi.it email')
    parser.add_argument('password', help='your unimi.it password')
    parser.add_argument('--videos', help='download YouTube videos', action='store_true')
    parser.add_argument('--files', help='download files', action='store_true')
    main(parser.parse_args())
