#!/usr/bin/python3
"""Racing Post horses info scraper."""
import csv
import json
import logging
import os
import re
import traceback
from datetime import datetime
from time import sleep

import requests
from bson.json_util import dumps
from lxml import html
from pymongo import MongoClient

import pandas as pd
from openpyxl import load_workbook

client = MongoClient()
db = client.betfair

logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s',
                    level=logging.INFO, datefmt='%Y/%m/%dT%H:%M:%S')

# Setting access variables
session = requests.Session()
headers =\
    {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ' +
     '(KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36'}
base = 'https://www.racingpost.com'

# Writing rows in the end to avoid any connection problems, etc.
rows = []


def excelize(dataframe, columns):
    """Save dataframe as formatted Excel file."""
    dataframe = dataframe[columns]
    path = os.path.join('data', '{}'.format(
        datetime.now().strftime("%Y-%m-%d")))
    book = load_workbook(os.path.join('assets', 'racingpost_m.xlsx'))
    writer = pd.ExcelWriter(os.path.join(
        path, 'racingpost_m.xlsx'), engine='openpyxl')
    writer.book = book
    writer.sheets = dict((ws.title, ws) for ws in book.worksheets)
    dataframe.to_excel(writer, "Main", startrow=1,
                       startcol=0, index=False, header=False)
    writer.save()


def totalizer(numbers):
    """Sum all percentages."""
    total = 0
    for n in numbers:
        if n == '-' or n is None:
            n = '0%'
        try:
            total += float(str(n).replace('%', ''))
        except:
            logging.warning('\t\tPossible data loss!')

    return int(round(total))


def grab_events():
    """Get a full list of today's events, lad."""
    code = requests.get(
        'https://www.racingpost.com/racecards/time-order', headers=headers)

    # Checking if the page is accessible
    if code.status_code in [502, 503, 404]:
        logging.critical('Page is unaccessible! Try again later.')
        return

    # Scraping links from the main page
    tree = html.fromstring(code.text)
    links = tree.xpath('//a[contains(@class, "RC-meetingItem__link")]/@href')
    years = [re.findall('[Cl\d\s]?\((\d).*?\)\s+\d+.?[fm]',
                        i.strip().replace('\n', ''))[0] for i in tree.xpath(
        '//a[contains(@class, "RC-meetingItem__link")]//' +
        'span[@class="RC-meetingItem__goingData"]/text()')]
    return list(zip(links, years))


def process_horse(race_type, advanced, final, tree, num, horse, data):
    """Fill all the advanced horse data columns."""
    if tree.xpath(
        '//span[@data-test-selector="RC-cardPage-runnerNumber-no"]/text()'
    )[num].strip() == 'NR':
        logging.warning('\tA horse is not running: {}!'.format(horse.xpath(
            '//a[@data-test-selector="RC-cardPage-runnerName"]/text()'
        )[num].strip()))
        return

    if data['Course'].endswith('(IRE)') or tree.xpath(
        '//title/text()')[0].split('|'
                                   )[0].strip().endswith('(IRE)'):
        country = 'IRE'
    else:
        country = 'GB'

    data['Age'] = horse.xpath(
        '//span[@class="RC-runnerAge"]/text()')[num].strip()
    data['Horse'] = horse.xpath(
        '//a[@data-test-selector="RC-cardPage-runnerName"]/text()'
    )[num].strip()
    logging.info('\tProcessing {}'.format(data['Horse']))
    try:
        trainer_name = tree.xpath(
            '//a[contains(text(), "{}")]'.format(data['Horse']) +
            '/parent::div/parent::div/parent::div' +
            '//a[@data-test-selector="RC-cardPage-runnerTrainer-name"]' +
            '/text()')[0].strip()
        data['Trainer'] = '<a href={}>{}</a>'.format(base + tree.xpath(
            '//a[contains(text(), "{}")]'.format(data['Horse']) +
            '/parent::div/parent::div/parent::div' +
            '//a[@data-test-selector="RC-cardPage-runnerTrainer-name"]' +
            '/@href')[0].strip(), tree.xpath(
            '//a[contains(text(), "{}")]'.format(data['Horse']) +
            '/parent::div/parent::div/parent::div' +
            '//a[@data-test-selector="RC-cardPage-runnerTrainer-name"]' +
            '/text()')[0].strip().title())
    except:
        trainer_name = 'NOBODY'
        data['Trainer'] = 'NOBODY'
    try:
        jockey_name = tree.xpath(
            '//a[contains(text(), "{}")]'.format(data['Horse']) +
            '/parent::div/parent::div/parent::div' +
            '//a[@data-test-selector="RC-cardPage-runnerJockey-name"]' +
            '/text()')[0].strip()
        data['Jockey'] = '<a href={}>{}</a>'.format(base + tree.xpath(
            '//a[contains(text(), "{}")]'.format(data['Horse']) +
            '/parent::div/parent::div/parent::div' +
            '//a[@data-test-selector="RC-cardPage-runnerJockey-name"]' +
            '/@href')[0].strip(), tree.xpath(
            '//a[contains(text(), "{}")]'.format(data['Horse']) +
            '/parent::div/parent::div/parent::div' +
            '//a[@data-test-selector="RC-cardPage-runnerJockey-name"]' +
            '/text()')[0].strip().title())
    except:
        jockey_name = 'NOBODY'
        data['Jockey'] = 'NOBODY'
    data['Form'] = horse.xpath(
        'string((//span[@class="RC-runnerInfo__form"])[{}])'.format(num + 1)
    ).strip()
    if not data['Form']:
        data['Form'] = '-'

    # Using regex to get the forecast from text string
    try:
        data['Forc'] =\
            tree.xpath('//a[@data-test-selector="RC-bettingForecast_link" ' +
                       'and text()="{}"]/parent::span//text()'.format(
                           data['Horse']))[0].strip()
    except:
        data['Forc'] = 'N/A'

    # Filling the "Horse" advanced columns
    horse_data = [i.strip() for i in advanced.xpath(
        '//a[contains(text(), ' +
        '"{}")][1]/parent::td/parent::tr//td//text()'.format(
            data['Horse'])) if i.strip()]
    data['Go'] = re.sub('\s+', ' ', horse_data[1])
    data['Go %'] = re.sub('\s+', ' ', horse_data[2]).replace('%', '')
    data['Dist'] = re.sub('\s+', ' ', horse_data[3])
    data['Dist %'] = re.sub('\s+', ' ', horse_data[4]).replace('%', '')
    data['Cse'] = re.sub('\s+', ' ', horse_data[5])
    data['Cse %'] = re.sub('\s+', ' ', horse_data[6]).replace('%', '')

    # Filling the "Trainer" advanced columns
    trainer_data = [i.strip() for i in advanced.xpath(
        '//a[contains(text(), ' +
        '"{}")][1]/parent::td/parent::tr//td//text()'.format(
            trainer_name)) if i.strip()]
    try:
        data['T 14dys'] = re.sub('\s+', ' ', trainer_data[1])
        data['T D W %'] = re.sub('\s+', ' ', trainer_data[2]).replace('%', '')
        data['T D £1 + -'] = re.sub('\s+', ' ', trainer_data[3])
        data['T O/A Seas'] = re.sub('\s+', ' ', trainer_data[4])
        data['T S W %'] = re.sub('\s+', ' ', trainer_data[5]).replace('%', '')
        data['T S £1 + -'] = re.sub('\s+', ' ', trainer_data[6])
        data['T O/A Track'] = re.sub('\s+', ' ', trainer_data[4])
        data['T T W %'] = re.sub('\s+', ' ', trainer_data[5]).replace('%', '')
        data['T T £1 + -'] = re.sub('\s+', ' ', trainer_data[6])
    except:
        logging.warning('\t\tMissing trainer data!')
        data['T 14dys'] = '-'
        data['T D W %'] = '-'
        data['T D £1 + -'] = '-'
        data['T O/A Seas'] = '-'
        data['T S W %'] = '-'
        data['T S £1 + -'] = '-'
        data['T O/A Track'] = '-'
        data['T T W %'] = '-'
        data['T T £1 + -'] = '-'

    try:
        for t in range(2):
            try:
                advanced_trainer_code = requests.get(base + tree.xpath(
                    '//a[contains(text(), "{}")]'.format(data['Horse']) +
                    '/parent::div/parent::div/parent::div' +
                    '//a[@data-test-selector=' +
                    '"RC-cardPage-runnerTrainer-name"]/@href')[0],
                    headers=headers)
                advanced_trainer_data = json.loads(re.findall(
                    'window.PRELOADED_STATE = ({.*});',
                    advanced_trainer_code.text)[0])
                break
            except:
                logging.warning('Website blocked request, sleep...')
                sleep(30)

        data['RTF %'] =\
            str(int(
                round(advanced_trainer_data['profile']['runningToForm'], 0)))
        if data['RTF %'] is not None:
            data['RTF %'] = data['RTF %'].replace('%', '')
        if race_type[0] == 'Jumps':
            data['T Won'] =\
                advanced_trainer_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5']['data']['recordByRaceType'
                                                         ][race_type[1]
                                                           ]['place1stNumber']
            data['Ran'] =\
                advanced_trainer_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5']['data']['recordByRaceType'
                                                         ][race_type[1]
                                                           ]['racesNumber']
            data['T W %'] =\
                str(advanced_trainer_data['recordsByType'][
                    'recByType{}{}'.format(
                        country, race_type[0])]['5']['data']['recordByRaceType'
                                                             ][race_type[1]
                                                               ]['percent']
                    )
            if data['T W %'] is not None and data['T W %'].strip() != 'None':
                data['T W %'] = data['T W %'].replace('%', '')

            data['Plcd'] =\
                advanced_trainer_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5']['data']['recordByRaceType'
                                                         ][race_type[1]
                                                           ]['placed']
        else:
            data['T Won'] =\
                advanced_trainer_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ]['{}YO{}'.format(race_type[2][0],
                                              race_type[2][1]) + race_type[1
                                                                           ]
                              ]['place1stNumber']
            data['Ran'] =\
                advanced_trainer_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ]['{}YO{}'.format(race_type[2][0],
                                              race_type[2][1]) + race_type[1
                                                                           ]
                              ]['racesNumber']
            data['T W %'] =\
                str(advanced_trainer_data['recordsByType'][
                    'recByType{}{}'.format(
                        country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ]['{}YO{}'.format(race_type[2][0],
                                              race_type[2][1]) + race_type[1
                                                                           ]
                              ]['percent'])
            if data['T W %'] is not None and data['T W %'].strip() != 'None':
                data['T W %'] = data['T W %'].replace('%', '')

            data['Plcd'] =\
                advanced_trainer_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ]['{}YO{}'.format(race_type[2][0],
                                              race_type[2][1]) + race_type[1
                                                                           ]
                              ]['placed']
    except:
        logging.warning('\t\tAdvanced trainer data is not available')
        data['T Won'] = '-'
        data['Ran'] = '-'
        data['T W %'] = '-'
        data['Plcd'] = '-'
        data['RTF %'] = '-'
    if race_type[0] == 'Jumps':
        if race_type[1] != 'NHF':
            data['T 5yr O/A'] = race_type[1].title()
        else:
            data['T 5yr O/A'] = race_type[1]
    elif race_type[0] == 'Flat':
        if race_type[2][1]:
            data['T 5yr O/A'] = '{}yo+{}'.format(race_type[2][0], race_type[1])
        else:
            data['T 5yr O/A'] = '{}yo{}'.format(race_type[2][0], race_type[1])

    # Filling the trainer "final" columns
    final_trainer_data = [i.strip() for i in final.xpath(
        '//a[contains(text(), ' +
        '"{}")][1]/parent::td/parent::tr//td//text()'.format(
            trainer_name)) if i.strip()]
    try:
        if race_type[0] == 'Jumps':
            if race_type[1] == 'HURDLE':
                data['T F Won'] = re.sub('\s+', ' ', final_trainer_data[4])
                data['T F W %'] = re.sub(
                    '\s+', ' ', final_trainer_data[5]).replace('%', '')
                data['T F £1 + -'] = re.sub('\s+', ' ', final_trainer_data[6])
            elif race_type[1] == 'CHASE':
                data['T F Won'] = re.sub('\s+', ' ', final_trainer_data[7])
                data['T F W %'] = re.sub(
                    '\s+', ' ', final_trainer_data[8]).replace('%', '')
                data['T F £1 + -'] = re.sub('\s+', ' ', final_trainer_data[9])
            elif race_type[1] == 'NHF':
                data['T F Won'] = re.sub('\s+', ' ', final_trainer_data[10])
                data['T F W %'] = re.sub(
                    '\s+', ' ', final_trainer_data[11]).replace('%', '')
                data['T F £1 + -'] = re.sub('\s+', ' ', final_trainer_data[12])
        elif race_type[0] == 'Flat':
            data['T F Won'] = re.sub('\s+', ' ', final_trainer_data[10])
            data['T F W %'] = re.sub(
                '\s+', ' ', final_trainer_data[11]).replace('%', '')
            data['T F £1 + -'] = re.sub('\s+', ' ', final_trainer_data[12])
    except:
        data['T F Won'] = '-'
        data['T F W %'] = '-'
        data['T F £1 + -'] = '-'

    # Filling the "Jockey" advanced columns
    jockey_data = [i.strip() for i in advanced.xpath(
        '//a[contains(text(), ' +
        '"{}")][1]/parent::td/parent::tr//td//text()'.format(
            jockey_name)) if i.strip()]
    try:
        data['J 14dys'] = re.sub('\s+', ' ', jockey_data[1])
        data['J D W %'] = re.sub('\s+', ' ', jockey_data[2]).replace('%', '')
        data['J D £1 + -'] = re.sub('\s+', ' ', jockey_data[3])
        data['J O/A Seas'] = re.sub('\s+', ' ', jockey_data[4])
        data['J S W %'] = re.sub('\s+', ' ', jockey_data[5]).replace('%', '')
        data['J S £1 + -'] = re.sub('\s+', ' ', jockey_data[6])
        data['J O/A Track'] = re.sub('\s+', ' ', jockey_data[4])
        data['J T W %'] = re.sub('\s+', ' ', jockey_data[5]).replace('%', '')
        data['J T £1 + -'] = re.sub('\s+', ' ', jockey_data[6])
    except:
        logging.warning('\t\tMissing jockey data!')
        data['J 14dys'] = '-'
        data['J D W %'] = '-'
        data['J D £1 + -'] = '-'
        data['J O/A Seas'] = '-'
        data['J S W %'] = '-'
        data['J S £1 + -'] = '-'
        data['J O/A Track'] = '-'
        data['J T W %'] = '-'
        data['J T £1 + -'] = '-'

    try:
        for t in range(2):
            try:
                advanced_jockey_code = requests.get(base + tree.xpath(
                    '//a[contains(text(), "{}")]'.format(data['Horse']) +
                    '/parent::div/parent::div/parent::div' +
                    '//a[@data-test-selector=' +
                    '"RC-cardPage-runnerJockey-name"]/@href')[0],
                    headers=headers)
                advanced_jockey_data = json.loads(re.findall(
                    'window.PRELOADED_STATE = ({.*});',
                    advanced_jockey_code.text)[0])
                break
            except:
                logging.warning('Website blocked request, sleep...')
                sleep(30)

        if race_type[0] == 'Jumps':
            data['J Won'] =\
                advanced_jockey_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ][race_type[1]
                              ]['place1stNumber']
            data['Rode'] =\
                advanced_jockey_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5']['data']['recordByRaceType'
                                                         ][race_type[1]
                                                           ]['racesNumber']
            data['J W %'] =\
                str(advanced_jockey_data['recordsByType'][
                    'recByType{}{}'.format(
                        country, race_type[0])]['5']['data']['recordByRaceType'
                                                             ][race_type[1]
                                                               ]['winPercent']
                    )
            if data['J W %'] is not None and data['J W %'] != 'None':
                data['J W %'] = data['J W %'].replace('%', '')

        else:
            data['J Won'] =\
                advanced_jockey_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ]['{}YO{}'.format(race_type[2][0],
                                              race_type[2][1]) + race_type[1
                                                                           ]
                              ]['place1stNumber']
            data['Rode'] =\
                advanced_jockey_data['recordsByType']['recByType{}{}'.format(
                    country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ]['{}YO{}'.format(race_type[2][0],
                                              race_type[2][1]) + race_type[1
                                                                           ]
                              ]['racesNumber']
            data['J W %'] =\
                str(advanced_jockey_data['recordsByType'][
                    'recByType{}{}'.format(
                        country, race_type[0])]['5'][
                    'data']['recordByRaceType'
                            ]['{}YO{}'.format(race_type[2][0],
                                              race_type[2][1]) + race_type[1
                                                                           ]
                              ]['winPercent'])
            if data['J W %'] is not None and data['J W %'] != 'None':
                data['J W %'] = data['J W %'].replace('%', '')

    except:
        logging.warning('\t\tAdvanced jockey data is not available!')
        data['J Won'] = '-'
        data['Rode'] = '-'
        data['J W %'] = '-'

    if race_type[0] == 'Jumps':
        if race_type[1] != 'NHF':
            data['J 5yr O/A'] = race_type[1].title()
        else:
            data['J 5yr O/A'] = race_type[1]
    elif race_type[0] == 'Flat':
        if race_type[2][1]:
            data['J 5yr O/A'] = '{}yo+{}'.format(race_type[2][0], race_type[1])
        else:
            data['J 5yr O/A'] = '{}yo{}'.format(race_type[2][0], race_type[1])

    # Filling the jockey "final" columns
    final_jockey_data = [i.strip() for i in final.xpath(
        '//a[contains(text(), ' +
        '"{}")][1]/parent::td/parent::tr//td//text()'.format(
            jockey_name)) if i.strip()]
    try:
        if race_type[0] == 'Jumps':
            if race_type[1] == 'HURDLE':
                data['J F Won'] = re.sub('\s+', ' ', final_jockey_data[4])
                data['J F W %'] = re.sub(
                    '\s+', ' ', final_jockey_data[5]).replace('%', '')
                data['J F £1 + -'] = re.sub('\s+', ' ', final_jockey_data[6])
            elif race_type[1] == 'CHASE':
                data['J F Won'] = re.sub('\s+', ' ', final_jockey_data[7])
                data['J F W %'] = re.sub(
                    '\s+', ' ', final_jockey_data[8]).replace('%', '')
                data['J F £1 + -'] = re.sub('\s+', ' ', final_jockey_data[9])
            elif race_type[1] == 'NHF':
                data['J F Won'] = re.sub('\s+', ' ', final_jockey_data[10])
                data['J F W %'] = re.sub(
                    '\s+', ' ', final_jockey_data[11]).replace('%', '')
                data['J F £1 + -'] = re.sub('\s+', ' ', final_jockey_data[12])
        elif race_type[0] == 'Flat':
            data['J F Won'] = re.sub('\s+', ' ', final_jockey_data[10])
            data['J F W %'] = re.sub(
                '\s+', ' ', final_jockey_data[11]).replace('%', '')
            data['J F £1 + -'] = re.sub('\s+', ' ', final_jockey_data[12])
    except:
        data['J F Won'] = '-'
        data['J F W %'] = '-'
        data['J F £1 + -'] = '-'

    data['Mean'] = totalizer([data['Go %'], data['Dist %'],
                              data['Cse %'], data['T D W %'], data['T S W %'],
                              data['RTF %'], data['T W %'], data['T T W %'],
                              data['T F W %'], data['J D W %'],
                              data['J S W %'],
                              data['J W %'], data['J T W %'], data['J F W %']])
    data['Horse'] = '<a href={}>{}</a>'.format(base + tree.xpath(
        '//a[contains(text(), "{}")]'.format(data['Horse']) +
        '/parent::div/parent::div/parent::div' +
        '//a[@data-test-selector="RC-cardPage-runnerName"]' +
        '/@href')[0].strip(), tree.xpath(
        '//a[contains(text(), "{}")]'.format(data['Horse']) +
        '/parent::div/parent::div/parent::div' +
        '//a[@data-test-selector="RC-cardPage-runnerName"]' +
        '/text()')[0].strip().title())
    data['Update'] = datetime.now().strftime('%Y-%m-%d')
    rows.append(data.copy())


def process_event(event, year):
    """Process exact event."""
    data = {}

    # Main code part
    code = requests.get(event, headers=headers)
    tree = html.fromstring(code.text)
    data['Course'] = tree.xpath(
        '//a[@data-test-selector="RC-courseHeader__name"]/text()'
    )[0].strip()
    if data['Course'].endswith(')') and not\
            data['Course'].endswith(('(IRE)', '(AW)')):
        return
    elif tree.xpath('//title/text()'
                    )[0].split('|')[0].strip().endswith(')') and not\
            tree.xpath('//title/text()'
                       )[0].split('|')[0].strip().endswith(('(IRE)', '(AW)')):
        return
    # Advanced code part
    advanced_code = requests.get(
        'https://www.racingpost.com/racecards/data/accordion/{}'.format(
            event.split('/')[-1]), headers=headers)
    advanced_tree = html.fromstring(advanced_code.text)

    # Final code part
    final_code = requests.get(event + '/stats', headers=headers)
    final_tree = html.fromstring(final_code.text)

    # Checking if the page is accessible
    if code.status_code in [502, 503, 404]:
        logging.critical('Page is unaccessible! Try again later.')
        return

    try:
        data['Time'] = tree.xpath(
            '//section[@data-page-type="free-card"]/@data-diffusion-racetime'
        )[0]
        # data['Surf'] = ''
        data['Distance'] = tree.xpath(
            '//strong[@class="RC-cardHeader__distance"]/text()')[0].strip()
    except IndexError:
        logging.warning('\tEvent is not available!')
        return

    logging.info('[{}]'.format(data['Time']))

    # Estimating the race type
    try:
        race_descr = tree.xpath(
            '//span[@data-test-selector="RC-header__raceInstanceTitle"]/text()'
        )[0].lower()
        if re.findall('hurdle', race_descr):
            race_type = ['Jumps', 'HURDLE']
        elif re.findall('chase', race_descr):
            race_type = ['Jumps', 'CHASE']
        elif re.findall('national hunt', race_descr):
            race_type = ['Jumps', 'NHF']
        else:
            raise IndexError
    except:
        race_type = ['Flat']
        if data['Course'].endswith('(AW)') or tree.xpath(
                '//title/text()')[0].split('|')[0].strip().endswith('(AW)'):
            race_type.append(' AW')
            if year == '4':
                race_type.append([year, '+'])
            else:
                race_type.append([year, ''])
        else:
            race_type.append(' TURF')
            if year == '4':
                race_type.append([year, '+'])
            else:
                race_type.append([year, ''])
    if tree.xpath('//title/text()'
                  )[0].split('|'
                             )[0].strip().endswith('(IRE)'
                                                   ) and race_type[0
                                                                   ] == 'Flat':
        race_type = ['Jumps', 'NHF']

    # Processing advanced columns for each horse
    for num, horse in enumerate(tree.xpath(
            '//div[@class="RC-runnerCardWrapper"]')):
        process_horse(race_type, advanced_tree,
                      final_tree, tree, num, horse, data)


def write_data():
    """Write data into CSV. Nothing else."""
    path = os.path.join('data', '{}'.format(
        datetime.now().strftime("%Y-%m-%d")))
    if not os.path.exists(path):
        os.makedirs(path)
    with open(os.path.join(path, 'racingpost.csv'), 'w', newline=''
              ) as csvfile:
        fieldnames = ['Time',
                      'Course',
                      'Age',
                      'Distance',
                      'Form',
                      'Forc',
                      'Horse',
                      'Go',
                      'Go %',
                      'Dist',
                      'Dist %',
                      'Cse',
                      'Cse %',
                      'Trainer',
                      'T 14dys',
                      'T D W %',
                      'T D £1 + -',
                      'T O/A Seas',
                      'T S W %',
                      'T S £1 + -',
                      'RTF %',
                      'T 5yr O/A',
                      'T Won',
                      'Ran',
                      'T W %',
                      'Plcd',
                      'T O/A Track',
                      'T T W %',
                      'T T £1 + -',
                      'T F Won',
                      'T F W %',
                      'T F £1 + -',
                      'Jockey',
                      'J 14dys',
                      'J D W %',
                      'J D £1 + -',
                      'J O/A Seas',
                      'J S W %',
                      'J S £1 + -',
                      'J 5yr O/A',
                      'J Won',
                      'Rode',
                      'J W %',
                      'J O/A Track',
                      'J T W %',
                      'J T £1 + -',
                      'J F Won',
                      'J F W %',
                      'J F £1 + -',
                      'Mean']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        sleep(3)
        excelize(pd.DataFrame(rows), fieldnames)


def racingpost():
    """Use this function to wrap everything up."""
    # Grab all today's links!
    events = grab_events()
    for event in events:
        logging.info(event[0])
        [process_event(
            base + event[0].replace('results', 'racecards'), event[1])]
    [db.racingpost.update_one(r, {'$set': r}, upsert=True) for r in rows]


def get_racingpost():
    """Use this function to get racingpost table."""
    return dumps(list(d for d in db.racingpost.find(
        {'Update': {'$gte': datetime.now().strftime('%Y-%m-%d')},
         'Trainer': {'$ne': 'NOBODY'},
         'Jockey': {'$ne': 'NOBODY'}})))


if __name__ == '__main__':
    try:
        racingpost()
        # excelize()
    except:
        logging.critical(traceback.print_exc())
        input('Press any key to exit...')
        exit(1)
