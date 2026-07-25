import sys; sys.path.insert(0,'/home/mdsadmin/Stock/tw-stock-analysis')
from pymongo import MongoClient
from datetime import datetime
import argparse
ap=argparse.ArgumentParser(); ap.add_argument('--apply',action='store_true'); a=ap.parse_args()
db=MongoClient('localhost',27017)['tw_stock_analysis']
src=db.securities_lending; dst=db.securities_lending_detail
cur=list(src.find({'date':{'$type':'string'}}))
moved=err=0
for d in cur:
    try:
        dt=datetime.strptime(str(d['date'])[:10],'%Y-%m-%d')
    except ValueError:
        err+=1; continue
    if a.apply:
        d2=dict(d); d2['date']=dt
        dst.replace_one({'_id':d['_id']}, d2, upsert=True)  # 保留_id,冪等
        src.delete_one({'_id':d['_id']})
    moved+=1
print(f"{'[APPLY]' if a.apply else '[DRY]'} 搬移借券明細(轉datetime) {moved} 筆, 錯誤 {err}")
if a.apply:
    print(f"securities_lending 剩 string-date: {src.count_documents({'date':{'$type':'string'}})} | date型: {src.count_documents({'date':{'$type':'date'}})}")
    print(f"securities_lending_detail 總: {dst.count_documents({})}")
