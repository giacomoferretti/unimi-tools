#!/usr/bin/env python3

# Copyright 2020 Giacomo Ferretti
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

import re
import json
import requests

BASE_URL = 'http://unimia.unimi.it/imageserver'

HREF_REGEX = re.compile(r'<a\s+(?:[^>]*?\s+)?href=(["\'])(.*?)\1')

headers = {
    'User-Agent': 'Mozilla/5.0'
}

proxies = {
    'http': 'http://localhost:8080',
    'https': 'http://localhost:8080'
}

verify = False


def find_all_links(string):
    return [x[1] for x in HREF_REGEX.findall(string)]


if __name__ == '__main__':
    dump = []
    targets = [BASE_URL]
    already_scanned = []

    total_scanned = 0
    total = 1

    while len(targets) != 0:
        current_target = targets.pop()

        print(f'Scanning: "{current_target}"... {total_scanned}/{total}')

        # Get index
        r = requests.get(current_target, headers=headers, proxies=proxies, verify=verify)
        if r.status_code != 200:
            print('ERROR: HTTP response is not 200.')
            exit(1)

        # Increment
        total_scanned += 1

        # Extract all links
        for link in find_all_links(r.text):

            # Skip already scanned
            if link == '/' or ('http://unimia.unimi.it' + link) in already_scanned:
                continue

            # Extract filetype
            link_type = 'file'
            if link[-1] == '/':
                link_type = 'directory'
                total += 1

            dump.append({'type': link_type, 'link': r.url + link})

            if link_type != 'file':
                targets.append(r.url + link)
            else:
                #print(f' -> Found {link}')
                pass


        already_scanned.append(r.url)

    with open('server_dump.json', 'w') as f:
        f.write(json.dumps(dump, separators=(',', ':')))