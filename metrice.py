from prometheus_client import Gauge, start_http_server
from db.db_config import session, shutdown_session
import threading
import time
from logs.logs import Logger
from db.namecom import Domain as Namecom
from db.dynadot import Domain as Dynadot
from db.namecheap import Domain as Namecheap
from config import APP_NAME,LOG_PATH

# 配置日志（可根据需要替换为你已有的日志类）
info_log = Logger(LOG_PATH + '/' + APP_NAME + '-info.log', level='info')
err_log = Logger(LOG_PATH + '/' + APP_NAME + '-error.log', level='error')

# Prometheus 指标定义
domain_created_timestamp = Gauge(
    'domain_created_timestamp',
    'Domain creation timestamp',
    ['domainName', 'source']
)

domain_expires_timestamp = Gauge(
    'domain_expires_timestamp',
    'Domain expiration timestamp',
    ['domainName', 'source']
)

# 数据获取函数
def fetch_domains():
    # 确保会话处于干净状态
    if session.transaction and not session.transaction.is_active:
        session.rollback()
    all_data = []
    try:
        for model in [Namecheap, Dynadot, Namecom]:
            source = model.__tablename__
            domains = session.query(model).all()
            for d in domains:
                all_data.append({
                    'name': d.name,
                    'created': d.created,
                    'expires': d.expires,
                    'source': source
                })
    except Exception as e:
        err_log.logger.error(f"Database error: {e}")
    return all_data

# 指标更新函数
def update_metrics():
    while True:
        try:
            data = fetch_domains()

            domain_created_timestamp.clear()
            domain_expires_timestamp.clear()

            for item in data:
                domain_created_timestamp.labels(
                    domainName=item['name'], source=item['source']
                ).set(item['created'].timestamp() if item['created'] else 0)

                domain_expires_timestamp.labels(
                    domainName=item['name'], source=item['source']
                ).set(item['expires'].timestamp() if item['expires'] else 0)

            info_log.logger.info("Prometheus metrics updated.")
        except Exception as e:
            err_log.logger.error(f"Error updating metrics: {e}")

        time.sleep(30)  # 每 30 秒更新一次

# 启动 Prometheus 指标采集服务
def start_prometheus_exporter():
    start_http_server(10106)
    info_log.logger.info("Prometheus exporter started on port 10106")
    t = threading.Thread(target=update_metrics)
    t.daemon = True
    t.start()


