"""托管服务的自有控制管道；独立serve不启用此监护行为。"""
from __future__ import annotations

import json
import os
import signal
import threading
import time
import uuid


def serve(app, config, run_id: str, control_fd: int, watch_fd: int) -> None:
    """报告同一app实例，父管道断开时保持监督直到自有组被回收。"""
    import uvicorn
    if str(uuid.UUID(run_id)) != run_id or os.getpgrp() == os.getpid():
        raise ValueError('托管服务身份无效')
    record={'version':1,'run_id':run_id,'instance_id':app.state.boundary.instance,'config_id':config.config_id,
            'index_config_id':config.index_config_id,'activity_config_id':config.activity_config_id if config.activity_options else None}
    if config.etf_options:
        record['etf_config_id'] = config.etf_config_id
    os.write(control_fd,(json.dumps(record)+'\n').encode());os.close(control_fd)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=config.port,workers=1,reload=False,
                                       proxy_headers=False,server_header=False,access_log=False))
    unexpected=threading.Event(); finished=threading.Event()
    def watch():
        with os.fdopen(watch_fd,'rb') as pipe: message=pipe.readline()
        if message != b'stop\n': unexpected.set()
        server.should_exit=True
        if unexpected.is_set():
            time.sleep(7)
            os.killpg(os.getpgrp(),signal.SIGKILL)
        finished.set()
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    server.run()
    if unexpected.is_set(): finished.wait(8)
