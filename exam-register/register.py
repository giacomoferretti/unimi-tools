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
import time
import pathlib
from urllib.parse import urljoin
import argparse

import requests
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


class Downloader():
    def __init__(self, download_folder=None):
        if download_folder:
            self.download_folder = download_folder
            pathlib.Path(self.download_folder).mkdir(parents=True, exist_ok=True)
        else:
            self.download_folder = ''

    # https://stackoverflow.com/questions/1094841/
    @staticmethod
    def sizeof_fmt(num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return '%3.1f%s%s' % (num, unit, suffix)
            num /= 1024.0
        return '%.1f%s%s' % (num, 'Yi', suffix)

    def download(self, url, session=None, name=None):
        # Extract name from url
        if name is None:
            name = url.split('/')[-1]

        output_file = os.path.join(self.download_folder, name)

        # Prepare session
        if session:
            session_ = session
        else:
            session_ = requests.session()

        with session_.get(url, stream=True) as r:
            r.raise_for_status()

            # Check if Transfer-Encoding is chunked
            if r.headers.get('Transfer-Encoding') and r.headers.get('Transfer-Encoding').lower() == 'chunked':
                chunk_size = None
            else:
                chunk_size = 4096

            # Estimate time
            file_size = r.headers.get('Content-Length')
            if file_size:
                file_size = int(file_size)

            downloaded = 0
            start_time = time.perf_counter()

            # Save file
            with open(name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)

            #         if file_size:
            #             downloaded += len(chunk)

            #             downloaded_formatted = self.sizeof_fmt(downloaded)
            #             file_size_formatted = self.sizeof_fmt(file_size)
            #             mbps = downloaded // (time.perf_counter() - start_time) / 100000
            #             percentage = downloaded / file_size * 100

            #             print('\r\x1b[K{} of {} [{:3.1f}%] at {:3.1f} Mbps'.format(downloaded_formatted, file_size_formatted, percentage, mbps), end='', flush=True)

            # print('\r\x1b[KDone!')


        return True


class ExamRegistration():
    endpoints = {
        'login': 'https://cas.unimi.it/login',
        'exams': 'http://studente.unimi.it/foIscrizioneEsami/',
        'exams_list': 'http://studente.unimi.it/foIscrizioneEsami/esamiPack/EsamiNonSostenutiDelCorsoPage',
    }

    def __init__(self, username, password):
        self.username = username
        self.password = password

        # Prepare session
        self.session = requests.session()
        self.session.proxies = proxies
        self.session.headers = headers
        self.session.verify = VERIFY_ENABLED

        # Login
        self.login(self.endpoints['exams'])

        # Set language to Italian (some courses have ??? as their name in English, UNIMI pls fix ur shit)
        r = self.session.get(self.endpoints['exams'] + 'checkLogin.asp?1-1.ILinkListener-itLink')
        r.raise_for_status()

    def login(self, service):
        # Get execution flow
        execution_flow = self.get_execution_flow()

        # Prepare login data
        login_data = {
            'username': self.username,
            'password': self.password,
            'selTipoUtente': 'S',
            'hCancelLoginLink': 'http://www.unimi.it',
            'hForgotPasswordLink': 'https://auth.unimi.it/password/',
            'lt': execution_flow,
            'execution': execution_flow,
            'service': service,
            '_eventId': 'submit',
            '_responsive': 'responsive'
        }

        # Do login
        r = self.session.post(self.endpoints['login'], data=login_data, allow_redirects=False)
        if r.status_code != 302:
            raise ValueError('Wrong email or password.')

        # Check correct login
        r = self.session.get(self.endpoints['exams'])
        r.raise_for_status()
        
    def get_execution_flow(self):
        r = self.session.get(self.endpoints['login'])
        r.raise_for_status()

        soup = BeautifulSoup(r.content, features=SOUP_PARSER)
        value = soup.find('input', {'id': 'hExecution', 'name': 'execution'})

        if value == None:
            raise ValueError('Cannot find \'execution\' value.')

        self.session.cookies.clear()

        return value['value']

    def get_exams(self):
        exams = []

        queue = [self.endpoints['exams_list']]

        while len(queue) > 0:
            current = queue.pop()

            r = self.session.get(current)
            r.raise_for_status()

            soup = BeautifulSoup(r.content, features=SOUP_PARSER)

            entries = soup.find('table', {'class': 'smart-table'}).find('tbody').find_all('tr')
            for entry in entries:
                code = entry.find_all('td')[0].text.strip()
                name = entry.find_all('td')[1].text.strip()
                credits = entry.find_all('td')[2].text.strip()
                link = urljoin(current, entry.find_all('td')[3].find('a').get('href'))

                exams.append({
                    'code': code,
                    'name': name,
                    'credits': int(credits),
                    'link': link
                })


            next_page = soup.find('ul', {'class': 'pagination'}).find('a', {'title': 'Go to next page'})
            if next_page:
                queue.append(urljoin(current, next_page.get('href')))


        return exams

    def get_exams_dates(self, exam):
        current = exam['link']

        exam_sessions = []

        r = self.session.get(current)
        r.raise_for_status()

        soup = BeautifulSoup(r.content, features=SOUP_PARSER)

        entries = soup.find('ul', {'role': 'list'}).find_all('li')
        for index, entry in enumerate(entries):
            date = entry.find('div', {'class': 'panel-heading'}).find_all('span')[-1].text.strip()

            body = entry.find('div', {'class': 'panel-body'})

            # Check if disabled
            active = body.find('span', {'role': 'link'}) is None

            # Check if need to compile
            need_compilation = 'necessario compilare il questionario' in body.text
            can_register = active and 'Iscriviti' in body.text
            action = None

            # States
            # compilation and active = COMPILARE QUESTIONARIO
            # active and can_register = CAN REGISTER
            # can_register = ALREADY REGISTERED
            # TODO: Check if active based on date

            if need_compilation or can_register:
                action = urljoin(current, body.find('a', {'role': 'link'}).get('href'))

            exam_sessions.append({
                'date': date,
                'active': active,
                'compile': need_compilation,
                'register': can_register,
                'action': action
            })

            # t = self.session.get(urljoin(r.url, '../esame/selezioneAppello?{}-1.IBehaviorListener.0-form-appelli-{}-detailLink'.format(r.url.split('?')[1], index)), headers=merge_two_dicts(self.session.headers, {
            #     'Wicket-Ajax-BaseURL': '',
            #     'Wicket-Ajax': 'true'
            # }))
            # print(t.content)

        return exam_sessions

    def register_exam_session(self, exam):
        if not exam.get('action'):
            raise ValueError('You cannot register to this session.')

        r = self.session.get(exam.get('action'))
        r.raise_for_status()

        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find('form')
        hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))

        users_registered = int(re.search(r'Al momento risultano iscritti ([0-9]+) studenti', form.find('tr', {'class': 'wicketExtensionsWizardViewRow'}).text).group(1))

        r = self.session.post(form_action, data={hidden_id: '', 'wizard:form:buttons:finish': 'Finish'})
        r.raise_for_status()

        soup = BeautifulSoup(r.content, SOUP_PARSER)
        qr_code = urljoin(r.url, soup.find('form').find('div', {'class': 'row'}).find('img').get('src'))
        pdf = urljoin(r.url, soup.find('form').find('a').get('href'))

        return {
            'qr': qr_code,
            'pdf': pdf
        }

    def complete_survey(self, exam):
        if not exam.get('action'):
            raise ValueError('You cannot register to this session.')

        # Home
        r = self.session.get(exam.get('action'))
        r.raise_for_status()
        
        # Next button
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={hidden_id: '', 'avantiButton': 'next'})
        r.raise_for_status()

        # Next button
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={hidden_id: '', 'avantiButton': 'next'})
        r.raise_for_status()

        # Skip button
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        # Select course
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'view:form:content:form:insegnamentiTable:body:rows:1:cells:4:cell:button': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        # Frequency
        # 0 Mai
        # 1 Piu' di due anni fa
        # 2 Due anni fa
        # 3 Lo scorso anno accademico
        # 4 In quest'anno accademico
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'view:form:content:form:frequentazione': 4, 'buttons:next': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        # Frequency percentage
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'view:form:content:form:frequenzaSlider:model:input': 50, 'view:form:content:form:frequenzaText': 50, 'buttons:next': 'BRUH'})
        r.raise_for_status()

        # Next button
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'buttons:next': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        # Next button
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'buttons:next': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()


        # First section (Motivo della non frequenza)
        # 1. Indicare il motivo principale della non frequenza o della frequenza ridotta alle lezioni: (*)
        # "1" "Frequenza alle lezioni dell'insegnamento in un altro anno accademico"
        # "2" "Lavoro"
        # "3" "Frequenza lezioni di altri insegnamenti"
        # "4" "Frequenza poco utile ai fini della preparazione dell'esame"
        # "5" "La logistica delle aule non consente la frequenza agli studenti interessati"
        # "6" "Altro"
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'jsonField': '{"D1":"6"}', 'avantiButton': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        # Second section (Insegnamento)
        # 1. Le conoscenze preliminari possedute sono risultate sufficienti per la comprensione degli argomenti previsti nel programma d'esame? (*)
        # {"D2":"2","D3":"2","D5a":"2","D5b":"1","D6":"2","D7":"2","D8":"2","D9":"2"}
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'jsonField': '{"D2":"2","D3":"2","D5a":"2","D5b":"1","D6":"2","D7":"2","D8":"2","D9":"2"}', 'avantiButton': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        # Third section (Docente/i)
        # 1. Il docente è reperibile per chiarimenti e spiegazioni? (*)
        # D10
        # "2" "Decisamente NO"
        # "5" "Più NO che Sì"
        # "7" "Più Sì che No"
        # "10" "Decisamente Sì"
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'jsonField': '{"D10":"2"}', 'avantiButton': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        # Fourth section (Suggerimenti)
        # 1. Indichi eventuali suggerimenti per migliorare la qualità dell'insegnamento che sta valutando
        soup = BeautifulSoup(r.content, SOUP_PARSER)
        form = soup.find_all('form')[1]
        #hidden_id = form.find('input', {'type': 'hidden'}).get('name')
        form_action = urljoin(r.url, form.get('action'))
        r = self.session.post(form_action, data={'jsonField': '{"D11":["8","6"]}', 'fineQuestionarioButton': 'BRUH'})# data={hidden_id: '', 'skipButton': 'next'})
        r.raise_for_status()

        return r


def default_format(entry):
    return entry


def choose_from_list(message, list_, format_=default_format):
    max_value = len(list_)

    for i, entry in enumerate(list_):
        print('[{:02}] {}'.format(i + 1, format_(entry)))

    choice = None
    valid = False

    while not valid:
        choice = input('{} [1-{}]: '.format(message, max_value))
        valid = choice.isnumeric() and int(choice) < max_value and int(choice) > 0

        if not valid:
            print('Invalid input. Please retry.')

    choice = int(choice) - 1

    return list_[choice]


def slugify(string):
    simple_string = ''.join(e for e in string if e.isalnum() or e == ' ')

    return '-'.join(simple_string.lower().strip().split())


def merge_two_dicts(x, y):
    z = x.copy()
    z.update(y)
    return z


def main(args):
    downloader = Downloader('receipts')
    unimi = ExamRegistration(args.username, args.password)

    exams = unimi.get_exams()

    exam = choose_from_list('Choose an exam', list_=exams, format_=lambda e: e.get('name'))

    exam_sessions = unimi.get_exams_dates(exam)

    exam_session = choose_from_list('Choose an exam session', list_=exam_sessions, format_=lambda e: '{} [{}]'.format(e.get('date'), e.get('action')))

    if exam_session['active'] and exam_session['register']:
        result = unimi.register_exam_session(exam_session)
    elif exam_session['active'] and exam_session['compile']:
        # Need to compile survey
        result = unimi.complete_survey(exam_session)
        exam_sessions = unimi.get_exams_dates(exam)
        exam_session = choose_from_list('Choose an exam session', list_=exam_sessions, format_=lambda e: '{} [{}]'.format(e.get('date'), e.get('action')))
        result = unimi.register_exam_session(exam_session)
    else:
        print('You cannot register to this exam session. Exiting...')
        sys.exit(1)

    # Download PDF receipt
    if args.pdf:
        downloader.download(result['pdf'], session=unimi.session, name='{}{}_{}.pdf'.format(exam['code'], slugify(exam['name']), slugify(exam_session['date'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('username', help='your @studenti.unimi.it email')
    parser.add_argument('password', help='your @studenti.unimi.it password')
    parser.add_argument('-p', '--pdf', help='save pdf receipt', action='store_true')
    # TODO: Add --all logic
    # parser.add_argument('--all', help='register on all available exam sessions', action='store_true')
    main(parser.parse_args())
