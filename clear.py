
from datetime import datetime, timedelta
from db.db_config import session_scope
from db.dynadot import Domain as DynadotDomain
from db.cloudflare import Domain as CloudflareDomain
from db.namecom import Domain as NamecomDomain
from db.namecheap import Domain as NamecheapDomain

from sqlalchemy.orm.attributes import InstrumentedAttribute
from config import LOG_PATH,APP_NAME
from logs.logs import Logger

info_log = Logger(LOG_PATH + '/' + APP_NAME + '-info.log', level='info')
err_log = Logger(LOG_PATH + '/' + APP_NAME + '-error.log', level='error')


def get_expired_domains(session, model, deadline):
    return session.query(model).filter(model.expires < deadline).all()

def clear_expired_domains():
    deadline = datetime.now() - timedelta(days=3)
    expired_domain_names = set()  # 记录已删除的域名名

    with session_scope() as session:
        # 处理 dynadot、namecom、namecheap 三张表
        for name, model in [
            ('dynadot', DynadotDomain),
            ('namecom', NamecomDomain),
            ('namecheap', NamecheapDomain)
        ]:
            expired = get_expired_domains(session, model, deadline)
            count = len(expired)
            if count:
                for domain in expired:
                    expired_domain_names.add(domain.name)
                    session.delete(domain)
                info_log.logger.info(f"[删除] 表 `{name}` 中删除了 {count} 条过期域名")
            else:
                info_log.logger.info(f"[无过期] 表 `{name}` 中无过期域名")

        # 删除 cloudflare 表中对应的域名
        if expired_domain_names:
            cf_domains = session.query(CloudflareDomain).filter(CloudflareDomain.name.in_(expired_domain_names)).all()
            if cf_domains:
                for domain in cf_domains:
                    session.delete(domain)
                info_log.logger.info(f"[同步删除] 表 `cloudflare` 中删除了 {len(cf_domains)} 条匹配的域名")
            else:
                info_log.logger.info("[同步删除] 表 `cloudflare` 中无匹配的域名")
        else:
            info_log.logger.info("[跳过] 没有需要删除的域名，无需处理 cloudflare 表")

