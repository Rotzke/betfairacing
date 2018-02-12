#!/usr/bin/python3
"""Betfair horse racing backs parser."""
import argparse
import itertools
import json
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bson import SON
from pymongo import MongoClient

import pandas as pd
from tabulate import tabulate

client = MongoClient()
db = client.betfair

data = False
sleeper = 10
ranger = 70.0
woe = False
regexp = r'-[6-9][0-9]?[0-9]?\.[0-9][0-9]?|-[1-9][0-9][0-9]?\.[0-9][0-9]?'

parser = argparse.ArgumentParser()
parser.add_argument("--ranger",
                    help="Set ranger value, man.", required=False)


def get_races():
    """Get current races list."""
    pipeline =\
        [{"$match":
          {"Update":
           {"$gte": '{}'.format(datetime.utcnow().strftime('%Y-%m-%d'))
            },
           "Time":
           {"$gte": '{}'.format(datetime.utcnow().strftime('%H:%M:%S'))}
           }
          },
         {"$group":
          {"_id":
           {"Venue": "$Venue",
            "Race": "$Race",
            "Time": "$Time"
            }
           }
          },
         {"$sort": SON([("_id.Time", 1)])
          }
         ]
    return len(list(db.basic.aggregate(pipeline)))


def send_message(msg, fromaddr, toaddrs):
    """Send the message via our own SMTP server."""
    username = email_username
    password = email_password
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.ehlo()
    server.starttls()
    server.login(username, password)
    server.send_message(msg, fromaddr, toaddrs)
    server.quit()


def send_letter(alert):
    """Use this function to send letter."""
    fromaddr = fromaddress
    toaddrs = toaddress
    # Letter to Alan
    msg = MIMEMultipart('alternative')
    text = alert
    html = '<html><body><pre style="font: monospace">' + \
        alert.replace("\n", "<br />") + '</body></html>'
    msg['Subject'] = 'BetfairMaster Alert!'
    msg['From'] = fromaddr
    msg['To'] = toaddrs
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')
    msg.attach(part1)
    msg.attach(part2)
    send_message(msg, fromaddr, toaddrs)


def email_alan(df, date):
    """Search for important horses and email Alan."""
    emails = os.path.join('data', '{}'.format(date), 'emails')
    alert = df.loc[df.iloc[:, 2].astype(str).str.contains(regexp)]
    horses = []
    if os.path.exists(emails):
        with open(emails, 'r') as emails_file:
            horses = [h.strip() for h in emails_file.readlines()]
            alert = alert[~alert['Horse'].isin(horses)]
    if not alert.empty:
        send_letter(tabulate([list(row)
                              for row in alert.values],
                             headers=list(alert.columns),
                             tablefmt='psql'))
        with open(emails, 'a') as emails_file:
            for h in alert['Horse'].tolist():
                if h not in horses:
                    emails_file.write(h + '\n')


def pricerator(e):
    """Generate price."""
    try:
        return (item for item
                in data
                if item['Horse'] == e[
                    'Horse']
                and item['Time'] == e[
                    'Time']
                and floatizer(
                    item['Price'])
                ).__next__()['Price']
    except:
        return False


def thirty_five(data):
    """Check if price is fine for XXXX-XX-XX-basic.csv."""
    try:
        return float(data) <= ranger
    except:
        return False


def sign(data):
    """Add + or - sign to number."""
    if float(data) > 0:
        return round(float(data), 2)
    elif float(data) < 0:
        return round(float(data), 2)
    else:
        return float(0)


def floatizer(digit):
    """Check if number is float."""
    try:
        float(digit)
        return True
    except:
        return False


def login():
    """Get the session key."""
    headers = {'X-Application': xapplication}
    payload = {'username': payloadusername,
               'password': payloadpassword}
    response = requests.post(
        'https://identitysso.betfair.com/api/certlogin',
        cert='/home/ubuntu/betfairacing/modules/assets/client-2048.pem',
        headers=headers, data=payload)
    return response.json()


def print_table(races, horses, goal, timestamp, date):
    """Print neat table of results."""
    global data
    table = []

    def f(x):
        x.loc[-1] = pd.Series([])
        return x
    for r in horses['result']:
        for h in r['runners']:
            entry = []
            event = (item for item in races['result']
                     if item['marketId'] == r['marketId']).__next__()
            entry.append(event['event']['name'].upper()[:3])
            horse = (item for item in event['runners']
                     if item['selectionId'] == h['selectionId']).__next__()
            start_time = event['marketStartTime'].split('T')[-1].split('.')[0]
            entry.append((datetime.strptime(start_time, '%H:%M:%S') +
                          timedelta(hours=0)).strftime('%H:%M:%S'))
            entry.append(horse['runnerName'])
            entry.append(event['marketName'])
            try:
                entry.append(max([float(x['price']) for x
                                  in h['ex']['availableToBack']]))
            except:
                entry.append('N/A')
            try:
                entry.append(sorted(h['ex']['availableToBack'],
                                    key=lambda k: k['price'],
                                    reverse=True)[0]['size'])
            except:
                entry.append('N/A')
            try:
                entry.append(sorted(h['ex']['availableToLay'],
                                    key=lambda k: k['price'],
                                    reverse=False)[0]['size'])
            except:
                entry.append('N/A')
            entry.append(datetime.now().strftime('%Y-%m-%d'))
            table.append(entry)
    if goal == 'basic':
        data = [{'Venue': e[0],
                 'Time': e[1],
                 'Horse': e[2],
                 'Race': e[3],
                 'Price': e[4],
                 'Update': e[7],
                 'Back': e[5],
                 'Lay': e[6]
                 } for e in table if thirty_five(e[4])]
        [db.basic.update_one(d, {"$set": d}, upsert=True) for d in data]
    elif goal == 'compare':
        data = list(db.basic.find({'Update': date}))
        compare = [{'Venue': e[0],
                    'Time': e[1],
                    'Horse': e[2],
                    'Race': e[3],
                    'Price': e[4],
                    'Update': e[7],
                    'Back': e[5],
                    'Lay': e[6]
                    } for e in table if thirty_five(e[4])]

        difference = [[e['Venue'], e['Time'],
                       sign((float(e['Price']) - float(pricerator(e)
                                                       ))),
                       e['Horse'],
                       e['Race'],
                       e['Back'], e['Lay'], timestamp.replace('-', ':')
                       ] for e in compare
                      if floatizer(e['Price']
                                   ) and pricerator(e)]
        # maxissimo = [{'Horse': i[3], 'Price': i[2]} for i in difference]
        # max_to_write = []
        # max_file = os.path.join('data', '{}'.format(
        #     date), '{}-max.csv'.format(date))
        # if os.path.exists(max_file):
        #     with open(max_file, 'r') as csvfile:
        #         reader = csv.DictReader(csvfile)
        #        for h in reader:
        #            if not [item for item in maxissimo
        #                    if item["Horse"] == h['Horse']]:
        #                maxissimo.append(h)
        #            else:
        #                maxissimo_item =\
        #                    [item for item in maxissimo if item["Horse"]
        #                        == h['Horse']][0]
        #                if maxissimo_item['Price'] < float(h['Price']):
        #                    max_to_write.append(maxissimo_item)
        #                else:
        #                    max_to_write.append(h)
        # else:
        #    max_to_write = maxissimo
        # with open(max_file, 'w') as csvfile:
        #    fieldnames = ['Horse', 'Price']
        #    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        #    writer.writeheader()
        #    [writer.writerow(i) for i in sorted(max_to_write,
        #                                        key=lambda k: k['Horse'])]
        tablissimo = pd.DataFrame(difference, index=None,
                                  columns=[
                                      'Venue', 'Time', 'Price', 'Horse',
                                      'Race', 'Back', 'Lay', 'Update', ])
        tablissimo = tablissimo.sort_values(
            ['Time', 'Price'], ascending=[True, True])
        tablissito = tablissimo[:30].groupby(
            ['Time'], as_index=False).apply(f).fillna('').to_dict('records')
        # if not tablissito.empty:
        #    email_alan(tablissito, date)
        # tablissimo.groupby(
        #    ['Time'],
        #    as_index=False
        # ).apply(f).fillna('').to_csv(os.path.join('data', '{}'.format(date),
        #                                          '{}.csv'.format(
        #    datetime.now().strftime("%H-%M-%S"))), index=False)
        return tablissito


def get_data(mode):
    """Parse and dump all horses data."""
    global data
    timestamp = datetime.now().strftime("%H-%M-%S")
    date = datetime.now().strftime("%Y-%m-%d")
    # Login procedure
    login_data = login()
    login_status = login_data['loginStatus']
    if login_status != 'SUCCESS':
        return

    # Starting main session
    session = requests.Session()
    url = "https://api.betfair.com/exchange/betting/json-rpc/v1"
    header = {'X-Application': xapplication,
              'X-Authentication': login_data['sessionToken'],
              'content-type': 'application/json'}
    # Getting all horse races for the date
    events_req = """
    {{
       "jsonrpc": "2.0",
       "method": "SportsAPING/v1.0/listEvents",
       "params": {{"filter":
                    {{
                       "eventTypeIds": ["7"],
                       "marketCountries": ["GB", "IE"],
                       "marketStartTime": {{
                                             "from": "{}T00:00:00Z",
                                             "to": "{}T23:59:00Z"
                                           }}
                     }}, "id": 1
                  }}
     }}
    """.format(date, date)
    events_response = session.post(url, data=events_req, headers=header)
    events = [c['event']['id'] for c in events_response.json()['result']]

    # Getting all events of each race
    event_req = """
    {{
       "jsonrpc": "2.0",
       "method": "SportsAPING/v1.0/listMarketCatalogue",
       "params": {{"filter":
                    {{
                       "eventIds": [{}],
                       "marketStartTime": {{
                                             "from": "{}T00:00:00Z",
                                             "to": "{}T23:59:00Z"
                                           }}
                     }},
                  "maxResults": "500",
                  "marketProjection": [
                    "COMPETITION",
                    "EVENT",
                    "EVENT_TYPE",
                    "MARKET_START_TIME",
                    "RUNNER_DESCRIPTION"
                    ]
                  }}
     }}
    """.format('"' + '","'.join(events) + '"', date, date)

    event_response = session.post(url, data=event_req, headers=header)
    races_json = event_response.json()

    # Filtering all race events for regular ones
    races = [e['marketId'] for e in event_response.json()['result']
             if e['marketName'][0].isdigit()
             and not e['marketName'].endswith('TBP')]
    if len(races) > 0:
        pass
    else:
        return
    chunks = [races[x:x + 40] for x in range(0, len(races), 40)]
    races = []
    for c in chunks:
        race_req = """
        {{
           "jsonrpc": "2.0",
           "method": "SportsAPING/v1.0/listMarketBook",
           "params": {{
                        "marketIds": [{}],
                        "priceProjection": {{
                           "priceData": ["EX_BEST_OFFERS"],
                           "virtualise": "true"
                                            }}
                      }}
         }}
        """.format('"' + '","'.join(c) + '"')
        races.append(session.post(url, data=race_req,
                                  headers=header).json()['result'])
    race_response = {}
    race_response['result'] = list(itertools.chain(*races))
    if mode == 'basic':
        return print_table(races_json, race_response,
                           'basic', timestamp, date)
    else:
        return print_table(races_json, race_response,
                           'compare', timestamp, date)


if __name__ == '__main__':
    from config import *
    if parser.parse_args().ranger:
        ranger = float(parser.parse_args().ranger)
    get_data('basic')
else:
    from modules.config import *
