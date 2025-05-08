from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth

from config import NAMECOM_CONFIG
from db.namecom import Domain,session

def list_domains(username, token):
    url = 'https://api.name.com/v4/domains'
    response = requests.get(url, auth=HTTPBasicAuth(username, token))
    if response.status_code == 200:
        data = response.json()
        domains = data.get("domains", [])

        for item in domains:
            domain = Domain(
                account=username,
                name=item['domainName'],
                is_locked=item['locked'],
                auto_renew=item['autorenewEnabled'],
                created=datetime.fromisoformat(item['createDate'].replace('Z', '+00:00')),
                expires=datetime.fromisoformat(item['expireDate'].replace('Z', '+00:00'))
            )
            # 如果已存在则更新，否则插入
            existing = session.query(Domain).filter_by(name=domain.name).first()
            if existing:
                for attr, value in vars(domain).items():
                    if attr != "_sa_instance_state":
                        setattr(existing, attr, value)
            else:
                session.add(domain)
        session.commit()
        print(f"name.com [{username}] 账号，{len(domains)} 条记录已成功写入数据库。")
    else:
        print(f"请求失败，状态码: {response.status_code}")
        print(response.text)

def main():
    configs = NAMECOM_CONFIG["config"]
    for config in configs:
        username = config["userName"]
        token = config["token"]
        list_domains(username, token)