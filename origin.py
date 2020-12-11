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
        r = requests.get(movie.resourceURL,headers=headers)
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
    def __init__(self, configURL:str, updater:MovieUpdater) -> None:
        self.configURL = configURL
        self.webhook = ""
        self.sleepSecs = -1
        self.items = []
        self.updater = updater
        self.refreshConfig()

    def refreshConfig(self) -> None:
        conf = ConfigFactory.parse_URL(self.configURL)
        if (type(conf) == list):
            conf = ConfigFactory.parse_file("default.conf")
        WEBHOOK_URL = conf.get_string("push.url")
        CHECK_SLEEP = conf.get_int("push.sleep")
        MOVIE_LIST = conf.get_list("items")
        print("Update with URL %s, and Sleep Seconds %s, Keywords %s"\
            %(WEBHOOK_URL, CHECK_SLEEP, str(MOVIE_LIST)))
        movies = []
        for MOV in MOVIE_LIST:
            movies.append(Movie(MOV.get_string("name"),\
                                MOV.get_string("detailURL"),\
                                MOV.get_string("resourceURL")))
        self.webhook = WEBHOOK_URL
        self.sleepSecs = CHECK_SLEEP
        self.items = movies

    def handle(self):
        print("启动查询序列...")
        while True:
            try:
                print("Updating CONFIG...")
                self.refreshConfig()
                print("Refresh config with %s %s"%(self.sleepSecs, self.items))
                self.doEachTime()
            except Exception:
                print("发生错误:")
                print(traceback.format_exc())
            finally:
                print("Sleep for next time search")
                time.sleep(self.sleepSecs)
        print("查询序列结束...")

    def doEachTime(self) -> None:
        for movie in self.items:
            print("Checking Resources for movie %s now..."%(movie.name))
            resources = self.updater.checkMovieResources(movie)
            print("Diff and Update DB")
            results = self.updater.diffUpdateFormat(resources)
            print("Pushing to Slack now...")
            for result in results:
                print("Push %s"%(result))
                self.post(result)

    def post(self, text:str) -> None:
        payload = {
                "text": text
        }
        r = requests.post(self.webhook, data = json.dumps(payload))
        if r.text != 'ok': raise RuntimeError("信息发送失败")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(prog="推送系统Python版", description="查找到更新的影视剧时,发送更新到 Slack")
    p.add_argument("-c","--config",  dest="config", help="在线配置文件地址", type=str)
    args = p.parse_args()
    if args.config != None:
        CONF_URL = str(args.config)
    else:
        CONF_URL = "http://xxxxx.mazhangjing.com/xxxxx/xxxx"
    print("Initilizing Action Sequence...")
    huginn = MovieHuginn(CONF_URL, MovieUpdater(MovieDB()))
    huginn.handle()
    print("Ending Action Sequence...")

    # print("Update Config")
    # config = refresh_config(CONF_URL)
    # slackURL = "https://hooks.slack.com/services/T3P92xxxx/B3NKV5516/DvuBxxxxxx"
    # post_message(slackURL,str(config))

    # movie = Movie("太空部队", \
    # "http://www.rrys2019.com/resource/39942", \
    # "http://rss.rrys.tv/rss/feed/39942")
    # updater = MovieUpdater(MovieDB())
    # res = updater.checkMovieResources(movie)
    # ans = updater.diffUpdateFormat(res)
    # print(ans)
    # print(updater.movieDB.guids)