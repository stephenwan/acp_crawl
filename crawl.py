import json
import time
import logging
import logging.config
import yaml
import pymysql as db
from itertools import dropwhile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ChromeOptions


class AcpCrawler:
    def __init__(self, db_config):
        self.db_config = db_config

    def __enter__(self):
        self.browser = webdriver.Chrome()
        if self.db_config is not None:
            self.db_connection = db.connect(host=self.db_config['host'],
                                            user=self.db_config['user'],
                                            password=self.db_config['password'],
                                            db=self.db_config['database'],
                                            cursorclass=db.cursors.DictCursor)
        return self

    def __exit__(self, *exc):
        self.browser.close()
        self.db_connection.close()


    def set_country(self, code):
        self.browser.get('http://shop.acprail.com/#/ptp/point__to_point_tickets/')
        try:
            WebDriverWait(self.browser, 30).until(
                EC.presence_of_element_located((By.ID, "options-navigation-select-country"))
            )
            time.sleep(1)
            self.browser.execute_script('$("#options-navigation-select-country").val("{}")'.format(code))
            self.browser.execute_script('$("#options-navigation-select-country").change()')

            logging.info('0.CountrySelected')
        except Exception as e:
            logging.error(str(e))
            return


    def get_prices(self, from_station, to_station, on_date, on_hour):

        self.browser.get('http://shop.acprail.com/#/ptp/point__to_point_tickets/')

        logging.info('Start:{},{},{},{}'.format(from_station, to_station, on_date, on_hour))

        try:
            WebDriverWait(self.browser, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "booking_form_submit"))
            )
            logging.info('1.SubmitLocated')
            time.sleep(2)
        except Exception as e:
            logging.error(str(e))
            return

        logging.info('2.InvockingScripts')
        self.browser.execute_script('$("input.from_station").val("{}")'.format(from_station))
        self.browser.execute_script('$("input.to_station").val("{}")'.format(to_station))
        self.browser.execute_script('$("input#input-departure").val("{}")'.format(on_date))
        self.browser.execute_script('$("select#departure_time").val("{}")'.format(on_hour))
        self.browser.execute_script('$("input.age_of_traveller").val("20")')
        self.browser.execute_script('$("button.booking_form_submit").click()')

        logging.info('3.InvockingScriptsDone')

        try:
            WebDriverWait(self.browser, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "a_journey"))
            )

            logging.info('4.AJourneyLocated')
            time.sleep(1)

            trs = self.browser.find_elements_by_css_selector('.a_journey')

            logging.info('5.FoundJourneys:{}'.format(len(trs)))
            journeys = []

            for tr in trs:
                tds = tr.find_elements_by_tag_name('td')
                if len(tds) != 7:
                    logging.error('invalidTds:{}'.format(len(tds)))
                    continue
                else:
                    journeys.append({
                        'from': from_station,
                        'to': to_station,
                        'date': on_date,
                        'hour': on_hour,
                        'rfrom': tds[0].text,
                        'rto': tds[1].text,
                        'rdept': tds[2].text,
                        'rarrt': tds[3].text,
                        'rprice': tds[6].text
                    })
                    logging.info('..addOne')
            logging.info('6.JourneysAdded')

            self._persist_journeys(journeys)
            return journeys
        except Exception as e:
            self._persist_journeys([{
                'from': from_station,
                'to': to_station,
                'date': on_date,
                'hour': on_hour,
                'rfrom': '',
                'rto': '',
                'rdept': '',
                'rarrt': '',
                'rprice': ''
            }])
            logging.error(str(e))
            return

    def _persist_journeys(self, journeys):
        if self.db_connection is not None:
            sql = sql_template.format(self.db_config['table'])
            with self.db_connection.cursor() as cursor:
                for journey in journeys:
                    cursor.execute(sql, journey)
                self.db_connection.commit()
            logging.info('7.JourneysPersisted')


def main():
    config = load_config()
    logging.config.dictConfig(config['logging'])
    session = config['session']

    with AcpCrawler(config.get('db')) as crawler:
        crawler.set_country('GB')
        if session['routes'].get('all'):
            routes = get_all_routes()
        else:
            routes = get_routes_after(session['routes']['baseline']['from'],
                                      session['routes']['baseline']['to'])

        for on_date in session['dates']:
            for on_hour in session['hours']:
                for route in routes:
                    crawler.get_prices(mappings[route['from']], mappings[route['to']], on_date, on_hour)


def load_config():
    with open('dev.yml', 'r') as f:
        return yaml.load(f)


def get_all_routes():
    with open('routes_in_excel.json', 'r') as f:
        rs = json.load(f)
    return rs

def get_routes_after(from_station, to_station):
    routes = get_all_routes()
    _r = dropwhile(lambda e: (e['from'] != from_station) or (e['to'] != to_station), routes)
    up_to = next(_r)
    logging.info('StartingFrom:{from},{to}'.format(**up_to))
    return list(_r)


sql_template = '''
INSERT INTO `{}` (`query_from`, `query_to`, `query_date`, `query_hour`, `result_from`, `result_to`,
                 `result_dep_time`, `result_arr_time`, `result_price`)
                VALUES (%(from)s, %(to)s, %(date)s, %(hour)s, %(rfrom)s,
                        %(rto)s, %(rdept)s, %(rarrt)s, %(rprice)s)
'''

mappings = {
    'ardrossan': 'Ardrossan Stations',
    'bedford': 'Bedford All Stations',
    'birkenhead': 'Birkenhead Stations',
    'birmingham': 'Birmingham All Stations',
    'blackpool': 'Blackpool Stations',
    'bradford': 'Bradford All Stations',
    'brighton': 'Brighton',
    'bristol': 'Bristol Stations',
    'burnley': 'BURNLEY STATIONS',
    'canterbury': 'Canterbury All Stations',
    'cardiff': 'Cardiff Central',  # there are a few others
    'colchester': 'Colchester',
    'croydon': 'Coryton',  # typo???!!!
    'dorchester': 'Dorchester West',  # 'Dorchester South'
    'dorking': 'Dorking',
    'edenbridge': 'Edenbridge Stations',
    'edinburgh': 'Edinburgh',
    'enfield': 'Enfield Stations',
    'exeter': 'EXETER STATIONS',
    'falkirk': 'Falkirk Stations',
    'farnborough': 'Farnborough',
    'folkestone': 'Folkestone West',  # 'Folkestone Central'
    'gainsborough': 'GAINSB0R0UGH STATIONS',
    'glasgow': 'Glasgow All Stations',
    'guildford': 'Guildford',
    'hamilton': 'Hamilton West',  # 'Hamilton Central'
    'helensburgh': 'Helensburgh Stations',
    'hertford': 'Hertford Stations',
    'lichfield': 'LICHFIELD STATIONS',
    'liverpool': 'Liverpool All Stations',
    'london': 'London All Stations',
    'lymington': 'Lymington Town',  # there are a few others
    'maidstone': 'Maidstone Stations',
    'manchester': 'Manchester All Stations',
    'new mills': 'New Mills Central',  # 'New Mills Newtown'
    'newark': 'Newark Stations',
    'newbury': 'Newbury',
    'newhaven': 'Newhaven Town',  # 'Newhaven Harbour'
    'plymouth': 'Plymouth',
    'pontefract': 'Pontefract Stations',
    'portsmouth': 'Portsmouth Harbour',   # 'Portsmouth Arms'
    'reading': 'Reading',
    'southend': 'Southend All Stations',
    'tyndrum': 'TYNDRUM STATIONS',
    'wakefield': 'Wakefield Westgate',  # 'WAKEFIELD KIRKGATE'
    'warrington': 'Warrington Central',  # 'Warrington Bank Quay'
    'west hampstead': 'West Hampstead',
    'wigan': 'WIGAN STATIONS',
    'worcester': 'Worcester Stations',
    'wrexham': 'Wrexham General',  # 'Wrexham Central'
}
