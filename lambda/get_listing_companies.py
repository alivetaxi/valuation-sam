""" This function gets listing companies information from TWSE. """

import boto3
import requests
from bs4 import BeautifulSoup

TABLE_NAME = 'valuation-sam-ListingCompanyTable-KLJKZWB1AE8'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)
URL = 'https://isin.twse.com.tw/isin/C_public.jsp?strMode='
strMode = ['2', '4']

def lambda_handler(event, context): # pylint: disable=unused-argument
    """ This is lambda handler. """

    companies = { company['company_id']: company for company in table.scan()['Items'] }

    for mode in strMode:
        resp = requests.get(URL + mode, timeout = 30)
        soup = BeautifulSoup(resp.text, 'html.parser')
        trs = soup.select('tr')
        for tr in trs:
            if len(tr.find_all()) == 7:
                id_name = tr.select_one(':nth-child(1)').get_text().split()
                if len(id_name) < 2:
                    continue

                co_id = id_name[0]
                name = id_name[1]
                industry = tr.select_one(':nth-child(5)').get_text()
                cfi_code = tr.select_one(':nth-child(6)').get_text()

                if cfi_code != 'ESVUFR' or name.find('KY') >= 0 or industry == '金融保險業':
                    continue

                company = companies.get(co_id)
                if company is None:
                    table.put_item(
                        Item = {
                            'company_id': co_id,
                            'company_name': name,
                            'industry': industry,
                            'process_time': 0
                        }
                    )
                else:
                    if name != company['company_name'] or industry != company['industry']:
                        table.update_item(
                            Key = {
                                'company_id': co_id
                            },
                            AttributeUpdates = {
                                'company_name': {
                                    'Value': name,
                                    'Action': 'PUT'
                                },
                                'industry': {
                                    'Value': industry,
                                    'Action': 'PUT'
                                }
                            }
                        )
                    companies.pop(co_id)

    for company in companies:
        table.delete_item(
            Key = {
                'company_id': company['company_id']
            }
        )

lambda_handler(None, None)
