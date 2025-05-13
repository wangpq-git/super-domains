import requests
from db.cloudflare import Domain,session
from config import CF_CONFIG,LOG_PATH,APP_NAME
from logs.logs import Logger

info_log = Logger(LOG_PATH + '/' + APP_NAME + '-info.log', level='info')
err_log = Logger(LOG_PATH + '/' + APP_NAME + '-error.log', level='error')

def list_domains(account_id, email, api_key):
    # API 端点
    url = "https://api.cloudflare.com/client/v4/zones"

    # 请求头（Email + Key 认证方式）
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }

    # 查询参数（可根据需要调整）
    params = {
        "account.id": account_id,  # 按账户 ID 过滤
        "per_page": 200,  # 每页最多 50 条记录
        "page": 1,  # 页码（从 1 开始）
        "status": "active",  # 只显示活跃域名
        "order": "name",  # 按域名名称排序
        "direction": "asc"  # 升序排列
    }

    # 发送 GET 请求
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()  # 检查请求是否成功

    # 解析响应数据
    data = response.json()

    if data["success"]:
        zones = data["result"]
        for zone in zones:
            domain = Domain(
                account_id=account_id,
                name=zone["name"],
                status=zone["status"] if zone.get("status") else None,
                email=email,
                ns=", ".join(zone["name_servers"]) if zone.get("name_servers") else None,
                origin_ns=", ".join(zone["original_name_servers"]) if zone.get("original_name_servers") else None
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
        info_log.logger.info(f"CloudFlare [{email}] 账号，{len(zones)} 条记录已成功写入数据库。")
    else:
        err_log.logger.error(f"请求失败，状态码: {response.status_code}")
        err_log.logger.error(response.text)


def main():
    configs = CF_CONFIG["config"]
    for config in configs:
        account_id = config["accountId"]
        email = config["apiEmail"]
        api_key = config["apiKey"]

        list_domains(account_id, email, api_key)