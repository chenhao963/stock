''''
version: 1.1
策略：1. 遍历所有的00和60的股票，找出开盘涨停的
      2. 分钟线找出破板的，然后又回封涨停，此时买入
      3.  卖出： 1）开盘价卖出，除非继续涨停
      4. 先算出个股利润，再算出每天的利润
'''
import tushare as ts
import pandas as pd
import csv
import time
import datetime
import os.path
import os
import sys
import threading
import pymysql
import readAndCheckCsv
import downloadFile

ts.set_token('85a6e863fa91060204e5339228932e52c4f90863d773778f3040f14a')

g_dicBuyStock = {}

g_dailyCsvPath= 'C:/python/csv/zhangting/daily/2019to2020/'
g_minuteCsvPath = 'C:/python/csv/zhangting/minute/202001060731/'
g_calendarFile = 'C:/python/csv/zhangting/validCalendar.csv'

#计算涨停价，涨停价 = 昨日收盘价 * 1.100 (四舍五入，取小数点2位)
def calculateZhangTingPrice(price):
    highestPrice = round(float(price) * 1.100, 2)
    #print(f'calculateZhangtingPrice: price={price}, highestPrice={highestPrice}')
    return highestPrice

#从本地文件夹获取目录下的所有00和60开头的文件
def getStockIDFromLocal(filePath):
    listAllStocks = []
    filesList = []
    files = []
    for root, dirs, files in os.walk(filePath):
        break

    for i in range(len(files)):
        if (files[i][0:2] == '00') or (files[i][0:2] == '60'):
            listAllStocks.append(files[i][0:9])
    print(f'所有股票池: num = {len(listAllStocks)}, list = {listAllStocks}')
    return listAllStocks

#从日线文件夹下读取所有股票的日线文件数据，然后把当日开盘即涨停的股票保存到文件imitAllstock.csv,filaPath = 'C:/python/csv/zhangting/daily/2019to2020/'
def saveOpenLimitStockToCsv(startDate, endDate, filePath):
    listAllStocks = getStockIDFromLocal(filePath)
    limitFileName = filePath + 'limitAllstock.csv'
    readAndCheckCsv.deleteFile(limitFileName)
    for i in range(len(listAllStocks)):
        fileName = filePath + listAllStocks[i] + '.csv'
        try:
            with open(fileName, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tradeDate = row['trade_date']
                    open1 = float(row['open'])
                    pre_close = float(row['pre_close'])
                    limit = calculateZhangTingPrice(pre_close)
                    if open1 == limit:
                        readAndCheckCsv.saveLimitToCsv(limitFileName, tradeDate, listAllStocks[i])
        except Exception as e:
            print(e)
            continue

#获得合法交易日: 从本地文件g_calendarFile读取，并return合理的开始和结束日期，还有calendar列表
def getTradeCalendarFromLocalFile(startDate, endDate):
    listTempCalendar = []
    listTradeCalendar = []

    try:
        with open(g_calendarFile, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cal_date = row['cal_date']
                listTempCalendar.append(cal_date)
    except Exception as e:
        listTempCalendar = []
    #print('listTempCalendar: ' + str(listTempCalendar))
    if 0 == len(listTempCalendar):
        print(f'日期文件不存在，请检查! e={e}')
        exit(0)

    begin_date = datetime.datetime.strptime(startDate, "%Y%m%d")
    calendarFileBeginDate = datetime.datetime.strptime(listTempCalendar[0], "%Y%m%d")
    if begin_date < calendarFileBeginDate:
        print(f'起始日期太早了，startDate = {startDate}, calendarFileBeginDate = {listTempCalendar[0]}')
        exit(0)

    end_date = datetime.datetime.strptime(endDate, "%Y%m%d")
    calendarFileEndDate = datetime.datetime.strptime(listTempCalendar[len(listTempCalendar)-1], "%Y%m%d")
    if end_date > calendarFileEndDate:
        print(f'结束日期太晚了，end_date = {end_date}, calendarFileEndDate = {listTempCalendar[len(listTempCalendar)-1]}')
        exit(0)

    startDataFlag = False
    endDateFlag = False
    if (startDate not in listTempCalendar) or (endDate not in listTempCalendar):
        begin_date = datetime.datetime.strptime(startDate, "%Y%m%d")
        end_date   = datetime.datetime.strptime(endDate, "%Y%m%d")
        if startDate in listTempCalendar:
            startDataFlag = True
        if endDate in listTempCalendar:
            endDateFlag = True
        for i in range(12):
            if False == startDataFlag:
                delta = datetime.timedelta(days=1)
                begin_date = begin_date + delta
                tempDate = str(begin_date.date())
                tempDate = tempDate.replace('-', '')
                if tempDate in listTempCalendar:
                    startDate = tempDate
                    startDataFlag = True

            if False == endDateFlag:
                delta = datetime.timedelta(days=-1)
                end_date = end_date + delta
                tempDate = str(end_date.date())
                tempDate = tempDate.replace('-', '')
                if tempDate in listTempCalendar:
                    endDate = tempDate
                    endDateFlag = True

    i = listTempCalendar.index(startDate)
    j = listTempCalendar.index(endDate)
    listTradeCalendar = listTempCalendar[i:(j+1)]

    return startDate, endDate, listTradeCalendar

#获得某一天某个股票的最高价和收盘价,open, high, close
def getOnedayHighestAndClosePriceFromLocal(date, ts_code):
    openPrice, lowPrice, highPrice, closePrice = 0.0, 10000, 0.0, 0.0
    fileName = g_dailyCsvPath + ts_code + '.csv'

    try:
        with open(fileName, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trade_date = row['trade_date']
                if date in trade_date:
                    openPrice = float(row['open'])
                    lowPrice = float(row['low'])
                    highPrice = float(row['high'])
                    closePrice = float(row['close'])
                    break
    except:
        t = 0
    return openPrice, lowPrice, highPrice, closePrice

#计算收益率
def calculateYield(date):
    global g_dicBuyStock
    #g_dicBuyStock = {'002500.SZ':'7.99'}  #临时测试使用
    if 0 == len(g_dicBuyStock):
        return
    tempDicBuyStock = g_dicBuyStock.copy()
    try:
        for stock, value in g_dicBuyStock.items():
            open1, low, high, close = getOnedayHighestAndClosePriceFromLocal(date, stock)
            highestPrice = float(value[0])
            #连续涨停几次，就需要算出此时涨停价是多少
            for i in range(int(tempDicBuyStock[stock][1])):
                highestPrice = round(highestPrice * 1.1, 2)

            if (0 == open1) or (0 == low) or (0 == close):
                print(f'    Abnormal: date={date},stock={stock}, open1={open1}, low={low}, high={high}, close={close},highestPrice={highestPrice}')
                continue

            #继续涨停则不卖
            if float(low) == float(highestPrice):
                print(f'    不卖：继续涨停. date = {date}, code = {stock}, open1={open1}, low={low}, high={high}, close={close}')
                tempDicBuyStock[stock][1] += 1
                continue
            #开盘价是涨停价，但是破板了，需要立即卖出
            elif (float(open1) == float(highestPrice)) and (float(low) < float(highestPrice)):
                yeild = int( ( (float(open1) * 0.98 - float(value[0])) / float(value[0]) ) * 100 )
            #开盘价不是涨停价，立即以开盘价卖出
            else:
                #否则按当天开盘价卖出
                yeild = int( ( (open1 - float(value[0])) / float(value[0]) ) * 100 )
            print(f'    卖出：日期 = {date}, 股票代码 = {stock}, 开盘价 = {open1}，收益 = {yeild}%')
            tempDicBuyStock.pop(stock)
            readAndCheckCsv.saveProfitToCsv(stock, date, yeild)
    except Exception as e:
        print(e)

    g_dicBuyStock = tempDicBuyStock.copy()

#从csv文件里读取某一个股票的某一天在某一时间段内的分钟数据，并保存到list里面返回
def getOneStockMinuteDataFromCsv(ts_code, date, endTime):
    fileName = g_minuteCsvPath + ts_code + '.csv'
    low, high,close = 0, 0, 0
    tradeTime = ''
    lastAddFlag = False
    qtClose, ztClose =0,0 #前天收盘价，昨天收盘价
    listClose150000 = []      #15:00:00收盘价
    listData = []
    date = downloadFile.convertDate(date)

    try:
        with open(fileName, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tradeTime = row['trade_time']
                low = row['low']
                high = row['high']
                close = row['close']
                if '15:00:00' in tradeTime:
                    listClose150000.append(tradeTime)
                    listClose150000.append(low)
                    listClose150000.append(high)
                    listClose150000.append(close)

                if date in tradeTime:
                    if endTime in tradeTime:
                        break
                    if False == lastAddFlag: #昨日收盘价保存在list第一条记录里
                        close150000Len = len(listClose150000)
                        if close150000Len < 8:
                            listData = []
                            break
                        listData.append(listClose150000[close150000Len - 1 - 7])
                        listData.append(listClose150000[close150000Len - 1 - 6])
                        listData.append(listClose150000[close150000Len - 1 - 5])
                        listData.append(listClose150000[close150000Len - 1 - 4])
                        listData.append(listClose150000[close150000Len - 1 - 3])
                        listData.append(listClose150000[close150000Len - 1 - 2])
                        listData.append(listClose150000[close150000Len - 1 - 1])
                        listData.append(listClose150000[close150000Len - 1 - 0])
                        lastAddFlag = True
                    listData.append(tradeTime)
                    listData.append(low)
                    listData.append(high)
                    listData.append(close)
    except Exception as e:
        listData = []
    #print(listData)
    return listData

#从股票池里读取某一天某个时间段内的所有股票的分钟数据，并保存在一个字典里，ts_code作为key，某一个股票的数据作为value
def getCurrentDayMinuteDataFromCsv(date, endTime, listAllStocks):
    allStockInfo = {}
    oneStockInfo = []
    for k in range(len(listAllStocks)):
        oneStockInfo = []
        oneStockInfo = getOneStockMinuteDataFromCsv(listAllStocks[k], date, endTime)
        if len(oneStockInfo):
            allStockInfo[listAllStocks[k]] = oneStockInfo
    return allStockInfo

def mainFunc(startDate, endDate, endTime):
    global g_dicBuyStock

    hasReachMaxBoughtNum = False
    maxBoughtNum = 7

    startDate, endDate, listTradeCalendar = getTradeCalendarFromLocalFile(startDate, endDate)  # 从本地获取可交易日期
    print(f'交易日期范围 = {str(listTradeCalendar)}')

    # 读取开盘即涨停的csv文件，把所有数据返回到一个字段里，key是日期，value是股票字符串
    dictLimitStock = readAndCheckCsv.getOpenLimitStockFromCsv(g_dailyCsvPath + 'limitAllstock.csv')

    #保存某只股票分钟数据，其中第一条记录是前天的收盘数据，第二条是昨天的收盘数据，第三条才是当前日期的分钟数据,数据结构：ts_time, low, high, close
    # {'000796.SZ': ['2020-06-29 15:00:00', '9.49', '9.5', '9.49', '2020-06-30 15:00:00', '10.44', '10.44', '10.44', '2020-07-01 09:30:00', '11.48', '11.48', '11.48',
    dictOneDayMinuteInfo = {}
    readAndCheckCsv.deleteFile(readAndCheckCsv.g_profitFileName) #初始化，把老的profit文件先删除

    #获取一天内某个时间段内需要循环的次数
    startTime = datetime.datetime.strptime('2020-01-01 09:30:00', '%Y-%m-%d %H:%M:%S')
    lastTime = datetime.datetime.strptime('2019-01-01 '+endTime, '%Y-%m-%d %H:%M:%S')
    delta = lastTime - startTime
    loopMin = int(delta.seconds / 60) - 90

    #轮询所有交易日
    for i in range(0, len(listTradeCalendar)):
        date = listTradeCalendar[i]
        hasReachMaxBoughtNum = False
        skipStockList = []
        listAllStocks = []

        stockZhangTingList1 = []
        stockSkipList2 = []
        print(f'交易日期：{date}')

        #卖出昨天买入的股票
        calculateYield(date) #和昨天比较，计算收益率

        #结束那天只卖出股票，不再买入
        if endDate == date:
            break

        #获取当天不停牌的所有股票在9:30--11:00之间的数据, 数据结构：ts_time, low, high, close
        listAllStocks = dictLimitStock[date].split(',')

        dictOneDayMinuteInfo = getCurrentDayMinuteDataFromCsv(date, endTime, listAllStocks)
        if 0 == len(dictOneDayMinuteInfo):
            print('continue')
            continue

        #1. 把开盘就是涨停价的股票赋值到list里面 stockZhangTingList1
        stockZhangTingList1 = listAllStocks

        #2. 如果这个股票一直处于涨停价，则保存到list2，需要过滤掉
        for j in range(len(stockZhangTingList1)):
            open1, low, high, close = getOnedayHighestAndClosePriceFromLocal(date, stockZhangTingList1[j])
            if low == high:
                stockSkipList2.append(stockZhangTingList1[j])

        #3，把一直处于涨停价的股票过滤掉
        stockZhangTingList1 = list(set(stockZhangTingList1).difference(stockSkipList2))
        stockZhangTingList1.sort()
        listAllStocks = stockZhangTingList1
        print(f'    stockZhangTingList num={len(listAllStocks)}, list = {listAllStocks}')

        #4. 轮询所有符合条件的股票，如果有过开盘又封盘的，则买入
        for j in range(len(listAllStocks)):
            startMin = 1
            openFlag = False
            keyCode = listAllStocks[j]

            #达到当日买入上限则跳过当日
            if True == hasReachMaxBoughtNum:
                break

            try:  # 获得当前股票的昨日收盘价
                oldPrice = float(dictOneDayMinuteInfo[keyCode][7])
            except Exception as e:  # 如果股票今天才上市，那么昨天就没有数据，需要跳过
                continue

            #计算今天的涨停价是多少
            highestPrice = calculateZhangTingPrice(oldPrice)

            startMin = 2
            for k in range(startMin, loopMin):
                currentlowPrice = float(dictOneDayMinuteInfo[keyCode][4 * k + 9])  # 根据最低价计算
                # 开板了，则设置标志位openFlag为true
                if float(currentlowPrice) < float(highestPrice):
                    openFlag = True

                #开板过，又达到了涨停价，则买入，继续轮询下一个股票
                currentHighPrice = float(dictOneDayMinuteInfo[keyCode][4 * k + 11])  # 根据收盘价计算
                if (True == openFlag) and (float(currentHighPrice) == float(highestPrice)):
                    tempList = [str(highestPrice), 1]
                    g_dicBuyStock[keyCode] = tempList
                    time1 = dictOneDayMinuteInfo[keyCode][4 * k + 8]
                    print(f'    买入：日期时间= {time1}, 股票代码 = {keyCode}, 买入价格 = {str(g_dicBuyStock[keyCode][0])}')
                    if len(g_dicBuyStock) >= maxBoughtNum:
                        hasReachMaxBoughtNum = True
                    break

    readAndCheckCsv.calculateProfit(readAndCheckCsv.g_profitFileName)
    readAndCheckCsv.drawProfitPic() #打印 startDate~~~~endDate 收益率

if __name__ == "__main__":
    localtime = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    print(f'Start at {localtime}')

    startDate = '20200701'
    endDate   = '20200731'
    endTime = '14:30:00'

    #第一次运行本程序，需要先下载下面3个文件：日历文件、日线文件、分钟文件
    #downloadFile.saveTradeCalendarToLocal(g_calendarFile)
    #downloadFile.downloadDailyToCsv(startDate, endDate, filePath)
    #downloadFile.downloadMinutesToCsv(startDate, endDate, filePath)

    mainFunc(startDate, endDate, endTime)

    localtime = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    print(f'End at {localtime}')
