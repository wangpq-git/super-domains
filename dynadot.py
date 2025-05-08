import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from config import DYNADOT_API_KEY
from db.dynadot import Domain, session


def parse_unix_timestamp(ms_str):
    try:
        ts = int(ms_str) / 1000
        return datetime.utcfromtimestamp(ts)
    except:
        return None


def parse_and_store(xml_data):
    root = ET.fromstring(xml_data)
    domains = root.findall('.//Domain')

    if not domains:
        print("No domain list found.")
        return

    for domain in domains:
        domain_obj = Domain(
            name=domain.findtext('Name'),
            created=parse_unix_timestamp(domain.findtext('Registration')),
            expires=parse_unix_timestamp(domain.findtext('Expiration')),
            is_locked=domain.findtext('Locked').lower() == 'yes',
            privacy=domain.findtext('Privacy'),
            is_for_sale=domain.findtext('IsForSale'),
            renew_option=domain.findtext('RenewOption')
        )
        # 如果已存在则更新，否则插入
        existing = session.query(Domain).filter_by(name=domain_obj.name).first()
        if existing:
            for attr, value in vars(domain_obj).items():
                if attr != "_sa_instance_state":
                    setattr(existing, attr, value)
        else:
            session.add(domain_obj)

    session.commit()
    print(f"Dynadot 账号数据写入完成！")


def fetch_and_save_dynadot_domains():
    url = "https://api.dynadot.com/api3.xml"
    params = {
        "key": DYNADOT_API_KEY,
        "command": "list_domain"
    }

    response = requests.get(url, params=params)
    parse_and_store(response.text)


def main():
    fetch_and_save_dynadot_domains()