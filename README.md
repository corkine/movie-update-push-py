pyHuginn 基于 Python 的定时、远程更新配置、可扩展的极简爬虫程序

# 依赖

Python3, lxml, bs4, requests, pyhocon

![](http://static2.mazhangjing.com/badge/python.png)

# 运行

执行如下代码，传入远程配置的文件以开始进行数据收集和通知。

```python
python -u main.py --config http://xxx.xxx.xxx
nohup python -u main.py --config http://xxxxxx.mazhangjing.com/xxxxxx.conf 1>>pyHuginn.log 2>&1 &
```

# 效果

![](http://static2.mazhangjing.com/20201211/a16f2b6_屏幕截图2020-12-11205132.png)

# 框架

需要收集信息的网站的数据爬取通过 MovieHuginn 类，在 refreshConfig 中从远程/本地配置文件来获取需要爬取的原信息，比如需要爬取的美剧地址，在 doEachTime 中进行每次的数据爬取。doEachTime 主要通过 MovieUpdater 提供爬虫逻辑来处理数据，并且在 MovieHuginn 中进行 Slack 通知。

## V2.0

添加了 iqiyi 视频推送服务。