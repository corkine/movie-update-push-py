from pyhocon import ConfigFactory
from typing import NamedTuple, List, TypeVar, Generic
from bs4 import BeautifulSoup
import time
import requests
import traceback
import json
import re

T = TypeVar('T')

class Movie(NamedTuple):
    name:str
    detailURL:str
    resourceURL:str
    pushURL:str
    kind:str

class Resource(NamedTuple):
    guid:int
    title:str
    download:str
    movie: Movie

class MovieDB:
    guids = []
    def diff(self,allResources:List[Resource]) -> List[Resource]:
        result = []
        for res in allResources:
            if not res.guid in self.guids:
                result.append(res)
        return result
    def storeResources(self, resources:List[Resource]) -> None:
        self._keepDB_Health()
        for resource in resources:
            if resource.guid not in self.guids:
                self.guids.append(resource.guid)
    def _keepDB_Health(self):
        if len(self.guids) > 5000: self.guids = []

class MovieUpdater(object):
    def __init__(self, movieDB:MovieDB):
        self.movieDB = movieDB

    def checkMovieResources(self, movie:Movie) -> List[Resource]:
        headers = {
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language":"zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "DNT": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
        }
        r = requests.get(movie.resourceURL,headers=headers,timeout=10)
        assert(r.status_code == 200)
        soup = BeautifulSoup(r.text,"lxml")
        items = soup.find_all("item")
        result = []
        for item in items:
            guid = item.find("guid").text
            magnet = item.find("magnet")
            if magnet == None:
                download = ""
            else:
                download = magnet.text
            title = item.find("title").text
            result.append(Resource(guid, title, download, movie))
        return result

    def diffUpdateFormat(self,resources:List[Resource]) -> List[str]:
        resources = self.movieDB.diff(resources)
        self.movieDB.storeResources(resources)
        return self._formatMovieUpdate(resources)

    def _formatResource_old(self,resource:Resource) -> str:
            return "%s <%s|详情>"\
                %(resource.title, resource.movie.detailURL)

    def _formatResource(self,resource:Resource) -> str:
            try:
                res = re.findall("(\w+.*?)(S\d+E\d+)",resource.title)
                title, se = res[0]
                title = title.replace("."," ")
                return "\"%s\" 有更新 - %s <%s|文件> <%s|详情>" \
                    %(title, se, "http://" + resource.title, resource.movie.detailURL)
            except Exception as e:
                # print("ERROR FORMAT", str(e))
                return "[有更新] %s <%s|详情>"\
                    %(resource.title, resource.movie.detailURL)

    def _formatMovieUpdate(self,resources:List[Resource]) -> List[str]:
        if len(resources) > 3: return ["\"%s\" 有多条更新 <%s|详情>" \
            %(resources[0].movie.name, resources[0].movie.detailURL)]
        else: return [self._formatResource(res) for res in resources]

class MovieHuginn(object):
    def __init__(self, configURL:str, updaters) -> None:
        self.configURL = configURL
        self.sleepSecs = -1
        self.items = []
        self.updaters = updaters
        self.refreshConfig()

    def refreshConfig(self) -> None:
        conf = ConfigFactory.parse_URL(self.configURL)
        if (type(conf) == list):
            conf = ConfigFactory.parse_file("default.conf")
        CHECK_SLEEP = conf.get_int("push.sleep")
        MOVIE_LIST = conf.get_list("items")
        logging.info("Update with Sleep Seconds %s, Keywords %s"\
            %(CHECK_SLEEP, str(MOVIE_LIST)))
        movies = []
        for MOV in MOVIE_LIST:
            movies.append(Movie(MOV.get_string("name"),\
                                MOV.get_string("detailURL"),\
                                MOV.get_string("resourceURL"),\
                                MOV.get_string("pushURL"),\
                                MOV.get_string("kind")))
        self.sleepSecs = CHECK_SLEEP
        self.items = movies

    def handle(self):
        logging.info("启动查询序列...")
        while True:
            try:
                logging.info("Updating CONFIG...")
                self.refreshConfig()
                logging.info("Refresh config with %s %s"%(self.sleepSecs, self.items))
                self.doEachTime()
            except Exception:
                logging.info("派度过程中发生错误:")
                logging.info(traceback.format_exc())
            finally:
                logging.info("Sleep for next time search")
                time.sleep(self.sleepSecs)
        logging.info("查询序列结束...")

    def doEachTime(self) -> None:
        for movie in self.items:
            try:
                updater = self.updaters[movie.kind]
                logging.info("Checking Resources for movie %s now..."%(movie.name))
                resources = updater.checkMovieResources(movie)
                logging.info("Diff and Update DB")
                results = updater.diffUpdateFormat(resources)
                logging.info("Pushing to Slack now...")
                for result in results:
                    logging.info("Push %s"%(result))
                    self.post(movie.pushURL, result)
                logging.info("Push done.")
            except Exception:
                logging.info("在处理 %s 时发生错误:"%(movie.name))
                logging.info(traceback.format_exc())

    def post(self, webhook:str, text:str) -> None:
        payload = {
                "text": text
        }
        r = requests.post(webhook, data = json.dumps(payload),timeout=10)
        if r.text != 'ok': raise RuntimeError("信息发送失败")

class BiliBiliUpdater(MovieUpdater):
    def __init__(self, movieDB:MovieDB):
        self.movieDB = movieDB

    def checkMovieResources(self, movie:Movie) -> List[Resource]:
        headers = {
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language":"zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,ja;q=0.5",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "DNT": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36 Edg/83.0.478.45"
        }
        r = requests.get(movie.resourceURL,headers=headers,timeout=10)
        assert(r.status_code == 200)
        soup = BeautifulSoup(r.text,"lxml")
        items = soup.select(".title-link")
        result = []
        for item in items:
            if item.href == None:
                title = item.text
                guid = hash(title)
                result.append(Resource(guid, title, "", movie))
        return result

    def diffUpdateFormat(self,resources:List[Resource]) -> List[str]:
        resources = self.movieDB.diff(resources)
        self.movieDB.storeResources(resources)
        return self._formatMovieUpdate(resources)

    def _formatResource(self,resource:Resource) -> str:
            return "[%s] 有更新： %s <%s|详情>"\
                    %(resource.movie.name, resource.title, \
                    resource.movie.detailURL)

    def _formatMovieUpdate(self,resources:List[Resource]) -> List[str]:
        if len(resources) > 3: return ["\"%s\" 有多条更新 <%s|详情>" \
            %(resources[0].movie.name, resources[0].movie.detailURL)]
        else: return [self._formatResource(res) for res in resources if not "预告 " in res.title]

class IQIYIUpdater(MovieUpdater):
    def __init__(self, movieDB:MovieDB):
        self.movieDB = movieDB

    def checkMovieResources(self, movie:Movie) -> List[Resource]:
        headers = {
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language":"zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "DNT": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
        }
        r = requests.get(movie.resourceURL,headers=headers,timeout=10)
        assert(r.status_code == 200)
        soup = BeautifulSoup(r.text,"lxml")
        items = soup.select(".title-link")
        result = []
        for item in items:
            if item.href == None:
                title = item.text
                guid = hash(title)
                result.append(Resource(guid, title, "", movie))
        return result

    def diffUpdateFormat(self,resources:List[Resource]) -> List[str]:
        resources = self.movieDB.diff(resources)
        self.movieDB.storeResources(resources)
        return self._formatMovieUpdate(resources)

    def _formatResource(self,resource:Resource) -> str:
            return "[%s] 有更新： %s <%s|详情>"\
                    %(resource.movie.name, resource.title, \
                    resource.movie.detailURL)

    def _formatMovieUpdate(self,resources:List[Resource]) -> List[str]:
        if len(resources) > 3: return ["\"%s\" 有多条更新 <%s|详情>" \
            %(resources[0].movie.name, resources[0].movie.detailURL)]
        else: return [self._formatResource(res) for res in resources if not "预告" in res.title]

class MGTVUpdater(MovieUpdater):
    def __init__(self, movieDB:MovieDB):
        self.movieDB = movieDB

    def checkMovieResources(self, movie:Movie) -> List[Resource]:
        headers = {
            "Accept":"*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language":"zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "DNT": "1",
            "Cookie": "_source_=C; __STKUUID=87de1912-be38-44dc-bb30-e2764bdca150; PLANB_FREQUENCY=XuzL5uI28wwmcbUi; MQGUID=1273985921422970880; __MQGUID=1273985921422970880; mba_deviceid=285478c8-8753-5464-450d-faa151df6483; mba_sessionid=b30d78ce-5fb3-412e-2bcc-34785dd35b76; mba_cxid_expiration=1592582400000; mba_cxid=8kpqp21m4cm; sessionid=1592577001095_8kpqp21m4cm; pc_v6=v5; __random_seed=0.07642532216119857; PM_CHKID=3681e9da070bcddb; mba_last_action_time=1592577702988; beta_timer=1592577704138; lastActionTime=1592577766884",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
        }
        r = requests.get(movie.resourceURL,headers=headers,timeout=10)
        assert(r.status_code == 200)
        data = json.loads(r.text)
        shows = data["data"]["list"]
        result = []
        for show in shows:
            title = show["t3"]
            guid = hash(title)
            result.append(Resource(guid, title, "", movie))
        return result

    def diffUpdateFormat(self,resources:List[Resource]) -> List[str]:
        resources = self.movieDB.diff(resources)
        self.movieDB.storeResources(resources)
        return self._formatMovieUpdate(resources)

    def _formatResource(self,resource:Resource) -> str:
            return "%s <%s|详情>"\
                    %(resource.title, \
                    resource.movie.detailURL)

    def _formatMovieUpdate(self,resources:List[Resource]) -> List[str]:
        if len(resources) > 4: return ["\"%s\" 有多条更新 <%s|详情>" \
            %(resources[0].movie.name, resources[0].movie.detailURL)]
        else: return [self._formatResource(res) for res in resources if not "预告" in res.title]


if __name__ == "__main__":
    import argparse
    import logging
    logging.basicConfig(format='[%(asctime)s] %(message)s', datefmt='%Y/%m/%d %H:%M:%S', level=logging.INFO)
    p = argparse.ArgumentParser(prog="推送系统Python版", description="查找到更新的影视剧时,发送更新到 Slack")
    p.add_argument("-c","--config",  dest="config", help="在线配置文件地址", type=str)
    args = p.parse_args()
    if args.config != None:
        CONF_URL = str(args.config)
    else:
        CONF_URL = "http://xxxxx.mazhangjing.com/xxxxxxx.conf"
    logging.info("Initilizing Action Sequence...")
    db = MovieDB()
    
    huginn = MovieHuginn(CONF_URL, {
        "zimuzu": MovieUpdater(db),
        "bilibili": BiliBiliUpdater(db),
        "iqiyi": IQIYIUpdater(db),
        "mgtv": MGTVUpdater(db)
    })
    huginn.handle()
    logging.info("Ending Action Sequence...")

    # print("Update Config")
    # config = refresh_config(CONF_URL)
    # slackURL = "https://hooks.slack.com/services/T3P92AF6F/B3NKV5516/DvuBxxxxxxxxx"
    # post_message(slackURL,str(config))

    # movie = Movie("太空部队", \
    # "http://www.rrys2019.com/resource/39942", \
    # "http://rss.rrys.tv/rss/feed/39942")
    # updater = MovieUpdater(MovieDB())
    # res = updater.checkMovieResources(movie)
    # ans = updater.diffUpdateFormat(res)
    # print(ans)
    # print(updater.movieDB.guids)