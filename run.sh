#!/bin/bash
# 以对应用启动时，1）部分文件没有权限；2）/data/logs 挂载到容器后普通用户无写权限
sudo chown -R ${AppUser}:${AppGroup} /data
python3 app.py
