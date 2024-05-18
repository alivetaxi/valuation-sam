""" This function gets the report from a company. """

from decimal import Decimal
import time

import boto3
import requests
from bs4 import BeautifulSoup

COMPANY_TABLE_NAME = 'valuation-sam-ListingCompanyTable-LDPLI51PXXDP'
REPORT_TABLE_NAME = 'valuation-sam-CompanyReportTable-7EAUU6GT8G4Y'
dynamodb = boto3.resource('dynamodb')
company_table = dynamodb.Table(COMPANY_TABLE_NAME)
report_table = dynamodb.Table(REPORT_TABLE_NAME)
parse_tables = ['BalanceSheet', 'StatementOfComprehensiveIncome', 'StatementsOfCashFlows']

def get_company_to_run():
    """ This function gets the company to deal with. """

    companies = company_table.scan()['Items']
    company_to_run = min(companies, key=lambda c: c['process_time'])
    print(company_to_run)
    return company_to_run

def get_report_records(company_id):
    """ This function gets reports already in db. """

    reports = report_table.query(
        Select = 'SPECIFIC_ATTRIBUTES',
        ProjectionExpression = 'year_quarter',
        KeyConditionExpression = boto3.dynamodb.conditions.Key('company_id').eq(company_id)
    )['Items']

    return [r['year_quarter'] for r in reports]

def get_report_paths(company_id, reports):
    """ This function gets urls for new financial reports. """

    resp = requests.post(
        'https://mops.twse.com.tw/mops/web/ajax_t203sb01',
        {
            'encodeURIComponent': 1,
            'step': 1,
            'firstin': 1,
            'off': 1,
            'queryName': 'co_id',
            'inpuType': 'co_id',
            'TYPEK': 'all',
            'co_id': company_id
        },
        timeout = 30
    )

    soup = BeautifulSoup(resp.text, 'html.parser')
    trs = soup.select('tr')
    path_map = {}
    for tr in trs:
        path_td = tr.select_one(':nth-child(4) > input')
        if path_td is None:
            continue

        report_path = path_td.attrs['onclick']
        if report_path is None:
            continue

        minguo_year_quarter = tr.select_one(':nth-child(1)').get_text()
        if minguo_year_quarter is None or len(minguo_year_quarter) < 5:
            continue

        year = int(minguo_year_quarter[0:3]) + 1911
        if year < 2020:
            continue

        year_quarter = str(year) + minguo_year_quarter[3:5]
        if year_quarter in reports:
            continue

        path_map[year_quarter] = report_path[13:len(report_path)-10]

        if len(path_map) == 5:
            break

    return path_map

def get_report(company_id, report_paths):
    """ This function parses xbrls and save data to db. """

    for year_quarter, report_path in report_paths.items():
        report = {
            'company_id': company_id,
            'year_quarter': year_quarter
        }
        resp = requests.get('https://mops.twse.com.tw' + report_path, timeout = 30)
        soup = BeautifulSoup(resp.text, 'html.parser')

        for parse_table in parse_tables:
            trs = soup.select('#' + parse_table + ' + div + table tr')
            for tr in trs:
                acc_code = tr.select_one(':nth-child(1)').get_text().strip()
                if len(acc_code) == 0 or len(acc_code) > 6:
                    continue

                acc_value = tr.select_one(':nth-child(3)').get_text().strip().replace(',', '')
                if acc_value.startswith('('):
                    acc_value = '-' + acc_value[1:len(acc_value)-1]

                report[acc_code] = Decimal(acc_value)

        if len(report) > 2:
            report_table.put_item(Item = report)
        else:
            print(company_id + ' / ' + year_quarter + ' empty report error')

def update_company_process_time(company_id):
    """ This function updates the process time of company """

    company_table.update_item(
        Key = { 'company_id': company_id },
        UpdateExpression = "set process_time = :process_time",
        ExpressionAttributeValues = { ':process_time': Decimal(time.time()) }
    )


def lambda_handler(event, context): # pylint: disable=unused-argument
    """ This is lambda handler. """

    company_to_run = get_company_to_run()
    reports = get_report_records(company_to_run['company_id'])
    report_paths = get_report_paths(company_to_run['company_id'], reports)
    if len(report_paths) > 0:
        get_report(company_to_run['company_id'], report_paths)

    update_company_process_time(company_to_run['company_id'])

lambda_handler(None, None)
