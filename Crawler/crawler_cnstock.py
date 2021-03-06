# -*- coding: utf-8 -*-
"""
Created on Sat Feb 3 13:41:50 2018

@author: Damon Li
"""

import time, re, requests
from concurrent import futures
from bs4 import BeautifulSoup
from pymongo import MongoClient
import Text_Analysis.text_mining as tm

import gevent
from gevent import monkey,pool
#全部变成gevent框架
monkey.patch_all()


class WebCrawlFromcnstock(object):
    '''Crawl company news from 'http://company.cnstock.com/company/scp_gsxw/1',
                               'http://ggjd.cnstock.com/gglist/search/qmtbbdj/1',
                               'http://ggjd.cnstock.com/gglist/search/ggkx/1' website.

    # Arguments:
        totalPages: Number of pages set to be crawled.
        将整个网页分成totalPages/Range部分进行多线程处理
        Range: Divide total web pages into totalPages/Range parts 
               for multi-threading processing.
        ThreadsNum（多线程）: Number of threads needed to be start.
        dbName: Name of database.
        colName: Name of collection.
        IP: Local IP address.
        PORT: Port number corresponding to IP address.
    '''

    def __init__(self,**kwarg):
        self.ThreadsNum = kwarg['ThreadsNum']
        self.dbName = kwarg['dbName']
        self.colName = kwarg['collectionName']
        self.IP = kwarg['IP']
        self.PORT = kwarg['PORT']
        self.Prob = .5
        self.realtimeNewsURL = []
        self.tm = tm.TextMining(IP="localhost",PORT=27017)

    def ConnDB(self):
        '''Connect mongodb.
        '''
        Conn = MongoClient(self.IP, self.PORT) 
        db = Conn[self.dbName]
        self._collection = db.get_collection(self.colName)

    def countchn(self,string):
        '''Count Chinese numbers and calculate the frequency of Chinese occurrence.
            统计汉语数字，计算汉语出现的频率

        # Arguments:
            string: Each part of crawled website analyzed by BeautifulSoup.
        '''
        #中文, 必须表明所需编码,U代表是对字符串进行unicode编码
        #u'[\u1100-\uFFFDh]+?' 相当于所有的中文字符和其他特殊字符
        #这个h是什么意思？不会是html里面的</h>吧.....
        pattern = re.compile(u'[\u1100-\uFFFDh]+?')
        result = pattern.findall(string)
        #findalll得到的结果是一个List,里面的元素都是且仅是单一的中文，
        chnnum = len(result)
        possible = chnnum/len(str(string))
        #返回中文长度和频率
        return (chnnum, possible)


    def getUrlInfo(self,url): 
        '''Analyze website and extract useful information.
           返回一个网站的发布时间和正文中的所以中文
        '''
        #这里的爬虫很直接，主要是网站基本没有反爬机制
        respond = requests.get(url)
        #确定编码方式
        respond.encoding = BeautifulSoup(respond.content, "lxml").original_encoding
        #将respond.text改成了respond.content
        bs = BeautifulSoup(respond.content, "lxml")
        span_list = bs.find_all('span') #找每个新闻的时间
        #z找到每个新闻的内容，标签
        part = bs.find_all('p')
        article = ''
        date = ''
        for span in span_list:
            #这个爬的是每个新闻的网站而不是https://company.cnstock.com/company/scp_gsxw
            if 'class' in span.attrs and span['class'] == ['timer']:
                date = span.text
                break
        #把所以中文频率大于0.5的内容合在一起，这里会忽略标签
        for paragraph in part:
            chnstatus = self.countchn(str(paragraph))
            possible = chnstatus[1]
            if possible > self.Prob:
                #如果中文字符的频率大于0.5
                article += str(paragraph)

        while article.find('<') != -1 and article.find('>') != -1:
            #把<p>和</p>去掉
            string = article[article.find('<'):article.find('>')+1]
            article = article.replace(string,'')
        #\u3000是去掉中文空格
        while article.find('\u3000') != -1:
            article = article.replace('\u3000','')

        #re.split 切割字符串，有一些段落中会有 +|\n+？
        article = ' '.join(re.split(' +|\n+', article)).strip() 

        #返回最新的时间和所以的内容中文字符
        return date, article

    def GenPagesLst(self,totalPages,Range,initPageID): #621,10,1
        '''Generate page number list using Range parameter.
        '''
        PageLst = []
        k = initPageID
        while k+Range-1 <= totalPages:
            PageLst.append((k,k+Range-1))
            k += Range
        #这里是不是应该改成>？
        if k+Range-1 < totalPages:
            PageLst.append((k,totalPages))
        return PageLst

    def CrawlHistoryCompanyNews(self,startPage,endPage,url_Part_1):
        '''Crawl historical company news 
        '''
        self.ConnDB() #连接到数据库
        AddressLst = self.extractData(['Address'])[0]
        if AddressLst == []:
            urls = []
            for pageId in range(startPage,endPage+1):
                #现在中国证券网的翻页机制已经变成javascrip了
                urls.append(url_Part_1 + str(pageId))
            for url in urls:
                print(url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    
                    if 'href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span'):
                        date, article = self.getUrlInfo(a['href'])
                        while article == '' and self.Prob >= .1:
                            self.Prob -= .1
                            date, article = self.getUrlInfo(a['href'])
                        self.Prob =.5
                        if article != '':
                            data = {'Date' : date,
                                    'Address' : a['href'],
                                    'Title' : a['title'],
                                    'Article' : article}
                            self._collection.insert_one(data)
        else:
            urls = []
            for pageId in range(startPage,endPage+1):
                urls.append(url_Part_1 + str(pageId))
            for url in urls:
                print(' <Re-Crawl url> ', url)
                resp = requests.get(url)
                resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
                bs = BeautifulSoup(resp.text, "lxml")
                a_list = bs.find_all('a')
                for a in a_list:
                    if 'href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span'):
                        if a['href'] not in AddressLst:
                            date, article = self.getUrlInfo(a['href'])
                            while article == '' and self.Prob >= .1:
                                self.Prob -= .1
                                date, article = self.getUrlInfo(a['href'])
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a['title'],
                                        'Article' : article}
                                self._collection.insert_one(data)

    def CrawlRealtimeCompanyNews(self,url_part_lst):
        '''Continue crawling company news from first website page 
           every once in a while and extract the useful information, 
           including summary, key words, released date, related stock 
           codes list and main body.
           每隔一段时间从第一个网站页面继续抓取公司新闻，并提取有用信息，
           包括摘要、关键词、发布日期、相关股票代码列表和正文。
        '''
        doc_lst = []
        self.ConnDB()
        self._AddressLst = self.extractData(['Address'])[0]
        for url_Part in url_part_lst:
            url = url_Part + str(1)
            resp = requests.get(url)
            resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding 
            bs = BeautifulSoup(resp.text, "lxml")
            a_list = bs.find_all('a')
            if len(self.realtimeNewsURL) == 0:
                for a in a_list:
                    if ('href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span')) or ('href' in a.attrs and 'target' in a.attrs \
                    and 'title' in a.attrs and a['href'].find('http://ggjd.cnstock.com/company/') != -1 \
                    and a.parent.find('span')):
                        #表示这个网址的内容未被爬取过
                        if a['href'] not in self._AddressLst:
                            self.realtimeNewsURL.append(a['href'])
                            date, article = self.getUrlInfo(a['href'])
                            while article == '' and self.Prob >= .1:
                                self.Prob -= .1
                                date, article = self.getUrlInfo(a['href'])
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a['title'],
                                        'Article' : article}
                                self._collection.insert_one(data)
                                doc_lst.append(a['title'] + ' ' + article)
                                print(' [' + date + '] ' + a['title'])
            else:
                for a in a_list:
                    if ('href' in a.attrs and 'target' in a.attrs and 'title' in a.attrs \
                    and a['href'].find('http://company.cnstock.com/company/') != -1 \
                    and a.parent.find('span')) or ('href' in a.attrs and 'target' in a.attrs \
                    and 'title' in a.attrs and a['href'].find('http://ggjd.cnstock.com/company/') != -1 \
                    and a.parent.find('span')):
                        if a['href'] not in self.realtimeNewsURL and a['href'] not in self._AddressLst:
                            self.realtimeNewsURL.append(a['href'])
                            date, article = self.getUrlInfo(a['href'])
                            while article == '' and self.Prob >= .1:
                                self.Prob -= .1
                                date, article = self.getUrlInfo(a['href'])
                            self.Prob =.5
                            if article != '':
                                data = {'Date' : date,
                                        'Address' : a['href'],
                                        'Title' : a['title'],
                                        'Article' : article}
                                self._collection.insert_one(data)
                                doc_lst.append(a['title'] + ' ' + article)
                                print(' [' + date + '] ' + a['title'])
        return doc_lst

    def extractData(self,tag_list):
        '''Extract column data with tag in 'tag_list' to the list.
        '''
        data = []
        for tag in tag_list:
            exec(tag + " = self._collection.distinct('" + tag + "')")
            exec("data.append(" + tag + ")")
        return data

    def coroutine_run(self,totalPages,Range,initPageID,**kwarg):
        '''Coroutines running.
        '''
        jobs = []
        page_ranges_lst = self.GenPagesLst(totalPages,Range,initPageID)
        for page_range in page_ranges_lst:
            jobs.append(gevent.spawn(self.CrawlHistoryCompanyNews,page_range[0],page_range[1],kwarg['url_Part_1']))
        #多线程
        gevent.joinall(jobs) 

    def multi_threads_run(self,**kwarg):
        '''Multi-threading running.
        '''
        page_ranges_lst = self.GenPagesLst()
        print(' Using ' + str(self.ThreadsNum) + ' threads for collecting news ... ')
        with futures.ThreadPoolExecutor(max_workers=self.ThreadsNum) as executor:
            future_to_url = {executor.submit(self.CrawlHistoryCompanyNews,page_range[0],page_range[1]) : \
                             ind for ind, page_range in enumerate(page_ranges_lst)}  

    def classifyRealtimeStockNews(self):
        '''Continue crawling and classifying news(articles/documents) every 60s. 
        '''
        while True:
            print(' * start crawling news from CNSTOCK ... ')
            doc_list = self.CrawlRealtimeCompanyNews(['http://company.cnstock.com/company/scp_gsxw/',\
                                                    'http://ggjd.cnstock.com/gglist/search/qmtbbdj/',\
                                                    'http://ggjd.cnstock.com/gglist/search/ggkx/']) #
            print(' * finish crawling ... ')
            if len(doc_list) != 0:
                self.tm.classifyRealtimeStockNews(doc_list)
            time.sleep(60)