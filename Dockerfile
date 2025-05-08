FROM tencnet-ptc.tencentcloudcr.com/tencent-ptc/python3-builder-flask:v3.9.17

# copy run file
COPY ./ /data/code/
RUN sudo chmod +x /data/code/run.sh    && \
    sudo chown -R ${AppUser}:${AppGroup} /data
# set workdir
RUN pip3 install --no-cache-dir -r /data/code/requirements.txt

WORKDIR /data/code/
CMD ["/bin/bash","-c","bash /data/code/run.sh "]

