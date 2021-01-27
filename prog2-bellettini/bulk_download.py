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
SUPPRESS_WARNINGS = True
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

def my_hook(d):
    print(d)
    if d['status'] == 'finished':
        print('Done downloading, now converting ...')

ydl_opts = {
    'format': 'best',
    # 'postprocessors': [{
    #     'key': 'FFmpegExtractAudio',
    #     'preferredcodec': 'mp3',
    #     'preferredquality': '192',
    # }],
    # 'logger': MyLogger(),
    # 'outtmpl': '%(id)s.%(ext)s',
    # 'progress_hooks': [my_hook],
}


def slugify(string):
    simple_string = ''.join(e for e in string if e.isalnum() or e == ' ')

    return '-'.join(simple_string.lower().strip().split())


def main(args):
    session = requests.session()
    session.proxies = proxies
    session.headers = headers
    session.verify = VERIFY_ENABLED

    r = session.get('https://homes.di.unimi.it/bellettini/sito/progII.html')
    if r.status_code != 200:
        print('Wrong response.', file=sys.stderr)
        os.exit(1)

    soup = BeautifulSoup(r.content, SOUP_PARSER)

    # Extract tables
    main_div = soup.find_all('div', {'class': 'row neuin py-2'})[2]
    theory_entries = main_div.find_all('table')[0].find('tbody').find_all('tr')
    laboratory_entries = main_div.find_all('table')[1].find('tbody').find_all('tr')

    output = {}

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
    output['theory'] = theory
        
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
    output['laboratory'] = laboratory

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        for x in output.get('theory'):
            for y in x.get('links'):
                if 'youtube' in y.get('url'):
                    ydl.download([y.get('url')])

        for x in output.get('laboratory'):
            for y in x.get('links'):
                if 'youtube' in y.get('url'):
                    ydl.download([y.get('url')])

    # __import__('IPython').embed()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    main(parser.parse_args())
