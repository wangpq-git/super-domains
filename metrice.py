import atexit

from prometheus_client import Gauge, start_http_server
from sqlalchemy.exc import SQLAlchemyError

from db.db_config import session_scope,shutdown_session
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

# Prometheus指标定义（优化标签命名）
DOMAIN_INFO = Gauge(
    'domain_info',
    'Domain registration information',
    ['domain', 'registrar', 'created', 'expires']
)


def fetch_domains():
    """安全获取域名数据"""
    domains = []
    try:
        with session_scope() as session:
            for model in [Namecheap, Dynadot, Namecom]:
                try:
                    for d in session.query(model).yield_per(100):
                        domains.append({
                            'name': d.name,
                            'created': d.created,
                            'expires': d.expires,
                            'source': model.__tablename__
                        })
                except SQLAlchemyError as e:
                    err_log.logger.error(f"Query failed for {model.__name__}: {str(e)}")
                    continue
    except Exception as e:
        err_log.logger.error(f"Session error: {str(e)}")
    return domains


def update_metrics():
    """线程安全的指标更新"""
    while True:
        try:
            data = fetch_domains()

            # 清除旧指标（线程安全）
            DOMAIN_INFO.clear()

            # 批量更新指标
            for item in data:
                try:
                    DOMAIN_INFO.labels(
                        domain=item['name'],
                        registrar=item['source'],
                        created=item['created'].isoformat() if item['created'] else '',
                        expires=item['expires'].isoformat() if item['expires'] else ''
                    ).set(
                        item['expires'].timestamp() if item['expires'] else 0
                    )
                except Exception as e:
                    err_log.logger.error(f"Metric update failed for {item['name']}: {str(e)}")

            info_log.logger.info(f"Updated {len(data)} domains")

        except Exception as e:
            err_log.logger.error(f"Fatal update error: {str(e)}")
        finally:
            time.sleep(3600)  # 1小时更新间隔


def start_exporter():
    """启动监控服务"""
    try:
        start_http_server(10106)
        info_log.logger.info("Exporter started on port 10106")

        # 启动更新线程
        updater = threading.Thread(
            target=update_metrics,
            name="metrics-updater",
            daemon=True
        )
        updater.start()

        # 注册退出处理
        atexit.register(shutdown_session)
        return True
    except Exception as e:
        err_log.logger.error(f"Failed to start exporter: {str(e)}")
        return False