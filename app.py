import logging
from flask import Flask, request, jsonify, current_app
from flask_cors import CORS
from main import main
from db.db_config import Session, shutdown_session  # 修改为直接导入
from db.cloudflare import Domain as Cloudflare
from db.namecom import Domain as Namecom
from db.dynadot import Domain as Dynadot
from db.namecheap import Domain as Namecheap
from logs.logs import Logger
from config import APP_NAME,LOG_PATH
from metrice import start_prometheus_exporter


app = Flask(__name__)
CORS(app)

# 确保每个请求结束后清理会话
app.teardown_appcontext(shutdown_session)

def clean_domain_name(raw_name):
    """
    智能清理域名参数：
    1. 去除首尾空格
    2. 去除首尾的单/双引号
    3. 保留空字符串的原始值
    """
    if not raw_name:
        return ""
    cleaned = raw_name.strip()
    # 仅当首尾字符是引号时才去除（避免破坏合法域名）
    if (cleaned.startswith('"') and cleaned.endswith('"')) or \
            (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1]
    return cleaned.strip()


@app.route('/search', methods=['GET'])
def search_domain():
    # 获取并清理参数
    raw_name = request.args.get('name', '')
    domain_name = clean_domain_name(raw_name)

    if not domain_name:
        return jsonify({"error": "Parameter 'name' is required"}), 400

    # 定义要查询的所有表
    tables = {
        "cloudflare": Cloudflare,
        "namecom": Namecom,
        "dynadot": Dynadot,
        "namecheap": Namecheap
    }

    results = {}
    session = Session()
    try:
        for table_name, model in tables.items():
            # 精确查询（注意：SQLAlchemy的echo=True会在此打印实际SQL）
            domains = session.query(model).filter(
                model.name == domain_name
            ).all()

            if domains:
                results[table_name] = [
                    {c.name: getattr(d, c.name) for c in d.__table__.columns}
                    for d in domains
                ]
    except Exception as e:
        print(f"查询出错: {str(e)}")
        return jsonify({"error": "Database query failed"}), 500
    finally:
        session.close()

    # 返回结果或404
    if results:
        return jsonify(results)
    else:
        print("在所有表中均未找到匹配记录")
        return jsonify({"message": "Domain not found in any table"}), 404

@app.route('/sync', methods=['GET'])
def sync_data():
    session = Session()
    try:
        main()  # 将会话传递给main函数
        session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        session.rollback()  # 显式回滚
        current_app.logger.error(f"Sync failed: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e),
            'type': type(e).__name__
        }), 500
    finally:
        session.close()  # 确保关闭

@app.route('/', methods=['GET'])
def health():
    session = Session()
    try:
        return jsonify({"status": "healthy"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


def configure_logging():
    # 获取 Flask 的日志处理器
    flask_logger = app.logger
    werkzeug_logger = logging.getLogger('werkzeug')

    # 移除默认的 Flask 和 werkzeug 日志处理器
    for handler in list(flask_logger.handlers):
        flask_logger.removeHandler(handler)
    for handler in list(werkzeug_logger.handlers):
        werkzeug_logger.removeHandler(handler)

    # 添加自定义的日志处理器
    flask_logger.addHandler(info_log.logger.handlers[0])  # 文件日志处理器
    flask_logger.addHandler(info_log.logger.handlers[1])  # 屏幕日志处理器

    werkzeug_logger.addHandler(info_log.logger.handlers[0])  # 文件日志处理器
    werkzeug_logger.addHandler(info_log.logger.handlers[1])  # 屏幕日志处理器

    # 设置日志级别
    flask_logger.setLevel(logging.INFO)
    werkzeug_logger.setLevel(logging.INFO)

    # 确保日志处理器生效
    logging.getLogger().setLevel(logging.INFO)


if __name__ == '__main__':
    info_log = Logger(LOG_PATH + '/' + APP_NAME + '-info.log', level='info')
    err_log = Logger(LOG_PATH + '/' + APP_NAME + '-error.log', level='error')
    configure_logging()
    start_prometheus_exporter()
    app.run(host='0.0.0.0', port=5000, debug=False)
