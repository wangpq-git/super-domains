from datetime import datetime

import requests
import xml.etree.ElementTree as ET

from config import NAMECHEAP_API_KEY,NAMECHEAP_USERNAME
from db.namecheap import Domain,session

def fetch_domains():
    url = "https://api.namecheap.com/xml.response"
    params = {
        "ApiUser": NAMECHEAP_USERNAME,
        "ApiKey": NAMECHEAP_API_KEY,
        "UserName": NAMECHEAP_USERNAME,
        "Command": "namecheap.domains.getList",
        "ClientIp": "192.168.1.109"
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.text


def parse_and_store(xml_data):
    root = ET.fromstring(xml_data)
    ns = {'ns': 'http://api.namecheap.com/xml.response'}
    result = root.find('.//ns:DomainGetListResult', ns)

    if result is None:
        print("No domain list found.")
        return

    for domain in result.findall('ns:Domain', ns):
        domain_obj = Domain(
            domain_id=int(domain.attrib['ID']),
            name=domain.attrib['Name'],
            created=datetime.strptime(domain.attrib['Created'], '%m/%d/%Y'),
            expires=datetime.strptime(domain.attrib['Expires'], '%m/%d/%Y'),
            is_expired=domain.attrib['IsExpired'].lower() == 'true',
            is_locked=domain.attrib['IsLocked'].lower() == 'true',
            auto_renew=domain.attrib['AutoRenew'].lower() == 'true',
            whois_guard=domain.attrib['WhoisGuard'],
            is_our_dns=domain.attrib['IsOurDNS'].lower() == 'true'
        )

        # 如果已存在则更新，否则插入
        existing = session.query(Domain).filter_by(domain_id=domain_obj.domain_id).first()
        if existing:
            for attr, value in vars(domain_obj).items():
                if attr != "_sa_instance_state":
                    setattr(existing, attr, value)
        else:
            session.add(domain_obj)

    session.commit()
    print(f"NameCheap [{NAMECHEAP_USERNAME}] 账号，数据写入完成。")

def main():
    try:
        xml_data = fetch_domains()
        parse_and_store(xml_data)
    except Exception as e:
        print(f"NameCheap Error: {e}")

if __name__ == '__main__':
    main()