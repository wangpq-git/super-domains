"""
SQLAlchemy 基础模型
定义所有 ORM 模型的基类
"""
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """
    SQLAlchemy 声明式基类
    所有 ORM 模型都应继承此类
    """

    # 自动生成表名（小写的类名）
    @declared_attr.directive
    @classmethod
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    # 通用查询方法占位符
    def to_dict(self) -> dict:
        """
        将模型转换为字典
        子类可覆盖此方法以自定义输出
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
